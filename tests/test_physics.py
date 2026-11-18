import numpy as np
import pytest

from server.physics import (SOUND_SPEED, SyntheticTrack, coarse_cell_id, doppler_ratio,
                            emission_time, received_time, source_range)


def test_doppler_sign_approaching_then_receding():
    track = SyntheticTrack(0, 10_000)
    arrival = received_time(track, np.array([-40.0, 0.0, 40.0]))
    ratios = doppler_ratio(track, arrival)
    assert ratios[0] > 1
    assert ratios[1] == pytest.approx(1)
    assert ratios[2] < 1


def test_sound_travel_delay_and_inverse():
    track = SyntheticTrack(10_000, 20_000)
    emitted = np.linspace(-50, 60, 20)
    arrival = received_time(track, emitted)
    np.testing.assert_allclose(arrival - emitted, source_range(track, emitted) / SOUND_SPEED)
    np.testing.assert_allclose(emission_time(track, arrival), emitted, atol=1e-7)
    assert np.all(arrival > emitted)


def test_coarsening_never_returns_sub_10_km_cells():
    assert coarse_cell_id(2, 2) == coarse_cell_id(9_999, 9_999)
    assert coarse_cell_id(10_001, 2) != coarse_cell_id(9_999, 2)
    assert coarse_cell_id(-1, -1) != coarse_cell_id(1, 1)
    with pytest.raises(ValueError):
        coarse_cell_id(0, 0, 1_000)


def test_supersonic_tracks_are_rejected():
    with pytest.raises(ValueError):
        doppler_ratio(SyntheticTrack(0, 10_000, speed_mps=400), np.array([0.0]))
