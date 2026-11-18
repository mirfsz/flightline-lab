"""Coarse fixed-grid Doppler comparison against imaginary fixture tracks."""

import numpy as np

from server.physics import coarse_cell_id, doppler_ratio, fixed_grid
from server.schemas import AnalysisResult, CoarseCell, EvidenceSummary
from server.signal import Features

LIMITATIONS = [
    "Research demonstration only; confidence labels are not calibrated probabilities.",
    "The offline fixture grid is imaginary and has no real flight archive coverage.",
    "A constant source tone, speed, altitude, sound speed, and stationary microphone are assumed.",
    "Wind, reflections, engine changes, unknown clock offsets, and overlapping sources can invalidate a fit.",
    "No exact coordinates, flight identities, or sub-10 km cells are returned.",
]


def analyze_features(features: Features, *, synthetic: bool) -> AnalysisResult:
    evidence = EvidenceSummary(
        duration_seconds=round(features.duration_seconds, 2),
        usable_passages=int(features.quality == "usable" and features.duration_seconds >= 12),
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
        limitations=LIMITATIONS,
    )
    if reasons:
        return result
    scored: list[tuple[float, object]] = []
    for track in fixed_grid():
        ratio = doppler_ratio(track, features.times)
        # Fit a nuisance emitted pitch, but retain the absolute received time axis.
        fundamental = float(np.dot(ratio, features.ridge_hz) / np.dot(ratio, ratio))
        if not 250 <= fundamental <= 350:
            continue
        error = float(np.sqrt(np.mean((fundamental * ratio - features.ridge_hz)**2)))
        scored.append((error, track))
    scored.sort(key=lambda row: row[0])
    if not scored or scored[0][0] > 7:
        result.reason_codes = ["NO_COHERENT_SYNTHETIC_FIT"]
        return result
    eligible = [row for row in scored if row[0] <= scored[0][0] + 2.5]
    if len(eligible) > 3:
        result.reason_codes = ["AMBIGUOUS_GRID_FIT"]
        return result
    result.decision = "coarse synthetic match"
    result.reason_codes = ["SYNTHETIC_FIXTURE_ONLY", "COARSE_GRID_FIT"]
    for index, (_, track) in enumerate(eligible):
        result.coarse_cells.append(CoarseCell(
            cell_id=coarse_cell_id(track.x_start_m, track.cross_track_m),
            label=f"Synthetic cell {coarse_cell_id(track.x_start_m, track.cross_track_m)} · 10 km grid",
            confidence_label="synthetic fit" if len(eligible) == 1 else "ambiguous synthetic fit",
        ))
    return result
