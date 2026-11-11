"""Ticket 28b: tail block, stateful plume trail, marker and gap.

The spray block is fixed in size: length ``|v_abs| * dt``, width 3.4 m,
height 1.5 m, bottom on the box bottom.  Clusters are kept alive across frames
by :class:`spray.plume_state.PlumeState`, so the trail is continuous instead of
being rebuilt from scratch every frame.
"""

import numpy as np
import pytest

from spray.plume import PlumeConfig, _inside_box, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState

DT = 0.1
SPEED_KMH = 80.0
SPEED_MPS = SPEED_KMH / 3.6
TOKEN = "scene-tail-block"
BOX = np.array(
    [[23.2, 0.0, 0.899, 2.42, 6.83, 2.62, 0.0, SPEED_MPS, 0.0]],
    dtype=np.float32,
)


def _context(frame_index=0, velocity=None):
    return PlumeContext(
        scene_token=TOKEN,
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.array([0.0, 0.0, 1.8], dtype=np.float64),
        ego_speed_mps=SPEED_MPS,
        object_speed_mps=SPEED_MPS,
        wfh_mm=1.0,
        road_z_m=-0.411,
        object_velocity_ego_mps=velocity,
    )


def _empty_points():
    return np.zeros((0, 5), dtype=np.float32)


def _run_frames(count, state):
    for frame in range(count):
        inject_plume_stateful(
            _empty_points(),
            BOX,
            _context(frame),
            state,
            seed=100 + frame,
            token=TOKEN,
        )


def test_block_sits_behind_tail_with_fixed_width_and_fraction_height():
    state = PlumeState()

    inject_plume_stateful(
        _empty_points(), BOX, _context(), state, seed=1, token=TOKEN
    )

    clusters = state.alive(0)
    assert len(clusters) == 9

    block_len = SPEED_MPS * DT
    x_lo = 23.2 - 6.83 / 2.0 - block_len
    x_hi = 23.2 - 6.83 / 2.0
    height = 2.62
    box_bottom = 0.899 - height / 2.0
    frac_lo, frac_hi = PlumeConfig.tail_block_height_frac
    z_lo = box_bottom + frac_lo * height
    z_hi = box_bottom + frac_hi * height
    pos = np.array([cluster.pos for cluster in clusters])

    assert np.all(pos[:, 0] >= x_lo - 1e-6)
    assert np.all(pos[:, 0] <= x_hi + 1e-6)
    assert np.all(np.abs(pos[:, 1]) <= 3.4 / 2.0 + 1e-6)
    assert np.all(pos[:, 2] >= z_lo - 1e-6)
    assert np.all(pos[:, 2] <= z_hi + 1e-6)


def test_trail_keeps_clusters_alive_from_frame_two():
    state = PlumeState()

    alive = []
    for frame in range(10):
        inject_plume_stateful(
            _empty_points(),
            BOX,
            _context(frame),
            state,
            seed=200 + frame,
            token=TOKEN,
        )
        alive.append(len(state.all_alive()))

    assert alive[0] > 0
    assert all(count > 0 for count in alive[1:])
    assert alive[-1] > alive[0]


def test_gap_along_trajectory_median_below_one_metre():
    state = PlumeState()
    _run_frames(10, state)

    positions = np.array([cluster.pos for cluster in state.all_alive()])
    projected = np.sort(positions[:, 0])
    gaps = np.diff(projected)
    gap_p50 = float(np.median(gaps))

    print(f"gap_p50_m={gap_p50:.4f}")
    assert gap_p50 < 1.0


def test_no_injected_point_lies_inside_the_body_box():
    state = PlumeState()

    result = inject_plume_stateful(
        np.zeros((1, 5), dtype=np.float32),
        BOX,
        _context(),
        state,
        seed=3,
        token=TOKEN,
    )

    inside = _inside_box(result.injected, BOX[0], PlumeConfig().box_margin_m)
    assert not inside.any()
    assert result.stats.rejected_box >= 0


def test_probability_is_capped_at_one_on_birth_frame():
    state = PlumeState()
    center = np.array([18.67, 0.0, 0.34], dtype=np.float64)
    extents = np.array([1.11, 1.7, 0.75], dtype=np.float64)

    created = state.spawn(
        _context(),
        object_id=0,
        rng=np.random.default_rng(0),
        dt=DT,
        center=center,
        extents=extents,
    )

    assert created
    for cluster in created:
        assert cluster.age == pytest.approx(-DT)
        assert 0.0 < cluster.probability() <= 1.0


def test_marker_prints_one_line_with_seven_keys(capsys):
    state = PlumeState()

    inject_plume_stateful(
        _empty_points(),
        BOX,
        _context(frame_index=4),
        state,
        seed=7,
        token=TOKEN,
    )

    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("PLUME_STATE")
    ]
    assert len(lines) == 1

    fields = dict(part.split("=", 1) for part in lines[0].split()[1:])
    assert set(fields) == {
        "scene",
        "frame",
        "spawned",
        "alive",
        "expired",
        "capped",
        "assumed",
    }
    assert fields["scene"] == TOKEN
    assert fields["frame"] == "4"
    assert fields["assumed"] == "1"
