"""Pin the 9-column box convention written by ``spray/sspp_adapter.py``.

The adapter writes ``(x, y, z_bottom, size_x, size_y, size_z, yaw, vx, vy)``:
``box[2]`` is the box **bottom** (``center3D.z - size3D.z / 2``), ``box[3]`` is
the length along the yaw axis and ``box[4]`` the width across it.  Each test
below fails on exactly one of the three convention bugs.
"""

import numpy as np

from spray.plume import _inside_box, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState

DT = 0.1
SPEED_MPS = 80.0 / 3.6
TOKEN = "scene-box-convention"

BOX_BOTTOM = -0.411
LENGTH = 6.83
WIDTH = 2.42
HEIGHT = 2.62


def _box(x=0.0):
    return np.array(
        [[x, 0.0, BOX_BOTTOM, LENGTH, WIDTH, HEIGHT, 0.0, SPEED_MPS, 0.0]],
        dtype=np.float32,
    )


def _context(frame_index=0):
    return PlumeContext(
        scene_token=TOKEN,
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.array([0.0, 0.0, 1.8], dtype=np.float64),
        ego_speed_mps=SPEED_MPS,
        object_speed_mps=SPEED_MPS,
        wfh_mm=1.0,
        road_z_m=BOX_BOTTOM,
        object_velocity_ego_mps=None,
    )


def _spawn_one_frame():
    """Newest frame's cohort; ticket 29f dropped the rate to 0.69/cycle at
    80 km/h, so one call often spawns nothing and we accumulate cycles."""
    state = PlumeState()
    clusters = []
    for frame in range(20):
        before = {cluster.cluster_id for cluster in state.alive(0)}
        inject_plume_stateful(
            np.zeros((0, 5), dtype=np.float32),
            _box(),
            _context(frame),
            state,
            seed=11 + frame,
            token=TOKEN,
        )
        # Chỉ lấy **cohort sinh ở frame này**: từ khi có warm start, `alive`
        # còn chứa vệt cũ đã trôi xa; các assert dưới đây nói về hình học khối
        # của cụm MỚI, không phải toàn bộ vệt.
        # Cụm sinh ở frame này có `age < 0` (spawn đặt age = -dt); cụm cũ đã
        # được advance nên age >= 0. Dùng age thay vì id để không dính cohort
        # do warm start sinh ra trong chính lần gọi đầu.
        clusters = [c for c in state.alive(0) if c.age < 0.0]
        if clusters:
            break
    return clusters


def test_box_z_is_bottom_not_centre():
    clusters = _spawn_one_frame()
    assert clusters

    z = np.array([cluster.pos[2] for cluster in clusters])
    assert z.min() >= BOX_BOTTOM - 1e-6
    assert z.max() <= BOX_BOTTOM + HEIGHT + 1e-6


def test_block_offset_uses_length_not_width():
    clusters = _spawn_one_frame()
    assert clusters

    block_len = SPEED_MPS * DT
    x_lo = 0.0 - LENGTH / 2.0 - block_len
    x_hi = 0.0 - LENGTH / 2.0
    x = np.array([cluster.pos[0] for cluster in clusters])
    assert np.all(x >= x_lo - 1e-6)
    assert np.all(x <= x_hi + 1e-6)


def test_inside_box_uses_length_on_x():
    box = _box()[0]
    along = np.array([[2.0, 0.0, 0.5]], dtype=np.float64)
    across = np.array([[0.0, 2.0, 0.5]], dtype=np.float64)

    assert bool(_inside_box(along, box, margin=0.0)[0])
    assert not bool(_inside_box(across, box, margin=0.0)[0])


def test_inside_box_z_range_is_bottom_to_bottom_plus_height():
    box = _box()[0]

    inside = np.array([[0.0, 0.0, -0.30]], dtype=np.float64)
    below = np.array([[0.0, 0.0, -0.60]], dtype=np.float64)
    above = np.array([[0.0, 0.0, 2.30]], dtype=np.float64)

    assert bool(_inside_box(inside, box, margin=0.0)[0])
    assert not bool(_inside_box(below, box, margin=0.0)[0])
    assert not bool(_inside_box(above, box, margin=0.0)[0])
