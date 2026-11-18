import json

import numpy as np

from server.matcher import analyze_features
from server.physics import SOUND_SPEED, coarse_cell_id
from server.signal import SAMPLE_RATE, extract_features, synthetic_samples


def test_silence_is_inconclusive():
    result = analyze_features(extract_features(np.zeros(SAMPLE_RATE * 20)), synthetic=True)
    assert result.decision == "inconclusive"
    assert result.coarse_cells == []
    assert "SILENCE_OR_NEAR_SILENCE" in result.reason_codes
    assert result.evidence_summary.audio_quality == "silent"
    assert result.evidence_map is None


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
    assert result.evidence_map is None
    assert result.synthetic_only is False


def test_synthetic_evidence_map_geometry_and_timing():
    result = analyze_features(extract_features(synthetic_samples()), synthetic=True)
    evidence_map = result.evidence_map
    assert evidence_map is not None
    assert evidence_map.synthetic_only is True
    assert evidence_map.coordinate_frame == "fictional local kilometres"
    assert len(evidence_map.candidates) == 3
    errors = [candidate.doppler_rmse_hz for candidate in evidence_map.candidates]
    assert errors == sorted(errors)
    supported_ids = {cell.cell_id for cell in result.coarse_cells}
    for candidate in evidence_map.candidates:
        assert candidate.label.startswith("Synthetic passage A /")
        assert candidate.supported == (candidate.cell_id in supported_ids)
        bounds = candidate.cell_bounds
        assert bounds.max_x_km - bounds.min_x_km == 10
        assert bounds.max_y_km - bounds.min_y_km == 10
        center = candidate.microphone_area_center
        for x in (bounds.min_x_km, bounds.max_x_km):
            for y in (bounds.min_y_km, bounds.max_y_km):
                assert np.hypot(x - center.x_km, y - center.y_km) <= candidate.microphone_uncertainty_radius_km + 1e-9
        assert len(candidate.track_points) == 9
        assert all(point.y_km == 10 for point in candidate.track_points)
        times = [point.emission_seconds for point in candidate.track_points]
        assert times == sorted(times)
        event = candidate.closest_approach
        assert abs(event.predicted_arrival_seconds - event.emission_seconds - event.propagation_delay_seconds) <= .011
        if event.observed_transition_seconds is None:
            assert event.timing_residual_seconds is None
        else:
            assert event.timing_residual_seconds is not None
            assert abs(event.timing_residual_seconds - (event.observed_transition_seconds - event.predicted_arrival_seconds)) <= .011
    best = evidence_map.candidates[0]
    assert best.cell_id == coarse_cell_id(0, 0)
    assert abs(best.closest_approach.propagation_delay_seconds - np.hypot(10_000, 3_000) / SOUND_SPEED) < .01
    assert best.closest_approach.timing_residual_seconds is not None
    assert abs(best.closest_approach.timing_residual_seconds) < 1
    assert any(candidate.closest_approach.observed_transition_seconds is None for candidate in evidence_map.candidates)


def test_map_is_deterministic_and_never_added_to_inconclusive_output():
    features = extract_features(synthetic_samples())
    first = analyze_features(features, synthetic=True)
    second = analyze_features(features, synthetic=True)
    assert first.evidence_map == second.evidence_map
    short = analyze_features(extract_features(synthetic_samples(5)), synthetic=True)
    assert short.decision == "inconclusive"
    assert short.evidence_map is None
