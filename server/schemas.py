"""Public responses distinguish fictional geometry from anonymous observed paths."""

from typing import Literal

from pydantic import BaseModel, Field


class CoarseCell(BaseModel):
    cell_id: str
    label: str
    confidence_label: Literal["synthetic fit", "ambiguous synthetic fit", "compatible coarse cell"]


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


class GeographicBounds(BaseModel):
    south: float
    west: float
    north: float
    east: float


class PublicMapCandidate(BaseModel):
    label: str
    cell_id: str
    supported: bool = True
    doppler_rmse_hz: float = Field(ge=0)
    cell_bounds: GeographicBounds


class PublicTrackPoint(BaseModel):
    latitude: float
    longitude: float
    observed_at: str


class PublicEvidenceMap(BaseModel):
    coordinate_frame: Literal["geographic coarse cells"] = "geographic coarse cells"
    synthetic_only: Literal[False] = False
    passage_label: str = "Anonymous passage A"
    track_points: list[PublicTrackPoint]
    candidates: list[PublicMapCandidate]


class ArchiveMatch(BaseModel):
    status: Literal["installed_overlap", "region_unavailable", "time_unavailable", "not_requested"]
    message: str
    pack_id: str | None = None
    observation_start: str | None = None
    observation_end: str | None = None
    attribution: str | None = None


class AnalysisResult(BaseModel):
    decision: Literal["coarse_region_supported", "inconclusive"]
    reason_codes: list[str]
    coarse_cells: list[CoarseCell]
    evidence_summary: EvidenceSummary
    spectrogram: Spectrogram
    limitations: list[str]
    synthetic_only: bool = True
    evidence_kind: Literal["synthetic_fixture", "public_observation", "no_archive"] = "synthetic_fixture"
    audio_is_synthetic: bool | None = None
    archive_match: ArchiveMatch | None = None
    grid_resolution_km: float = Field(default=10.0, ge=10.0)
    evidence_map: SyntheticEvidenceMap | PublicEvidenceMap | None = None


class HealthResult(BaseModel):
    status: str
    offline: bool = True
    ffmpeg_available: bool
    max_upload_mb: int
    max_duration_seconds: int
    stored_recordings: int = 0
