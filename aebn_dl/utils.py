import logging
import subprocess
import shutil
import os
import re
import sys

from tqdm import tqdm

from .models import Scene

from .exceptions import FFmpegError


def remove_chars(text: str) -> str:
    """Remove characters from string"""
    for ch in ["#", "?", "!", ":", "<", ">", '"', "/", "\\", "|", "*"]:
        if ch in text:
            text = text.replace(ch, "")
    return text


def new_logger(name: str, log_level: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # Set the logger level to the lowest (DEBUG)

    formatter = logging.Formatter("%(asctime)s|%(levelname)s|%(message)s", datefmt="%H:%M:%S")

    # Console handler with user set level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.set_name("console_handler")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler with DEBUG level
    file_handler = logging.FileHandler(f"{name}.log")
    file_handler.setLevel(logging.DEBUG)
    file_handler.set_name("file_handler")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # https://stackoverflow.com/questions/6234405/
    def log_uncaught_exceptions(exctype, value, tb):
        logger.critical("Uncaught exception", exc_info=(exctype, value, tb))

    # Set the exception hook to log uncaught exceptions
    sys.excepthook = log_uncaught_exceptions
    return logger


def duration_to_seconds(duration: str) -> int:
    """Convert HH:MM:SS to seconds"""
    time_parts = list(map(int, duration.split(":")))
    time_parts.reverse()  # Reverse the list to start from seconds
    total_seconds = 0
    for i, part in enumerate(time_parts):
        if i == 0:  # Seconds
            total_seconds += part
        elif i == 1:  # Minutes
            total_seconds += part * 60
        elif i == 2:  # Hours
            total_seconds += part * 3600
    return total_seconds


def ffmpeg_mux_streams(stream_path_1: str, stream_path_2: str, output_path: str, silent: bool = False) -> None:
    """Mux two media streams with ffmpeg"""
    cmd = f'ffmpeg -i "{stream_path_1}" -i "{stream_path_2}" -y -c copy "{output_path}"'

    if silent:
        cmd += " -loglevel warning"

    out = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)

    if not out.returncode == 0:
        raise FFmpegError(out.stderr)


def natural_sort_key(s):
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r"(\d+)", s)]


def concat_segments(files: list[str], output_path: str, tqdm_desc: str, aggressive_cleaning: bool, silent: bool = False):
    """Concat segments into a single file"""
    _files = [files[0], *sorted(files[1:], key=natural_sort_key)]
    concat_progress = tqdm(files, desc=f"Joining {tqdm_desc}", disable=silent)
    with open(output_path, "wb") as f:
        for segment_file_path in _files:
            with open(segment_file_path, "rb") as segment_file:
                content = segment_file.read()
                segment_file.close()
                f.write(content)
                concat_progress.update()
            if aggressive_cleaning:
                os.remove(segment_file_path)
    concat_progress.close()


def is_valid_media(media_bytes: bytes) -> bool:
    """Check if media bytes are are read as valid media with fmmpeg"""
    cmd = "ffmpeg -f mp4 -i pipe:0 -f null -"

    # Use subprocess.Popen with PIPE to create a pipe for input
    process = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # Write the media bytes to the stdin of the FFmpeg process
    _, stderr_data = process.communicate(input=media_bytes)

    # Check if FFmpeg found any errors
    if b"Multiple frames in a packet" in stderr_data or b"Error" in stderr_data:
        return False  # Not Valid
    return True  # Valid


def ffmpeg_check() -> None:
    """Ensure ffmpeg is available in PATH"""
    if not shutil.which("ffmpeg"):
        raise FileNotFoundError("ffmpeg not found! Please add it to PATH.")
