import asyncio
import re
from typing import Optional, Union, Any, List, Dict
import numpy as np
import json
from loguru import logger

from ..message_handler import message_handler
from .types import WebSocketSend, BroadcastContext
from .tts_manager import TTSTaskManager
from ..agent.output_types import SentenceOutput, AudioOutput
from ..agent.input_types import BatchInput, TextData, ImageData, TextSource, ImageSource
from ..asr.asr_interface import ASRInterface
from ..live2d_model import Live2dModel
from ..tts.tts_interface import TTSInterface
from ..utils.stream_audio import prepare_audio_payload


# Coarse language buckets used by both the voice-language derivation (V) and the
# light per-sentence reply detector (R). Anything outside this set is treated as
# "unknown" (no gating -> speak verbatim, the conservative default).
_KNOWN_LANGS = {"ja", "zh", "en", "ko"}

# Light per-sentence reply-language detector. Regex only (zero network / no model),
# safe to run in the hot async loop. Order matters: kana (Hiragana/Katakana) -> ja
# FIRST, then Hangul -> ko, then Han-without-kana -> zh, then Latin -> en.
_RE_KANA = re.compile(r"[぀-ゟ゠-ヿ]")  # Hiragana + Katakana
_RE_HANGUL = re.compile(r"[가-힣ᄀ-ᇿ㄰-㆏]")  # Hangul
_RE_HAN = re.compile(r"[一-鿿㐀-䶿]")  # CJK Han (treat as Chinese)
_RE_LATIN = re.compile(r"[A-Za-z]")


def _detect_lang(text: str) -> Optional[str]:
    """Lightly detect the language bucket of a reply sentence (R).

    Returns one of {'ja','zh','en','ko'} or None when nothing recognizable is found
    (e.g. pure punctuation/numbers) -> caller treats None as "do not gate".

    KNOWN LIMITATION: a Japanese sentence written in pure kanji with no kana detects
    as 'zh' (Han -> Chinese). This is unfixable with a light regex detector; accept it.
    """
    if not text:
        return None
    if _RE_KANA.search(text):
        return "ja"
    if _RE_HANGUL.search(text):
        return "ko"
    if _RE_HAN.search(text):
        return "zh"
    if _RE_LATIN.search(text):
        return "en"
    return None


def derive_voice_lang(character_config: Any) -> Optional[str]:
    """Derive the active character's voice language V from its edge_tts voice ShortName.

    V = the locale language subtag (part before the FIRST hyphen) of
    ``character_config.tts_config.edge_tts.voice`` (e.g. 'ja-JP-NanamiNeural' -> 'ja',
    'zh-CN-XiaoyiNeural' -> 'zh'), lowercased and clamped to {'ja','zh','en','ko'}.

    Returns None when V cannot be derived (no tts_config / non-edge engine / edge_tts
    None / unrecognized subtag). A None V means "skip gating" -> speak R verbatim, since
    cross-language voice is the opt-in case (a non-edge or unknown voice should not
    silently trigger translation).
    """
    try:
        tts_config = getattr(character_config, "tts_config", None)
        if tts_config is None:
            return None
        edge_tts = getattr(tts_config, "edge_tts", None)
        if edge_tts is None:
            return None
        voice = getattr(edge_tts, "voice", None)
        if not voice:
            return None
        subtag = str(voice).split("-", 1)[0].strip().lower()
        return subtag if subtag in _KNOWN_LANGS else None
    except Exception as e:
        logger.debug(f"Could not derive voice language: {type(e).__name__}: {e}")
        return None


# Convert class methods to standalone functions
def create_batch_input(
    input_text: str,
    images: Optional[List[Dict[str, Any]]],
    from_name: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> BatchInput:
    """Create batch input for agent processing"""
    return BatchInput(
        texts=[
            TextData(source=TextSource.INPUT, content=input_text, from_name=from_name)
        ],
        images=[
            ImageData(
                source=ImageSource(img["source"]),
                data=img["data"],
                mime_type=img["mime_type"],
            )
            for img in (images or [])
        ]
        if images
        else None,
        metadata=metadata,
    )


async def process_agent_output(
    output: Union[AudioOutput, SentenceOutput],
    character_config: Any,
    live2d_model: Live2dModel,
    tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
    translate_engine: Optional[Any] = None,
    subtitle_translate_engine: Optional[Any] = None,
) -> str:
    """Process agent output with character information and optional translation"""
    # Display name shown on the AI side of the chat: prefer the explicit
    # character_name, else fall back to conf_name. Never let it be empty (which the
    # frontend would render as a hardcoded 'AI'/'A').
    output.display_text.name = (
        character_config.character_name or character_config.conf_name
    )
    output.display_text.avatar = character_config.avatar

    # Derive the voice language V once per output (not per sentence): the audio
    # translate gate translates a sentence only when V differs from the detected
    # reply language R. None V -> gating skipped (speak verbatim).
    voice_lang = derive_voice_lang(character_config)

    full_response = ""
    try:
        if isinstance(output, SentenceOutput):
            full_response = await handle_sentence_output(
                output,
                live2d_model,
                tts_engine,
                websocket_send,
                tts_manager,
                translate_engine,
                subtitle_translate_engine,
                voice_lang,
            )
        elif isinstance(output, AudioOutput):
            full_response = await handle_audio_output(output, websocket_send)
        else:
            logger.warning(f"Unknown output type: {type(output)}")
    except Exception as e:
        logger.error(f"Error processing agent output: {e}")
        await websocket_send(
            json.dumps(
                {"type": "error", "message": f"Error processing response: {str(e)}"}
            )
        )

    return full_response


async def handle_sentence_output(
    output: SentenceOutput,
    live2d_model: Live2dModel,
    tts_engine: TTSInterface,
    websocket_send: WebSocketSend,
    tts_manager: TTSTaskManager,
    translate_engine: Optional[Any] = None,
    subtitle_translate_engine: Optional[Any] = None,
    voice_lang: Optional[str] = None,
) -> str:
    """Handle sentence output type with optional translation support.

    Two INDEPENDENT translations may happen per sentence:
    - AUDIO: ``translate_engine`` rewrites ``tts_text`` for the spoken voice. This is
      now AUTOMATIC (no user toggle): the engine runs ONLY when the character's voice
      language ``voice_lang`` (V) differs from the detected reply language R of the
      sentence. Same-language (e.g. Japanese reply + Japanese voice) -> skip + speak R
      verbatim. When V cannot be derived (None) the gate is skipped (speak verbatim).
      The engine's actual TARGET stays the user-configured target_lang; V only drives
      the skip/translate DECISION.
    - SUBTITLE (display-only): ``subtitle_translate_engine`` rewrites a SEPARATE
      ``subtitle_text`` for the on-screen subtitle. UNCHANGED: gated only by the user's
      explicit subtitle language pick (built in init_translate). The canonical reply
      text (``display_text.text`` == R) is NEVER mutated, so ``full_response`` — the sole
      source for memory + history — stays on the original reply.
    """
    full_response = ""
    async for display_text, tts_text, actions in output:
        logger.debug(f"🏃 Processing output: '''{tts_text}'''...")

        if translate_engine:
            # Per-sentence AUTO gate: translate only when there is non-trivial content
            # AND the voice language V differs from the detected reply language R.
            if len(re.sub(r'[\s.,!?，。！？\'"』」）】\s]+', "", tts_text)):
                reply_lang = _detect_lang(tts_text)
                if voice_lang and reply_lang and reply_lang != voice_lang:
                    tts_text = translate_engine.translate(tts_text)
                    logger.info(
                        f"🏃 Audio translated (R={reply_lang} != V={voice_lang}): "
                        f"'''{tts_text}'''..."
                    )
                else:
                    logger.debug(
                        f"🚫 Audio translation skipped (R={reply_lang}, V={voice_lang}); "
                        "speaking reply verbatim."
                    )
        else:
            logger.debug("🚫 No translation engine available. Skipping translation.")

        # Canonical reply text (R). Accumulated for memory/history — DO NOT mutate.
        full_response += display_text.text

        # Display-only subtitle translation: compute a SEPARATE field; never touch
        # display_text.text. If no subtitle engine, the subtitle stays = R.
        subtitle_text = display_text.text
        if subtitle_translate_engine:
            if len(re.sub(r'[\s.,!?，。！？\'"』」）】\s]+', "", display_text.text)):
                subtitle_text = subtitle_translate_engine.translate(display_text.text)
            logger.info(f"🏃 Subtitle after translation: '''{subtitle_text}'''...")

        await tts_manager.speak(
            tts_text=tts_text,
            display_text=display_text,
            actions=actions,
            live2d_model=live2d_model,
            tts_engine=tts_engine,
            websocket_send=websocket_send,
            subtitle_text=subtitle_text,
        )
    return full_response


async def handle_audio_output(
    output: AudioOutput,
    websocket_send: WebSocketSend,
) -> str:
    """Process and send AudioOutput directly to the client"""
    full_response = ""
    async for audio_path, display_text, transcript, actions in output:
        full_response += transcript
        audio_payload = prepare_audio_payload(
            audio_path=audio_path,
            display_text=display_text,
            actions=actions.to_dict() if actions else None,
        )
        await websocket_send(json.dumps(audio_payload))
    return full_response


async def send_conversation_start_signals(websocket_send: WebSocketSend) -> None:
    """Send initial conversation signals"""
    await websocket_send(
        json.dumps(
            {
                "type": "control",
                "text": "conversation-chain-start",
            }
        )
    )
    await websocket_send(json.dumps({"type": "full-text", "text": "Thinking..."}))


async def process_user_input(
    user_input: Union[str, np.ndarray],
    asr_engine: ASRInterface,
    websocket_send: WebSocketSend,
) -> str:
    """Process user input, converting audio to text if needed"""
    if isinstance(user_input, np.ndarray):
        logger.info("Transcribing audio input...")
        input_text = await asr_engine.async_transcribe_np(user_input)
        await websocket_send(
            json.dumps({"type": "user-input-transcription", "text": input_text})
        )
        return input_text
    return user_input


async def finalize_conversation_turn(
    tts_manager: TTSTaskManager,
    websocket_send: WebSocketSend,
    client_uid: str,
    broadcast_ctx: Optional[BroadcastContext] = None,
) -> None:
    """Finalize a conversation turn"""
    if tts_manager.task_list:
        await asyncio.gather(*tts_manager.task_list)
        await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        response = await message_handler.wait_for_response(
            client_uid, "frontend-playback-complete"
        )

        if not response:
            logger.warning(f"No playback completion response from {client_uid}")
            return

    await websocket_send(json.dumps({"type": "force-new-message"}))

    if broadcast_ctx and broadcast_ctx.broadcast_func:
        await broadcast_ctx.broadcast_func(
            broadcast_ctx.group_members,
            {"type": "force-new-message"},
            broadcast_ctx.current_client_uid,
        )

    await send_conversation_end_signal(websocket_send, broadcast_ctx)


async def send_conversation_end_signal(
    websocket_send: WebSocketSend,
    broadcast_ctx: Optional[BroadcastContext],
    session_emoji: str = "😊",
) -> None:
    """Send conversation chain end signal"""
    chain_end_msg = {
        "type": "control",
        "text": "conversation-chain-end",
    }

    await websocket_send(json.dumps(chain_end_msg))

    if broadcast_ctx and broadcast_ctx.broadcast_func and broadcast_ctx.group_members:
        await broadcast_ctx.broadcast_func(
            broadcast_ctx.group_members,
            chain_end_msg,
        )

    logger.info(f"😎👍✅ Conversation Chain {session_emoji} completed!")


def cleanup_conversation(tts_manager: TTSTaskManager, session_emoji: str) -> None:
    """Clean up conversation resources"""
    tts_manager.clear()
    logger.debug(f"🧹 Clearing up conversation {session_emoji}.")


EMOJI_LIST = [
    "🐶",
    "🐱",
    "🐭",
    "🐹",
    "🐰",
    "🦊",
    "🐻",
    "🐼",
    "🐨",
    "🐯",
    "🦁",
    "🐮",
    "🐷",
    "🐸",
    "🐵",
    "🐔",
    "🐧",
    "🐦",
    "🐤",
    "🐣",
    "🐥",
    "🦆",
    "🦅",
    "🦉",
    "🦇",
    "🐺",
    "🐗",
    "🐴",
    "🦄",
    "🐝",
    "🌵",
    "🎄",
    "🌲",
    "🌳",
    "🌴",
    "🌱",
    "🌿",
    "☘️",
    "🍀",
    "🍂",
    "🍁",
    "🍄",
    "🌾",
    "💐",
    "🌹",
    "🌸",
    "🌛",
    "🌍",
    "⭐️",
    "🔥",
    "🌈",
    "🌩",
    "⛄️",
    "🎃",
    "🎄",
    "🎉",
    "🎏",
    "🎗",
    "🀄️",
    "🎭",
    "🎨",
    "🧵",
    "🪡",
    "🧶",
    "🥽",
    "🥼",
    "🦺",
    "👔",
    "👕",
    "👜",
    "👑",
]
