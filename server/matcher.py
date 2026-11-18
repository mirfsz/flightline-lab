"""Coarse fixed-grid Doppler comparison against imaginary fixture tracks."""

import math

import numpy as np

from server.physics import SOUND_SPEED, ReceiverCandidate, coarse_cell_id, doppler_ratio, emission_time, fixed_grid
from server.schemas import (AnalysisResult, CellBounds, ClosestApproach, CoarseCell,
                            EvidenceSummary, LocalPoint, MapCandidate, SyntheticEvidenceMap, TrackPoint)
from server.signal import Features

LIMITATIONS = [
    "Research demonstration only; confidence labels are not calibrated probabilities.",
    "The offline fixture grid is imaginary and has no real flight archive coverage.",
    "A constant source tone, speed, altitude, sound speed, and stationary microphone are assumed.",
    "Wind, reflections, engine changes, unknown clock offsets, and overlapping sources can invalidate a fit.",
    "No exact coordinates, flight identities, or sub-10 km cells are returned.",
]


def map_candidate(features: Features, error: float, candidate: ReceiverCandidate,
                  *, supported: bool) -> MapCandidate:
    """Explain a toy grid hypothesis; none of this frame maps to the Earth."""
    track = candidate.relative_track()
    ratio = doppler_ratio(track, features.times)
    fundamental = float(np.dot(ratio, features.ridge_hz) / np.dot(ratio, ratio))
    # A downward crossing of the fitted emitted pitch is an observable proxy
    # for arrival of the closest-approach sound. No independent timing fit is claimed.
    crossings = np.flatnonzero((features.ridge_hz[:-1] >= fundamental)
                              & (features.ridge_hz[1:] < fundamental))
    closest_emission = candidate.x_m / track.speed_mps
    delay = math.hypot(track.cross_track_m, track.altitude_m) / SOUND_SPEED
    predicted_arrival = closest_emission + delay
    observed = None
    if len(crossings):
        crossing_times = []
        for index in crossings:
            fraction = ((features.ridge_hz[index] - fundamental)
                        / (features.ridge_hz[index] - features.ridge_hz[index + 1]))
            crossing_times.append(float(features.times[index] + fraction *
                                        (features.times[index + 1] - features.times[index])))
        observed = min(crossing_times, key=lambda time: abs(time - predicted_arrival))
    emitted = emission_time(track, np.array([features.times[0], features.times[-1]]))
    # Include the closest point even when a ranked alternative puts it outside
    # the recording window. Track timestamps are emission time, not audio time.
    track_times = np.linspace(min(float(emitted[0]), closest_emission) - 4,
                              max(float(emitted[-1]), closest_emission) + 4, 9)
    x, y = candidate.x_m / 1000, candidate.y_m / 1000
    cell_id = coarse_cell_id(candidate.x_m, candidate.y_m)
    return MapCandidate(
        label=f"Synthetic passage A / {cell_id}", cell_id=cell_id, supported=supported,
        doppler_rmse_hz=round(error, 2),
        cell_bounds=CellBounds(min_x_km=x, min_y_km=y, max_x_km=x + 10, max_y_km=y + 10),
        microphone_area_center=LocalPoint(x_km=x + 5, y_km=y + 5),
        # The disk encloses the entire reported cell; it is not a precision estimate.
        microphone_uncertainty_radius_km=math.sqrt(50),
        track_points=[TrackPoint(x_km=round(float(t) * track.speed_mps / 1000, 3),
                                 y_km=10, emission_seconds=round(float(t), 2)) for t in track_times],
        closest_approach=ClosestApproach(
            x_km=x, y_km=10, emission_seconds=round(closest_emission, 2),
            predicted_arrival_seconds=round(predicted_arrival, 2),
            observed_transition_seconds=round(observed, 2) if observed is not None else None,
            timing_residual_seconds=round(observed - predicted_arrival, 2) if observed is not None else None,
            propagation_delay_seconds=round(delay, 2)),
    )


def analyze_features(features: Features, *, synthetic: bool) -> AnalysisResult:
    variation_hz = float(np.percentile(features.ridge_hz, 90) - np.percentile(features.ridge_hz, 10))
    evidence = EvidenceSummary(
        duration_seconds=round(features.duration_seconds, 2),
        tonal_motion_candidates=int(
            features.quality == "usable" and features.duration_seconds >= 12 and variation_hz >= 20
        ),
        audio_quality=features.quality,
        archive_coverage="deterministic synthetic grid only" if synthetic else "unavailable offline",
    )
    reasons: list[str] = []
    if features.quality == "silent":
        reasons.append("SILENCE_OR_NEAR_SILENCE")
    elif features.quality != "usable":
        reasons.append("LOW_RIDGE_SIGNAL_TO_NOISE")
    if features.duration_seconds < 12:
        reasons.append("INSUFFICIENT_DURATION")
    if not synthetic:
        reasons.append("OFFLINE_ARCHIVE_UNAVAILABLE")
    result = AnalysisResult(
        decision="inconclusive", reason_codes=reasons, coarse_cells=[],
        evidence_summary=evidence, spectrogram=features.spectrogram,
        limitations=LIMITATIONS, synthetic_only=synthetic,
        evidence_kind="synthetic_fixture" if synthetic else "no_archive",
        audio_is_synthetic=True if synthetic else None,
    )
    if reasons:
        return result
    if variation_hz < 20:
        result.reason_codes = ["INSUFFICIENT_DOPPLER_VARIATION"]
        return result
    scored: list[tuple[float, ReceiverCandidate]] = []
    for candidate in fixed_grid():
        track = candidate.relative_track()
        ratio = doppler_ratio(track, features.times)
        # Fit a nuisance emitted pitch, but retain the absolute received time axis.
        fundamental = float(np.dot(ratio, features.ridge_hz) / np.dot(ratio, ratio))
        if not 250 <= fundamental <= 350:
            continue
        error = float(np.sqrt(np.mean((fundamental * ratio - features.ridge_hz)**2)))
        scored.append((error, candidate))
    scored.sort(key=lambda row: row[0])
    if not scored or scored[0][0] > 7:
        result.reason_codes = ["NO_COHERENT_SYNTHETIC_FIT"]
        return result
    eligible = [row for row in scored if row[0] <= scored[0][0] + 2.5]
    if len(eligible) > 3:
        result.reason_codes = ["AMBIGUOUS_GRID_FIT"]
        return result
    result.decision = "coarse_region_supported"
    result.reason_codes = ["SYNTHETIC_FIXTURE_ONLY", "COARSE_GRID_FIT"]
    for _, candidate in eligible:
        cell_id = coarse_cell_id(candidate.x_m, candidate.y_m)
        result.coarse_cells.append(CoarseCell(
            cell_id=cell_id,
            label=f"Synthetic cell {cell_id} · 10 km grid",
            confidence_label="synthetic fit" if len(eligible) == 1 else "ambiguous synthetic fit",
        ))
    result.evidence_map = SyntheticEvidenceMap(candidates=[
        map_candidate(features, error, candidate, supported=error <= scored[0][0] + 2.5)
        for error, candidate in scored[:3]
    ])
    return result
