"""Public response models deliberately exclude coordinates and flight identities."""

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


class AnalysisResult(BaseModel):
    decision: Literal["coarse_region_supported", "inconclusive"]
    reason_codes: list[str]
    coarse_cells: list[CoarseCell]
    evidence_summary: EvidenceSummary
    spectrogram: Spectrogram
    limitations: list[str]
    synthetic_only: bool = True
    grid_resolution_km: float = Field(default=10.0, ge=10.0)


class HealthResult(BaseModel):
    status: str
    offline: bool = True
    ffmpeg_available: bool
    max_upload_mb: int
    max_duration_seconds: int
    stored_recordings: int = 0
