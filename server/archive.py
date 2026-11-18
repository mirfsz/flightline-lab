"""Small immutable, anonymous regional packs; no network access at request time.

The public span is sparse ADS-B position evidence, not a flight archive with
complete regional coverage. Acoustic comparisons are illustrative coarse-cell
compatibility checks, never receiver-position estimation or identification.
"""

from datetime import datetime, timezone
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from server.physics import SOUND_SPEED
from server.schemas import (AnalysisResult, ArchiveMatch, CoarseCell, EvidenceSummary,
                            GeographicBounds, PublicEvidenceMap, PublicMapCandidate,
                            PublicTrackPoint)
from server.signal import Features, SAMPLE_RATE

PACK_DIRECTORY = Path(__file__).parent / "packs"
MAX_PACK_BYTES = 256 * 1024
MAX_PROPAGATION_SECONDS = 180
PUBLIC_LIMITATIONS = [
    "Only three public position observations across 24.007 seconds are installed; regional traffic coverage is incomplete.",
    "A compatible cell is a coarse model hypothesis, not a calibrated probability or a receiver location estimate.",
    "The public demo audio is generated synthetically from the observed trajectory; it is not an aircraft recording.",
    "Linear interpolation is used only between observations; no aircraft path is extrapolated.",
    "Observation times are public API capture times, not independently verified aircraft transmission times.",
    "A stationary receiver, constant source tone and sound speed, and no wind or reflections are assumed.",
    "Clock uncertainty, sparse observations, engine changes and other sources can invalidate compatibility.",
    "Only cells at least 10 km wide are returned; no receiver point or aircraft identity is exposed.",
]


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PackBounds(FrozenModel):
    south: float = Field(ge=-80, le=80)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-80, le=80)
    east: float = Field(ge=-180, le=180)


class Provenance(FrozenModel):
    source_name: str
    source_url: str
    captured_date_utc: str
    license: Literal["ODbL-1.0"]
    license_url: str
    attribution: str
    processing: str


class Observation(FrozenModel):
    captured_ms: int = Field(gt=0)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    alt_geom_ft: float = Field(ge=0, le=60000)
    gs_knots: float = Field(gt=0, le=600)
    track_deg: float = Field(ge=0, lt=360)


class RegionalPack(FrozenModel):
    format_version: Literal[1]
    pack_id: str = Field(pattern=r"^[a-z0-9-]+$")
    region_id: str
    region_label: str
    region_aliases: tuple[str, ...]
    date_utc: str
    grid_resolution_km: float = Field(ge=10)
    bounds: PackBounds
    provenance: Provenance
    passage_label: Literal["Anonymous passage A"]
    observations: tuple[Observation, ...] = Field(min_length=2, max_length=100)

    @model_validator(mode="after")
    def bounded_span(self):
        times = [point.captured_ms for point in self.observations]
        if times != sorted(set(times)) or times[-1] - times[0] > 90_000:
            raise ValueError("Packs require increasing observations spanning at most 90 seconds")
        if any(iso_time(point.captured_ms / 1000)[:10] != self.date_utc for point in self.observations):
            raise ValueError("Observations must belong to the pack UTC date")
        bounds = self.bounds
        if not bounds.south < bounds.north or not bounds.west < bounds.east:
            raise ValueError("Invalid region bounds")
        # Current format intentionally bounds work to sixteen 0.1-degree cells.
        if bounds.north - bounds.south > .400001 or bounds.east - bounds.west > .400001:
            raise ValueError("Regional pack bounds exceed sixteen cells")
        cell_width = 111.195 * .1 * math.cos(math.radians(max(abs(bounds.south), abs(bounds.north))))
        if cell_width < 10 or self.grid_resolution_km > cell_width:
            raise ValueError("0.1-degree cells must be at least 10 km wide at this latitude")
        for extent in (bounds.north - bounds.south, bounds.east - bounds.west):
            if not math.isclose(extent / .1, round(extent / .1), abs_tol=1e-8):
                raise ValueError("Region bounds must contain whole 0.1-degree cells")
        if self.provenance.captured_date_utc != self.date_utc:
            raise ValueError("Provenance capture date must match the pack UTC date")
        if any(not (bounds.south <= p.latitude <= bounds.north and bounds.west <= p.longitude <= bounds.east)
               for p in self.observations):
            raise ValueError("Observation lies outside region")
        return self


def iso_time(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def load_pack(path: Path) -> RegionalPack:
    if path.stat().st_size > MAX_PACK_BYTES:
        raise ValueError("Regional pack exceeds size limit")
    return RegionalPack.model_validate_json(path.read_bytes())


@lru_cache(maxsize=1)
def installed_packs() -> tuple[RegionalPack, ...]:
    paths = sorted(PACK_DIRECTORY.glob("*.json"))
    if len(paths) > 8:
        raise ValueError("At most eight small regional packs may be installed")
    return tuple(load_pack(path) for path in paths)


def demo_pack() -> RegionalPack:
    return next(pack for pack in installed_packs() if pack.region_id == "singapore")


def demo_metadata() -> dict:
    pack = demo_pack()
    return {"pack_id": pack.pack_id, "recording_time": iso_time(pack.observations[0].captured_ms / 1000 + 10),
            "search_region": pack.region_label, "time_uncertainty_minutes": 0,
            "duration_seconds": 20, "audio_is_synthetic": True,
            "wav_url": "/api/demo/demo.wav", "analyze_url": "/api/demo/analyze"}


def archive_coverage() -> dict:
    packs = []
    for pack in installed_packs():
        payload = pack.model_dump(mode="json")
        packs.append({"pack_id": pack.pack_id, "region_id": pack.region_id, "region_label": pack.region_label,
                      "region_aliases": pack.region_aliases, "date_utc": pack.date_utc,
                      "observation_start": iso_time(pack.observations[0].captured_ms / 1000),
                      "observation_end": iso_time(pack.observations[-1].captured_ms / 1000),
                      "observation_count": len(pack.observations),
                      "observation_span_seconds": (pack.observations[-1].captured_ms - pack.observations[0].captured_ms) / 1000,
                      "coverage_level": "short_public_observation_span", "complete_regional_coverage": False,
                      "bounds": payload["bounds"], "grid_resolution_km": pack.grid_resolution_km,
                      "provenance": payload["provenance"],
                      "content_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()})
    return {"format_version": 1, "offline": True, "packs": packs, "demo": demo_metadata(),
            "limitations": PUBLIC_LIMITATIONS}


def select_pack(recording_time: datetime, duration_seconds: float, uncertainty_minutes: float,
                search_region: str) -> tuple[RegionalPack | None, ArchiveMatch]:
    region = search_region.strip().casefold()
    regional = [pack for pack in installed_packs() if region in pack.region_aliases]
    if not regional:
        return None, ArchiveMatch(status="region_unavailable", message="No installed public pack covers the requested region. Use an installed region alias from /api/archive/coverage.")
    start = recording_time.timestamp() - uncertainty_minutes * 60
    end = recording_time.timestamp() + duration_seconds + uncertainty_minutes * 60
    for pack in regional:
        first = pack.observations[0].captured_ms / 1000
        last = pack.observations[-1].captured_ms / 1000
        if end >= first and start <= last + MAX_PROPAGATION_SECONDS:
            return pack, ArchiveMatch(status="installed_overlap", pack_id=pack.pack_id,
                                     observation_start=iso_time(first), observation_end=iso_time(last),
                                     attribution=pack.provenance.attribution,
                                     message="Time and region overlap a short installed public observation span; other traffic and dates are not covered.")
    return None, ArchiveMatch(status="time_unavailable", message="The requested time window does not overlap an installed public observation span in this region.")


def trajectory(pack: RegionalPack):
    points = pack.observations
    times = np.array([(point.captured_ms - points[0].captured_ms) / 1000 for point in points])
    lat0, lon0 = points[0].latitude, points[0].longitude
    positions = np.array([[(p.longitude - lon0) * 111195 * math.cos(math.radians(lat0)),
                           (p.latitude - lat0) * 111195, p.alt_geom_ft * .3048] for p in points])
    return times, positions


@lru_cache(maxsize=2048)
def arrival_profile(pack: RegionalPack, receiver_lat: float, receiver_lon: float):
    """Cache only installed public geometry, never upload metadata or samples."""
    times, positions = trajectory(pack)
    point0 = pack.observations[0]
    receiver = np.array([(receiver_lon - point0.longitude) * 111195 * math.cos(math.radians(point0.latitude)),
                         (receiver_lat - point0.latitude) * 111195, 0])
    emitted = np.linspace(times[0], times[-1], 1000)
    position = np.column_stack([np.interp(emitted, times, positions[:, axis]) for axis in range(3)])
    delta = position - receiver
    distance = np.linalg.norm(delta, axis=1)
    arrival = emitted + distance / SOUND_SPEED
    velocity = np.gradient(position, emitted, axis=0)
    radial = np.sum(velocity * delta, axis=1) / distance
    ratio = 1 / (1 + radial / SOUND_SPEED)
    arrival.setflags(write=False)
    ratio.setflags(write=False)
    return arrival, ratio


def received_ratios(pack: RegionalPack, receiver_lat: float, receiver_lon: float,
                    receiver_times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Interpolate observed positions and invert sound delay without extrapolation."""
    arrival, ratio = arrival_profile(pack, receiver_lat, receiver_lon)
    valid = (receiver_times >= arrival[0]) & (receiver_times <= arrival[-1])
    return np.interp(receiver_times, arrival, ratio), valid


def public_demo_samples() -> np.ndarray:
    pack = demo_pack()
    times = 10 + np.arange(20 * SAMPLE_RATE) / SAMPLE_RATE
    # A fixed internal simulator input, not an estimated or exposed receiver point.
    ratio, valid = received_ratios(pack, 1.25, 103.95, times)
    if not valid.all():
        raise ValueError("Demo audio exceeds observed trajectory support")
    phase = 2 * np.pi * np.cumsum(300 * ratio) / SAMPLE_RATE
    tone = np.sin(phase) + .25 * np.sin(2 * phase)
    return (.45 * tone + np.random.default_rng(19).normal(0, .004, len(times))).astype(np.float32)


def analyze_public(features: Features, recording_time: datetime, uncertainty_minutes: float,
                   search_region: str, *, audio_is_synthetic: bool | None = None) -> AnalysisResult:
    pack, coverage = select_pack(recording_time, features.duration_seconds, uncertainty_minutes, search_region)
    reasons = []
    if features.quality == "silent":
        reasons.append("SILENCE_OR_NEAR_SILENCE")
    elif features.quality != "usable":
        reasons.append("LOW_RIDGE_SIGNAL_TO_NOISE")
    if features.duration_seconds < 12:
        reasons.append("INSUFFICIENT_DURATION")
    if pack is None:
        reasons.extend(["OFFLINE_ARCHIVE_UNAVAILABLE", "ARCHIVE_" + coverage.status.upper()])
    result = AnalysisResult(
        decision="inconclusive", reason_codes=reasons, coarse_cells=[], synthetic_only=False,
        evidence_kind="public_observation" if pack else "no_archive", audio_is_synthetic=audio_is_synthetic,
        archive_match=coverage, spectrogram=features.spectrogram, limitations=PUBLIC_LIMITATIONS,
        grid_resolution_km=pack.grid_resolution_km if pack else 10,
        evidence_summary=EvidenceSummary(duration_seconds=round(features.duration_seconds, 2),
                                         tonal_motion_candidates=int(features.quality == "usable"),
                                         audio_quality=features.quality,
                                         archive_coverage=coverage.message))
    if reasons or pack is None:
        return result
    variation = float(np.percentile(features.ridge_hz, 90) - np.percentile(features.ridge_hz, 10))
    if variation < 3:
        result.reason_codes = ["INSUFFICIENT_DOPPLER_VARIATION"]
        return result
    relative_times = recording_time.timestamp() - pack.observations[0].captured_ms / 1000 + features.times
    # A bounded clock grid, constrained by stated uncertainty and observed span.
    # No fitted clock offset or sample receiver point is included in responses.
    uncertainty = uncertainty_minutes * 60
    span = (pack.observations[-1].captured_ms - pack.observations[0].captured_ms) / 1000
    lower = max(-uncertainty, -float(relative_times[0]))
    upper = min(uncertainty, span + MAX_PROPAGATION_SECONDS - float(relative_times[-1]))
    offsets = np.arange(math.ceil(lower / 2) * 2, upper + .001, 2)
    if lower <= 0 <= upper:
        offsets = np.unique(np.r_[0, offsets])
    scored = []
    for row in range(round((pack.bounds.north - pack.bounds.south) / .1)):
        for col in range(round((pack.bounds.east - pack.bounds.west) / .1)):
            south, west = pack.bounds.south + row * .1, pack.bounds.west + col * .1
            best = float("inf")
            # Test a fixed 3x3 cell quadrature; no continuous position optimizer.
            for dy in (.02, .05, .08):
                for dx in (.02, .05, .08):
                    for offset in offsets:
                        ratios, valid = received_ratios(pack, south + dy, west + dx, relative_times + offset)
                        if not valid.all():
                            continue
                        pitch = float(np.dot(ratios, features.ridge_hz) / np.dot(ratios, ratios))
                        if 180 <= pitch <= 700:
                            best = min(best, float(np.sqrt(np.mean((pitch * ratios - features.ridge_hz) ** 2))))
            if best <= 5:
                scored.append((best, row, col, south, west))
    scored.sort()
    if not scored:
        result.reason_codes = ["NO_COMPATIBLE_PUBLIC_CELL"]
        return result
    result.decision = "coarse_region_supported"
    result.reason_codes = ["PUBLIC_OBSERVATION_PACK", "COARSE_CELL_COMPATIBILITY_ONLY", "SHORT_OBSERVATION_SPAN"]
    candidates = []
    for error, row, col, south, west in scored:
        cell_id = f"{pack.region_id.upper()}-{row}-{col}"
        label = f"{pack.region_label} cell {row + 1}/{col + 1} · ≥10 km"
        result.coarse_cells.append(CoarseCell(cell_id=cell_id, label=label, confidence_label="compatible coarse cell"))
        candidates.append(PublicMapCandidate(label=pack.passage_label, cell_id=cell_id, doppler_rmse_hz=round(error, 2),
                                            cell_bounds=GeographicBounds(south=round(south, 1), west=round(west, 1),
                                                                        north=round(south + .1, 1), east=round(west + .1, 1))))
    result.evidence_map = PublicEvidenceMap(
        candidates=candidates,
        track_points=[PublicTrackPoint(latitude=round(p.latitude, 3), longitude=round(p.longitude, 3),
                                       observed_at=iso_time(p.captured_ms / 1000)) for p in pack.observations])
    return result
