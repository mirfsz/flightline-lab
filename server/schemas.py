"""Public responses expose only coarse cells and explicitly fictional geometry."""

from typing import Literal

from pydantic import BaseModel, Field


class CoarseCell(BaseModel):
    cell_id: str
    label: str
    confidence_label: Literal["synthetic fit", "ambiguous synthetic fit"]


class EvidenceSummary(BaseModel):
    duration_seconds: float
    tonal_motion_candidates: int
    audio_quality: Literal["usable", "weak", "silent"]
    archive_coverage: str


class Spectrogram(BaseModel):
    width: int
    height: int
    values: list[list[float]]
    min_frequency_hz: float = 80.0
    max_frequency_hz: float = 1800.0


class LocalPoint(BaseModel):
    x_km: float
    y_km: float


class CellBounds(BaseModel):
    min_x_km: float
    min_y_km: float
    max_x_km: float
    max_y_km: float


class TrackPoint(LocalPoint):
    emission_seconds: float


class ClosestApproach(LocalPoint):
    emission_seconds: float
    predicted_arrival_seconds: float
    observed_transition_seconds: float | None
    timing_residual_seconds: float | None
    propagation_delay_seconds: float = Field(ge=0)


class MapCandidate(BaseModel):
    label: str
    cell_id: str
    supported: bool
    doppler_rmse_hz: float = Field(ge=0)
    cell_bounds: CellBounds
    microphone_area_center: LocalPoint
    microphone_uncertainty_radius_km: float = Field(ge=7.07)
    track_points: list[TrackPoint]
    closest_approach: ClosestApproach


class SyntheticEvidenceMap(BaseModel):
    coordinate_frame: Literal["fictional local kilometres"] = "fictional local kilometres"
    synthetic_only: Literal[True] = True
    candidates: list[MapCandidate]


class AnalysisResult(BaseModel):
    decision: Literal["coarse_region_supported", "inconclusive"]
    reason_codes: list[str]
    coarse_cells: list[CoarseCell]
    evidence_summary: EvidenceSummary
    spectrogram: Spectrogram
    limitations: list[str]
    synthetic_only: bool = True
    grid_resolution_km: float = Field(default=10.0, ge=10.0)
    evidence_map: SyntheticEvidenceMap | None = None


class HealthResult(BaseModel):
    status: str
    offline: bool = True
    ffmpeg_available: bool
    max_upload_mb: int
    max_duration_seconds: int
    stored_recordings: int = 0
