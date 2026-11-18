import json

import numpy as np

from server.matcher import analyze_features
from server.physics import coarse_cell_id
from server.signal import SAMPLE_RATE, extract_features, synthetic_samples


def test_silence_is_inconclusive():
    result = analyze_features(extract_features(np.zeros(SAMPLE_RATE * 20)), synthetic=True)
    assert result.decision == "inconclusive"
    assert result.coarse_cells == []
    assert "SILENCE_OR_NEAR_SILENCE" in result.reason_codes
    assert result.evidence_summary.audio_quality == "silent"


def test_too_short_is_inconclusive():
    result = analyze_features(extract_features(synthetic_samples(5)), synthetic=True)
    assert result.decision == "inconclusive"
    assert "INSUFFICIENT_DURATION" in result.reason_codes


def test_synthetic_recovery_and_public_output_is_coarse():
    result = analyze_features(extract_features(synthetic_samples()), synthetic=True)
    assert result.decision == "coarse_region_supported"
    assert coarse_cell_id(0, 0) in [cell.cell_id for cell in result.coarse_cells]
    assert result.grid_resolution_km >= 10
    serialized = json.dumps(result.model_dump())
    assert "latitude" not in serialized
    assert "longitude" not in serialized
    assert "x_start_m" not in serialized
    assert "flight_id" not in serialized
    assert result.spectrogram.width <= 160
    assert result.spectrogram.height <= 56


def test_fixture_is_reproducible():
    np.testing.assert_array_equal(synthetic_samples(), synthetic_samples())


def test_stationary_tone_is_inconclusive():
    times = np.arange(20 * SAMPLE_RATE) / SAMPLE_RATE
    result = analyze_features(extract_features(0.5 * np.sin(2 * np.pi * 300 * times)), synthetic=True)
    assert result.decision == "inconclusive"
    assert "INSUFFICIENT_DOPPLER_VARIATION" in result.reason_codes


def test_uploads_never_claim_real_world_match():
    result = analyze_features(extract_features(synthetic_samples()), synthetic=False)
    assert result.decision == "inconclusive"
    assert result.coarse_cells == []
    assert "OFFLINE_ARCHIVE_UNAVAILABLE" in result.reason_codes
