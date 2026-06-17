from typing import Union, List, Dict, Any, Optional
import asyncio
import json
from loguru import logger
import numpy as np

from .conversation_utils import (
    create_batch_input,
    process_agent_output,
    send_conversation_start_signals,
    process_user_input,
    finalize_conversation_turn,
    cleanup_conversation,
    EMOJI_LIST,
)
from .types import WebSocketSend
from .tts_manager import TTSTaskManager
from ..chat_history_manager import store_message
from ..service_context import ServiceContext

# Import necessary types from agent outputs
from ..agent.output_types import SentenceOutput, AudioOutput

# 保存背景核心記憶整理 task 的 reference，避免被 GC
_BG_MEMORY_TASKS: set = set()

# Per-session turn counter for consolidation throttling. Keyed by
# (conf_uid, client_uid) so each character + client tracks its own cadence.
# In-memory only (resets on restart -> interval cycle restarts, acceptable).
# One int per active client_uid -> negligible memory; cleared in cleanup below.
_TURN_COUNTS: "dict[tuple[str, str], int]" = {}


async def process_single_conversation(
    context: ServiceContext,
    websocket_send: WebSocketSend,
    client_uid: str,
    user_input: Union[str, np.ndarray],
    images: Optional[List[Dict[str, Any]]] = None,
    session_emoji: str = np.random.choice(EMOJI_LIST),
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    """Process a single-user conversation turn

    Args:
        context: Service context containing all configurations and engines
        websocket_send: WebSocket send function
        client_uid: Client unique identifier
        user_input: Text or audio input from user
        images: Optional list of image data
        session_emoji: Emoji identifier for the conversation
        metadata: Optional metadata for special processing flags

    Returns:
        str: Complete response text
    """
    # Create TTSTaskManager for this conversation
    tts_manager = TTSTaskManager()
    full_response = ""  # Initialize full_response here

    try:
        # Send initial signals
        await send_conversation_start_signals(websocket_send)
        logger.info(f"New Conversation Chain {session_emoji} started!")

        # Process user input
        input_text = await process_user_input(
            user_input, context.asr_engine, websocket_send
        )

        # Create batch input
        batch_input = create_batch_input(
            input_text=input_text,
            images=images,
            from_name=context.character_config.human_name,
            metadata=metadata,
        )

        # Store user message (check if we should skip storing to history)
        skip_history = metadata and metadata.get("skip_history", False)
        if context.history_uid and not skip_history:
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="human",
                content=input_text,
                name=context.character_config.human_name,
            )

        if skip_history:
            logger.debug("Skipping storing user input to history (proactive speak)")

        logger.info(f"User input: {input_text}")
        if images:
            logger.info(f"With {len(images)} images")

        # 睡眠勿擾（只看真人發話，不看主動觸發）。見 quiet_mode.py
        # 規則：說「晚安」→ 進勿擾、暫停主動說話；之後使用者「下一次主動搭話」（任何非空訊息）
        #       就自動恢復，不必特地說早安。
        try:
            from ..quiet_mode import set_quiet, is_quiet

            _is_proactive = bool(metadata and metadata.get("proactive_speak"))
            if not _is_proactive and isinstance(input_text, str) and input_text.strip():
                _conf = context.character_config.conf_uid
                if "晚安" in input_text:
                    set_quiet(_conf, True)
                elif is_quiet(_conf):
                    set_quiet(_conf, False)  # 醒了，第一句話就恢復
        except Exception as _q_e:
            logger.warning(f"[quiet_mode] toggle failed: {_q_e}")

        # 對話前刷新核心記憶到 system prompt（phase 1.5）：
        # agent_engine 在 server 開機時烤死 system prompt、新連線只 pass by reference 不重讀，
        # 導致背景 consolidation 寫入的新記憶要等重啟才生效。這裡在每輪對話前重讀 core_memory.md，
        # 只有記憶真的變了（或這個 session context 第一次跑）才重建 prompt 並 set_system，
        # 讓「越聊越認識你」免重啟即時生效，又不動到 agent 的對話歷史。見 MEMORY_SYSTEM_DESIGN.md
        # 長期記憶關閉時跳過 phase-1.5 重注入（construct_system_prompt 本身也已 gate，
        # 這裡短路避免無謂重建 prompt）。
        try:
            from ..memory_core import load_core_memory

            _mem_on = getattr(
                context.character_config, "long_term_memory_enabled", True
            )
            agent = context.agent_engine
            if _mem_on and hasattr(agent, "set_system"):
                fresh_mem = load_core_memory(context.character_config.conf_uid)
                if fresh_mem != getattr(context, "_core_mem_injected", None):
                    refreshed_prompt = await context.construct_system_prompt(
                        context.character_config.persona_prompt
                    )
                    agent.set_system(refreshed_prompt)
                    context._core_mem_injected = fresh_mem
                    logger.info(
                        "[core_memory] system prompt refreshed with latest core memory"
                    )
        except Exception as _refresh_e:
            logger.warning(f"[core_memory] refresh failed: {_refresh_e}")

        # 深度回憶（opt-in 全歷史 FTS5 檢索，預設關閉）：開啟時，用這輪使用者輸入去搜
        # 這個角色「全部過去對話」，把 top-K 相關片段「額外」附到 system prompt（核心記憶照舊）。
        # 完全 fail-soft：任何錯誤都當沒命中、照常對話。關閉時這段完全短路、行為與原本逐位元組相同。
        # 因為 FTS 結果每輪不同，開啟時必須「每輪」重設 system prompt（不像核心記憶只在變動時重設），
        # 並把 _core_mem_injected 記號清掉，讓之後關閉 FTS 的那一輪能重新同步乾淨的核心記憶 prompt。
        try:
            _fts_on = getattr(
                context.character_config, "fts_memory_enabled", False
            )
            agent = context.agent_engine
            if (
                _fts_on
                and hasattr(agent, "set_system")
                and isinstance(input_text, str)
                and input_text.strip()
            ):
                from .. import memory_fts

                _fts_k = getattr(context.character_config, "fts_memory_top_k", 3)
                snippets = memory_fts.search(
                    context.character_config.conf_uid, input_text, k=_fts_k
                )
                if snippets:
                    base_prompt = await context.construct_system_prompt(
                        context.character_config.persona_prompt
                    )
                    retrieval_block = (
                        f"\n\n{memory_fts.RETRIEVAL_LABEL}"
                        "（僅供參考，未必準確；若與當下無關就忽略）\n"
                        + "\n".join(snippets)
                    )
                    agent.set_system(base_prompt + retrieval_block)
                    # FTS 改了 prompt -> 清核心記憶記號，逼下一個 no-FTS turn 重新同步。
                    context._core_mem_injected = None
                    logger.info(
                        f"[fts] injected {len(snippets)} past-conversation snippet(s)"
                    )
        except Exception as _fts_e:
            logger.warning(f"[fts] retrieval/injection failed: {_fts_e}")

        try:
            # agent.chat yields Union[SentenceOutput, Dict[str, Any]]
            agent_output_stream = context.agent_engine.chat(batch_input)

            async for output_item in agent_output_stream:
                if (
                    isinstance(output_item, dict)
                    and output_item.get("type") == "tool_call_status"
                ):
                    # Handle tool status event: send WebSocket message
                    output_item["name"] = context.character_config.character_name
                    logger.debug(f"Sending tool status update: {output_item}")

                    await websocket_send(json.dumps(output_item))

                elif isinstance(output_item, (SentenceOutput, AudioOutput)):
                    # Handle SentenceOutput or AudioOutput
                    response_part = await process_agent_output(
                        output=output_item,
                        character_config=context.character_config,
                        live2d_model=context.live2d_model,
                        tts_engine=context.tts_engine,
                        websocket_send=websocket_send,  # Pass websocket_send for audio/tts messages
                        tts_manager=tts_manager,
                        translate_engine=context.translate_engine,
                        subtitle_translate_engine=context.subtitle_translate_engine,
                    )
                    # Ensure response_part is treated as a string before concatenation
                    response_part_str = (
                        str(response_part) if response_part is not None else ""
                    )
                    full_response += response_part_str  # Accumulate text response
                else:
                    logger.warning(
                        f"Received unexpected item type from agent chat stream: {type(output_item)}"
                    )
                    logger.debug(f"Unexpected item content: {output_item}")

        except Exception as e:
            logger.exception(
                f"Error processing agent response stream: {e}"
            )  # Log with stack trace
            await websocket_send(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error processing agent response: {str(e)}",
                    }
                )
            )
            # full_response will contain partial response before error
        # --- End processing agent response ---

        # Wait for any pending TTS tasks
        if tts_manager.task_list:
            await asyncio.gather(*tts_manager.task_list)
            await websocket_send(json.dumps({"type": "backend-synth-complete"}))

        await finalize_conversation_turn(
            tts_manager=tts_manager,
            websocket_send=websocket_send,
            client_uid=client_uid,
        )

        if context.history_uid and full_response:  # Check full_response before storing
            store_message(
                conf_uid=context.character_config.conf_uid,
                history_uid=context.history_uid,
                role="ai",
                content=full_response,
                name=context.character_config.character_name
                or context.character_config.conf_name,
                avatar=context.character_config.avatar,
            )
            logger.info(f"AI response: {full_response}")

        # 對話一輪後背景整理核心記憶（fire-and-forget，不阻塞使用者）。見 MEMORY_SYSTEM_DESIGN.md
        # 長期記憶關閉時（long_term_memory_enabled=False）跳過整理，連背景 task 都不建。
        # 節流：memory_consolidation_interval 控制每幾輪才整理一次（1=每輪、預設、行為不變；
        # 3/5 給弱機/本地模型省一半以上「整理用」的 LLM 呼叫）。用 per-session 計數器，
        # 只有 turn % interval == 0 那一輪才排整理 task。整段 fail-soft：計數器出錯絕不弄壞這輪對話。
        try:
            from ..memory_core import consolidate_core_memory, _clamp_interval

            _llm = context.character_config.agent_config.llm_configs.openai_compatible_llm
            _mem_on = getattr(
                context.character_config, "long_term_memory_enabled", True
            )
            if _mem_on and isinstance(input_text, str) and input_text.strip():
                _conf_uid = context.character_config.conf_uid
                _interval = _clamp_interval(
                    getattr(
                        context.character_config, "memory_consolidation_interval", 1
                    )
                )
                _key = (str(_conf_uid), str(client_uid))
                _n = _TURN_COUNTS.get(_key, 0) + 1
                _TURN_COUNTS[_key] = _n
                if _n % _interval == 0:
                    _cap = getattr(
                        context.character_config, "core_memory_max_chars", 1500
                    )
                    _t = asyncio.create_task(
                        consolidate_core_memory(
                            _conf_uid,
                            input_text,
                            full_response,
                            _llm.base_url,
                            _llm.model,
                            cap=_cap,
                            api_key=_llm.llm_api_key,
                        )
                    )
                    # 保存 reference 避免 fire-and-forget task 被 GC（Python asyncio 已知坑）
                    _BG_MEMORY_TASKS.add(_t)
                    _t.add_done_callback(_BG_MEMORY_TASKS.discard)
                else:
                    logger.debug(
                        f"[core_memory] consolidation skipped "
                        f"(turn {_n}, every {_interval})"
                    )
        except Exception as _mem_e:
            logger.warning(f"[core_memory] schedule failed: {_mem_e}")

        return full_response  # Return accumulated full_response

    except asyncio.CancelledError:
        logger.info(f"🤡👍 Conversation {session_emoji} cancelled because interrupted.")
        raise
    except Exception as e:
        logger.error(f"Error in conversation chain: {e}")
        await websocket_send(
            json.dumps({"type": "error", "message": f"Conversation error: {str(e)}"})
        )
        raise
    finally:
        cleanup_conversation(tts_manager, session_emoji)
