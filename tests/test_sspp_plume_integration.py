"""A4 — test tích hợp: plume phải đặt đúng theo **quy ước box của adapter**.

Vì sao test này tồn tại (plan §2 A4): đã từng có bug lọt qua toàn bộ unit test vì
unit test dựng box kiểu **tâm**, còn adapter ghi box kiểu **đáy**. Test này đi qua
đúng đường thật — `spray.sspp_adapter._boxes_to_arrays` (nguồn của quy ước) rồi
`spray.plume.inject_plume_stateful` — nên nếu ai đổi một trong hai đầu, test đỏ.

Quy ước (spray/sspp_adapter.py:13-15,117,141): 9 cột
``x, y, z_bottom, size_x(dài), size_y(rộng), size_z(cao), yaw, speed_mps, 0``,
trong đó **``box[2]`` là ĐÁY hộp**, không phải tâm.

Cách bắt lỗi: khối plume nằm trong ``[z_bottom + 0,05·h, z_bottom + 0,92·h]``.
Nếu ai đó hiểu ``box[2]`` là **tâm** thì khối bị dịch lên đúng ``h/2`` (≈0,95 m với
box cao 1,9 m) — lớn hơn nhiều so với dung sai của test.
"""

from __future__ import annotations

import contextlib
import io

import numpy as np
import pytest

from spray.plume import PlumeConfig, inject_plume_stateful
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState
from spray.sspp_adapter import _boxes_to_arrays

DT = 0.1
SPEED_MPS = 100.0 / 3.6
BOX_HEIGHT = 1.9
FRAC_LO, FRAC_HI = PlumeConfig.tail_block_height_frac


def _inject(z_bottom: float, speed_mps: float = SPEED_MPS) -> np.ndarray:
    """Chạy vài frame để có plume, trả về các điểm spray được chèn ở frame cuối."""
    boxes, _, _ = _boxes_to_arrays(
        [{
            "name": "Crafter",
            "x": 20.0,
            "y": 0.0,
            "z_bottom": z_bottom,
            "size_x": 4.5,
            "size_y": 1.9,
            "size_z": BOX_HEIGHT,
            "yaw": 0.0,
            "num_lidar_pts": 100,
        }],
        speed_mps,
    )
    config = PlumeConfig()
    state = PlumeState()
    injected = np.zeros((0, 3))
    with contextlib.redirect_stdout(io.StringIO()):
        for index in range(40):
            context = PlumeContext(
                scene_token="a4",
                frame_index=index,
                epoch=0,
                sensor_origin=np.zeros(3, dtype=np.float64),
                ego_speed_mps=speed_mps,
                object_speed_mps=speed_mps,
                wfh_mm=1.0,
                road_z_m=z_bottom,
            )
            result = inject_plume_stateful(
                np.zeros((0, 5), dtype=np.float32),
                boxes,
                context,
                state,
                seed=index,
                token=f"a4/{index}",
                config=config,
            )
            if len(result.injected):
                injected = result.injected[:, :3].astype(np.float64)
    return injected


def test_adapter_puts_the_box_bottom_in_column_two():
    boxes, _, _ = _boxes_to_arrays(
        [{
            "name": "Crafter",
            "x": 20.0, "y": 0.0, "z_bottom": -1.6,
            "size_x": 4.5, "size_y": 1.9, "size_z": BOX_HEIGHT,
            "yaw": 0.0, "num_lidar_pts": 100,
        }],
        SPEED_MPS,
    )
    assert boxes.shape == (1, 9)
    assert boxes[0, 2] == pytest.approx(-1.6)
    assert boxes[0, 3] == pytest.approx(4.5)   # dài dọc yaw
    assert boxes[0, 4] == pytest.approx(1.9)   # rộng ngang yaw
    assert boxes[0, 5] == pytest.approx(BOX_HEIGHT)


def test_plume_sits_above_the_box_bottom_not_the_box_centre():
    """Điểm mấu chốt của A4: dịch lên ``h/2`` là bug, không phải nhiễu."""
    z_bottom = -1.6
    injected = _inject(z_bottom)
    assert len(injected) > 0, "không có điểm plume nào — test không kiểm được gì"

    expected_low = z_bottom + FRAC_LO * BOX_HEIGHT
    expected_high = z_bottom + FRAC_HI * BOX_HEIGHT
    expected_mid = 0.5 * (expected_low + expected_high)
    wrong_mid = expected_mid + BOX_HEIGHT / 2.0  # nếu box[2] bị hiểu là tâm

    mean_z = float(injected[:, 2].mean())
    assert abs(mean_z - expected_mid) < 0.35 * BOX_HEIGHT, (
        f"plume ở z={mean_z:.2f}, kỳ vọng quanh {expected_mid:.2f} "
        f"(đáy {expected_low:.2f} … đỉnh {expected_high:.2f}); nếu là "
        f"{wrong_mid:.2f} thì đã dùng TÂM box thay vì ĐÁY"
    )
    assert abs(mean_z - wrong_mid) > abs(mean_z - expected_mid), (
        "plume gần giả thuyết 'box[2] là tâm' hơn — quy ước đáy đã bị phá"
    )


def test_raising_the_box_bottom_raises_the_plume_by_the_same_amount():
    """Bất biến: đổi đáy +1 m thì plume phải dời +1 m (không phải +1 m ± h/2)."""
    low = _inject(-2.6)
    high = _inject(-1.6)
    assert len(low) > 0 and len(high) > 0
    shift = float(high[:, 2].mean() - low[:, 2].mean())
    assert shift == pytest.approx(1.0, abs=0.25), (
        f"plume dời {shift:.2f} m khi đáy dời 1,00 m — sai quy ước hoặc sai hệ số"
    )


def test_plume_is_behind_the_box_along_its_yaw():
    """Khối plume nằm **sau** hộp: tâm khối lệch về phía -x khi yaw = 0."""
    injected = _inject(-1.6)
    assert len(injected) > 0
    # box ở x = 20 m, dài 4,5 m ⇒ đuôi xe ở x = 17,75 m; khối plume nằm sau đó.
    assert injected[:, 0].mean() < 17.75 + 1e-6, (
        "plume lấn về phía trước đuôi xe — sai chiều đặt khối"
    )
