import os
import base64
from pydub import AudioSegment
from pydub.utils import make_chunks
from loguru import logger
from ..agent.output_types import Actions
from ..agent.output_types import DisplayText

# pydub shells out to an external ffmpeg to decode/encode audio. Non-technical
# users (especially on Windows) usually don't have ffmpeg on PATH, so the default
# edge-tts voice — which produces an mp3 — would fail to convert to wav with
# "[WinError 2] ... ffmpeg not found" and play NO sound. Bundle a static ffmpeg
# via imageio-ffmpeg so the default voice works out of the box on all platforms.
# Falls back silently to whatever ffmpeg is on PATH if the bundle is unavailable.
try:
    import imageio_ffmpeg

    _bundled_ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    if _bundled_ffmpeg and os.path.exists(_bundled_ffmpeg):
        AudioSegment.converter = _bundled_ffmpeg
except Exception as _e:  # pragma: no cover - best-effort, keep startup resilient
    logger.debug(f"imageio-ffmpeg unavailable, using system ffmpeg: {type(_e).__name__}")


def _get_volume_by_chunks(audio: AudioSegment, chunk_length_ms: int) -> list:
    """
    Calculate the normalized volume (RMS) for each chunk of the audio.

    Parameters:
        audio (AudioSegment): The audio segment to process.
        chunk_length_ms (int): The length of each audio chunk in milliseconds.

    Returns:
        list: Normalized volumes for each chunk.
    """
    chunks = make_chunks(audio, chunk_length_ms)
    volumes = [chunk.rms for chunk in chunks]
    max_volume = max(volumes)
    if max_volume == 0:
        raise ValueError("Audio is empty or all zero.")
    return [volume / max_volume for volume in volumes]


def prepare_audio_payload(
    audio_path: str | None,
    chunk_length_ms: int = 20,
    display_text: DisplayText = None,
    actions: Actions = None,
    forwarded: bool = False,
    subtitle_text: str | None = None,
) -> dict[str, any]:
    """
    Prepares the audio payload for sending to a broadcast endpoint.
    If audio_path is None, returns a payload with audio=None for silent display.

    Parameters:
        audio_path (str | None): The path to the audio file to be processed, or None for silent display
        chunk_length_ms (int): The length of each audio chunk in milliseconds
        display_text (DisplayText, optional): Text to be displayed with the audio
        actions (Actions, optional): Actions associated with the audio
        subtitle_text (str | None, optional): Display-only translated subtitle. When
            provided it is carried as a separate ``subtitle_text`` field; the frontend
            shows it ONLY for the on-screen subtitle. ``display_text.text`` (the
            canonical reply R) is left untouched so memory/history stay on R.

    Returns:
        dict: The audio payload to be sent
    """
    if isinstance(display_text, DisplayText):
        display_text = display_text.to_dict()

    if not audio_path:
        # Return payload for silent display
        return {
            "type": "audio",
            "audio": None,
            "volumes": [],
            "slice_length": chunk_length_ms,
            "display_text": display_text,
            "subtitle_text": subtitle_text,
            "actions": actions.to_dict() if actions else None,
            "forwarded": forwarded,
        }

    try:
        # Pass the format explicitly (derived from the extension) so pydub does
        # NOT need ffprobe for detection — imageio-ffmpeg ships ffmpeg but not
        # ffprobe, so format auto-detection would otherwise fail on Windows.
        _fmt = os.path.splitext(audio_path)[1].lstrip(".").lower() or None
        audio = AudioSegment.from_file(audio_path, format=_fmt)
        audio_bytes = audio.export(format="wav").read()
    except Exception as e:
        raise ValueError(
            f"Error loading or converting generated audio file to wav file '{audio_path}': {e}"
        )
    audio_base64 = base64.b64encode(audio_bytes).decode("utf-8")
    volumes = _get_volume_by_chunks(audio, chunk_length_ms)

    payload = {
        "type": "audio",
        "audio": audio_base64,
        "volumes": volumes,
        "slice_length": chunk_length_ms,
        "display_text": display_text,
        "subtitle_text": subtitle_text,
        "actions": actions.to_dict() if actions else None,
        "forwarded": forwarded,
    }

    return payload


# Example usage:
# payload, duration = prepare_audio_payload("path/to/audio.mp3", display_text="Hello", expression_list=[0,1,2])
