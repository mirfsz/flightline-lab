"""Small, explicit acoustic model for synthetic hypotheses only.

Internal Cartesian distances describe an imaginary scene, never a geographic map.
The observer is stationary at the origin. Positive radial speed means receding.
"""

from dataclasses import dataclass
import math

import numpy as np
from numpy.typing import NDArray

SOUND_SPEED = 343.0
GRID_METERS = 10_000.0


@dataclass(frozen=True)
class SyntheticTrack:
    x_start_m: float
    cross_track_m: float
    altitude_m: float = 3_000.0
    speed_mps: float = 225.0


@dataclass(frozen=True)
class ReceiverCandidate:
    """A coarse listener cell tested against one fixed imaginary flight."""

    x_m: float
    y_m: float

    def relative_track(self) -> SyntheticTrack:
        # The fixed imaginary flight starts at (0, 10 km) and moves east.
        # Re-centering it on a candidate receiver preserves the acoustic model
        # while keeping the reported cell tied to the listener, not the aircraft.
        return SyntheticTrack(-self.x_m, 10_000.0 - self.y_m)


def source_range(track: SyntheticTrack, emission_time: NDArray) -> NDArray:
    x = track.x_start_m + track.speed_mps * emission_time
    return np.sqrt(x * x + track.cross_track_m**2 + track.altitude_m**2)


def received_time(track: SyntheticTrack, emission_time: NDArray) -> NDArray:
    return emission_time + source_range(track, emission_time) / SOUND_SPEED


def emission_time(track: SyntheticTrack, receiver_time: NDArray) -> NDArray:
    """Invert arrival time by Newton iteration for a subsonic constant track."""
    if not 0 <= track.speed_mps < SOUND_SPEED:
        raise ValueError("Synthetic tracks must be subsonic")
    estimate = np.asarray(receiver_time, dtype=float).copy()
    for _ in range(24):
        distance = source_range(track, estimate)
        x = track.x_start_m + track.speed_mps * estimate
        radial_speed = track.speed_mps * x / distance
        residual = estimate + distance / SOUND_SPEED - receiver_time
        estimate -= residual / (1.0 + radial_speed / SOUND_SPEED)
    return estimate


def doppler_ratio(track: SyntheticTrack, receiver_time: NDArray) -> NDArray:
    emitted = emission_time(track, receiver_time)
    distance = source_range(track, emitted)
    radial_speed = track.speed_mps * (track.x_start_m + track.speed_mps * emitted) / distance
    return SOUND_SPEED / (SOUND_SPEED + radial_speed)


def coarse_cell_id(x_m: float, y_m: float, cell_size_m: float = GRID_METERS) -> str:
    if cell_size_m < GRID_METERS:
        raise ValueError("Cells smaller than 10 km are not supported")
    return f"S{math.floor(x_m / cell_size_m) + 20:02d}-{math.floor(y_m / cell_size_m) + 20:02d}"


def fixed_grid() -> list[ReceiverCandidate]:
    # Candidate listeners in a private imaginary coordinate frame. Restricting
    # the toy search south of the flight avoids the one-pass mirror solution.
    return [ReceiverCandidate(float(x), float(y))
            for x in (-20_000, -10_000, 0, 10_000, 20_000)
            for y in (-20_000, -10_000, 0)]
