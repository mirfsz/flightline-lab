"""Temporary, size-bounded media decoding. Upload names never become file paths."""

from pathlib import Path
import shutil
import subprocess
import wave

import numpy as np
from scipy.signal import resample_poly

from server.signal import SAMPLE_RATE

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
MAX_DURATION_SECONDS = 90
DECODE_TIMEOUT_SECONDS = 30
ALLOWED_SUFFIXES = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".mp4", ".mov", ".webm"}


class MediaError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def read_pcm_wav(path: Path) -> np.ndarray:
    try:
        with wave.open(str(path), "rb") as reader:
            channels = reader.getnchannels()
            sample_rate = reader.getframerate()
            frame_count = reader.getnframes()
            if channels not in (1, 2) or not 8_000 <= sample_rate <= 96_000:
                raise MediaError("UNSUPPORTED_WAV", "Use mono/stereo WAV at 8–96 kHz, or install ffmpeg.")
            if frame_count > sample_rate * MAX_DURATION_SECONDS:
                raise MediaError("DURATION_LIMIT", "Recordings must be at most 90 seconds.")
            if reader.getsampwidth() != 2 or reader.getcomptype() != "NONE":
                raise MediaError("UNSUPPORTED_WAV", "Without ffmpeg, use uncompressed 16-bit PCM WAV.")
            raw = reader.readframes(frame_count)
    except (wave.Error, EOFError, OSError) as exc:
        raise MediaError("INVALID_MEDIA", "The file could not be decoded as PCM WAV.") from exc
    if not raw:
        raise MediaError("EMPTY_MEDIA", "The recording contains no audio samples.")
    if len(raw) % (2 * channels):
        raise MediaError("INVALID_MEDIA", "The audio data is truncated.")
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32).reshape(-1, channels).mean(axis=1) / 32768
    if sample_rate != SAMPLE_RATE:
        from math import gcd
        divisor = gcd(sample_rate, SAMPLE_RATE)
        samples = resample_poly(samples, SAMPLE_RATE // divisor, sample_rate // divisor)
    return samples


def decode_media(source: Path, directory: Path) -> np.ndarray:
    executable = shutil.which("ffmpeg")
    if executable is None:
        if source.suffix.lower() == ".wav":
            return read_pcm_wav(source)
        raise MediaError("FFMPEG_REQUIRED", "Install ffmpeg to decode video or compressed audio; PCM WAV works without it.")
    target = directory / "decoded.wav"
    command = [
        executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-threads", "1", "-protocol_whitelist", "file,pipe", "-i", str(source),
        "-map", "0:a:0", "-vn", "-t", str(MAX_DURATION_SECONDS + 1),
        "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        "-threads", "1", "-f", "wav", str(target),
    ]
    try:
        # stdout/stderr are discarded so hostile metadata cannot grow a capture buffer.
        completed = subprocess.run(command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=DECODE_TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as exc:
        raise MediaError("DECODE_TIMEOUT", "Media decoding exceeded the 30-second processing limit.") from exc
    except OSError as exc:
        raise MediaError("DECODE_FAILED", "The local ffmpeg process could not start.") from exc
    if completed.returncode or not target.exists():
        raise MediaError("INVALID_MEDIA", "No supported audio stream could be decoded from this file.")
    if target.stat().st_size > 2 * SAMPLE_RATE * (MAX_DURATION_SECONDS + 2) + 4096:
        raise MediaError("DECODE_OUTPUT_LIMIT", "Decoded audio exceeded the output limit.")
    return read_pcm_wav(target)
