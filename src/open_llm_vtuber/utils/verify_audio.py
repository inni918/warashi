import shutil
from loguru import logger


def verify_audio(lang):
    if shutil.which("ffmpeg") is not None:
        if lang == "zh":
            logger.warning("警告:此系统未安装ffmpeg。音频质量可能会下降。")
        else:
            logger.warning("Warning: ffmpeg is not installed on this system. Audio may be degraded")
    if shutil.which("ffprobe") is not None:
        if lang == "zh":
            logger.warning("警告:此系统未安装ffprobe。音频质量可能会下降。")
        else:
            logger.warning("Warning: ffprobe is not installed on this system. Audio may be degraded")