"""Ticket 28b: tail block, stateful plume trail, marker and gap.

The spray block is fixed in size: length ``|v_abs| * dt``, width 3.4 m,
height 5–92 % of the box height above the box bottom.  Clusters are kept alive
across frames by :class:`spray.plume_state.PlumeState`, so the trail is
continuous instead of being rebuilt from scratch every frame.

``BOX`` uses the adapter convention (``spray/sspp_adapter.py:117,141``):
``box[2]`` is the box **bottom**, ``box[3]`` the length along the yaw axis and
``box[4]`` the width across it.
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
BOX_HEIGHT = 2.62
BOX = np.array(
    [
        [
            23.2,
            0.0,
            0.899 - BOX_HEIGHT / 2.0,
            6.83,
            2.42,
            BOX_HEIGHT,
            0.0,
            SPEED_MPS,
            0.0,
        ]
    ],
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


def test_spawn_box_matches_the_static_calibration_box():
    """QĐ7 2026-11-19: cụm sinh ra nằm trong hộp calibration static.

    Hộp: sâu 20 m sau mặt đuôi (BOX x=23,2 m, dài 6,83 m), ngang W=3,4 m,
    cao H=1,5 m tính từ **mặt đường** (`road_z_m`). Thay block
    `|v|·dt` × `tail_block_height_frac` cũ — hai tham số nguồn SSPP, R2 audit
    đánh PHẢI BỎ. Test cũ khoá hình học cũ nên được thay, không nới lỏng.
    """
    state = PlumeState()

    clusters = []
    for frame in range(20):
        inject_plume_stateful(
            _empty_points(), BOX, _context(frame), state, seed=1 + frame, token=TOKEN
        )
        clusters = [c for c in state.alive(0) if c.age < 0.0]
        if clusters:
            break
    assert len(clusters) > 0

    x, _, _, length, _, _, _, _, _ = (float(v) for v in BOX[0])
    rear_x = x - length / 2.0
    x_lo, x_hi = rear_x - 20.0, rear_x
    road_z = _context(0).road_z_m
    pos = np.array([cluster.pos for cluster in clusters])

    assert np.all(pos[:, 0] >= x_lo - 1e-6)
    assert np.all(pos[:, 0] <= x_hi + 1e-6)
    assert np.all(np.abs(pos[:, 1]) <= 3.4 / 2.0 + 1e-6)
    assert np.all(pos[:, 2] >= road_z - 1e-6)
    assert np.all(pos[:, 2] <= road_z + 1.5 + 1e-6)


def test_tail_block_fraction_is_the_measured_0_05_to_0_92():
    # Ticket 29e-c: the block spans 5-92 % of the box height, not the 15-100 %
    # knob from 29e. Measured on the real `cal` labels.
    assert PlumeConfig.tail_block_height_frac == (0.05, 0.92)


def test_trail_keeps_clusters_alive_from_frame_two():
    state = PlumeState()

    alive = []
    for frame in range(20):
        inject_plume_stateful(
            _empty_points(),
            BOX,
            _context(frame),
            state,
            seed=200 + frame,
            token=TOKEN,
        )
        alive.append(len(state.all_alive()))

    # Ticket 29f: at 0.69 clusters/cycle a single frame often spawns nothing,
    # so the trail is checked from the first non-empty frame onward.
    first = next(index for index, count in enumerate(alive) if count > 0)
    assert all(count > 0 for count in alive[first:])
    assert alive[-1] > alive[first]


def test_trail_spans_more_than_one_block_so_it_persists():
    state = PlumeState()
    _run_frames(20, state)

    positions = np.array([cluster.pos for cluster in state.all_alive()])
    assert len(positions) > 3

    block_len = SPEED_MPS * DT
    span = float(positions[:, 0].max() - positions[:, 0].min())
    gaps = np.diff(np.sort(positions[:, 0]))
    gap_p50 = float(np.median(gaps))
    print(f"span_m={span:.3f} gap_p50_m={gap_p50:.3f} n={len(positions)}")

    # Persisted across frames (span much larger than one frame's block) and no
    # hole bigger than a few blocks. Ticket 29f: the absolute density is set by
    # the calibration table (17.6 clusters/frame at 130 km/h), so the old
    # "< 1 m gap" threshold only held while the 4x spawn bug was present.
    assert span > 3.0 * block_len
    assert gap_p50 < 4.0 * block_len


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

    # Ticket 29f: rate at 80 km/h is 0.69/cycle, so a single spawn may be empty.
    created = []
    for frame in range(20):
        created = state.spawn(
            _context(frame_index=frame),
            object_id=0,
            rng=np.random.default_rng(frame),
            dt=DT,
            center=center,
            extents=extents,
        )
        if created:
            break

    assert created
    for cluster in created:
        assert cluster.age == pytest.approx(-DT)
        assert 0.0 < cluster.probability() <= 1.0


def test_marker_prints_one_line_with_seven_keys(capsys):
    state = PlumeState()

    # Ticket 29f: a frame with no spawn prints assumed=0, so the marker is read
    # from the first frame that actually spawns a cluster.
    fields: dict[str, str] = {}
    frame_index = 0
    for frame_index in range(20):
        inject_plume_stateful(
            _empty_points(),
            BOX,
            _context(frame_index=frame_index),
            state,
            seed=7 + frame_index,
            token=TOKEN,
        )

        lines = [
            line
            for line in capsys.readouterr().out.splitlines()
            if line.startswith("PLUME_STATE")
        ]
        assert len(lines) == 1

        fields = dict(part.split("=", 1) for part in lines[0].split()[1:])
        if int(fields["spawned"]) > 0:
            break

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
    assert fields["frame"] == str(frame_index)
    assert fields["assumed"] == "1"
