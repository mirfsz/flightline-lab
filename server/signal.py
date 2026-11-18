"""Bounded STFT, ridge extraction, and a deterministic consent-free fixture."""

from dataclasses import dataclass
import io
import wave

import numpy as np
from numpy.typing import NDArray
from scipy import signal as scipy_signal

from server.physics import SyntheticTrack, doppler_ratio, source_range, emission_time
from server.schemas import Spectrogram

SAMPLE_RATE = 8_000


@dataclass(frozen=True)
class Features:
    duration_seconds: float
    times: NDArray
    ridge_hz: NDArray
    ridge_strength: float
    quality: str
    spectrogram: Spectrogram


def extract_features(samples: NDArray, sample_rate: int = SAMPLE_RATE) -> Features:
    samples = np.asarray(samples, dtype=np.float64)
    duration = len(samples) / sample_rate
    if len(samples) < 1024:
        samples = np.pad(samples, (0, 1024 - len(samples)))
    rms = float(np.sqrt(np.mean(samples * samples)))
    frequencies, times, spectrum = scipy_signal.stft(
        samples, fs=sample_rate, nperseg=1024, noverlap=768, boundary=None
    )
    magnitudes = np.abs(spectrum)
    selected = (frequencies >= 80) & (frequencies <= 1800)
    band = magnitudes[selected]
    selected_frequencies = frequencies[selected]
    # The demonstration engine has a constant emitted fundamental near 300 Hz.
    # This narrow-band ridge is deliberately not advertised as an engine classifier.
    ridge_band = (frequencies >= 180) & (frequencies <= 700)
    ridge_magnitudes = magnitudes[ridge_band]
    ridge_indices = ridge_magnitudes.argmax(axis=0)
    ridge_hz = frequencies[ridge_band][ridge_indices]
    peaks = ridge_magnitudes.max(axis=0)
    baseline = np.median(ridge_magnitudes, axis=0) + 1e-10
    strength = float(np.median(peaks / baseline))
    quality = "silent" if rms < 0.0002 else ("usable" if strength >= 8 else "weak")
    # Bounded payload, about 9k numeric values maximum.
    time_indices = np.linspace(0, band.shape[1] - 1, min(160, band.shape[1])).astype(int)
    freq_indices = np.linspace(0, band.shape[0] - 1, min(56, band.shape[0])).astype(int)
    preview = band[np.ix_(freq_indices, time_indices)]
    decibels = 20 * np.log10(preview + 1e-10)
    ceiling = max(float(decibels.max()), -80.0)
    normalized = np.clip((decibels - (ceiling - 65)) / 65, 0, 1)
    if quality == "silent":
        normalized[:] = 0
    return Features(duration, times, ridge_hz, strength, quality,
                    Spectrogram(width=len(time_indices), height=len(freq_indices),
                                values=np.round(normalized, 3).tolist()))


def synthetic_samples(duration_seconds: float = 45.0, seed: int = 7,
                      track: SyntheticTrack | None = None) -> NDArray:
    if not 1 <= duration_seconds <= 90:
        raise ValueError("Fixture duration must be between 1 and 90 seconds")
    track = track or SyntheticTrack(0.0, 10_000.0)
    times = np.arange(int(duration_seconds * SAMPLE_RATE)) / SAMPLE_RATE
    observed_frequency = 300.0 * doppler_ratio(track, times)
    phase = 2 * np.pi * np.cumsum(observed_frequency) / SAMPLE_RATE
    distance = source_range(track, emission_time(track, times))
    envelope = np.clip(10_000 / distance, 0, 1)
    tone = np.sin(phase) + 0.35 * np.sin(2 * phase) + 0.15 * np.sin(3 * phase)
    noise = np.random.default_rng(seed).normal(0, 0.012, len(times))
    return (0.45 * envelope * tone + noise).astype(np.float32)


def wav_bytes(samples: NDArray) -> bytes:
    result = io.BytesIO()
    with wave.open(result, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return result.getvalue()
