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
# "[WinError 2] ... not found" and play NO sound. We bundle a static ffmpeg via
# imageio-ffmpeg so the default voice works out of the box on every platform.
def _setup_bundled_ffmpeg() -> None:
    """Point pydub at the bundled static ffmpeg (decode/encode)."""
    try:
        import imageio_ffmpeg

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # pragma: no cover - keep startup resilient
        logger.debug(f"imageio-ffmpeg unavailable, using system ffmpeg: {type(e).__name__}")
        return
    if not ffmpeg_exe or not os.path.exists(ffmpeg_exe):
        return
    AudioSegment.converter = ffmpeg_exe
    # Put the ffmpeg folder on PATH too, so a real ffprobe sitting next to it (or
    # a system one) is still discovered when present.
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if ffmpeg_dir and ffmpeg_dir not in path_parts:
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")


def _make_ffprobe_optional() -> None:
    """imageio-ffmpeg ships ffmpeg but NOT ffprobe. pydub's ``from_file`` probes
    the input with ``mediainfo_json`` -> ffprobe *before* converting; when ffprobe
    is missing this raises FileNotFoundError ([WinError 2]) and kills the whole
    reply with no sound. The probe is only an optimisation (it refines the output
    codec) — the bundled ffmpeg converts mp3->wav fine without it. So wrap it to
    degrade gracefully: on any probe failure return {} and let pydub fall back to
    plain ffmpeg defaults."""
    try:
        import pydub.audio_segment as _pas

        _orig_mediainfo_json = _pas.mediainfo_json

        def _safe_mediainfo_json(filepath, read_ahead_limit=-1):
            try:
                return _orig_mediainfo_json(filepath, read_ahead_limit=read_ahead_limit)
            except Exception as e:
                logger.debug(f"ffprobe unavailable, skipping media probe: {type(e).__name__}")
                return {}

        _pas.mediainfo_json = _safe_mediainfo_json
    except Exception as e:  # pragma: no cover - keep startup resilient
        logger.debug(f"could not patch pydub mediainfo_json: {type(e).__name__}")


_setup_bundled_ffmpeg()
_make_ffprobe_optional()


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
        # Pass the format explicitly (derived from the extension) so ffmpeg knows
        # the input container. The optional ffprobe probe is made non-fatal at
        # import (see _make_ffprobe_optional) so a missing ffprobe no longer
        # crashes the conversion on Windows.
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
