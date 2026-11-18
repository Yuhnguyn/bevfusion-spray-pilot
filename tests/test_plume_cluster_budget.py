"""A1 acceptance — số cụm sống mỗi frame phải khớp bảng `cal`.

Ticket 29f. Trước bản sửa này, `cluster_rate_for_speed` chia cho
``K = Σ exp(−k·Δt/T)`` (mô hình *thinning xác suất*), nhưng
:meth:`spray.plume_state.PlumeState.prune` xoá **cứng** khi ``age > 4T``.
Một cụm vì vậy sống ``4T/Δt + 1`` frame (đo trực tiếp `[ĐO]`: 17 frame ở
60 km/h, 49 ở 100, 66 ở 120), nên tích luỹ thật là ``rate × (4T/Δt + 1)`` ≈
``4 × visible``: plume có 4× số cụm so với bảng và mỗi cụm vỡ vụn 4×
(`docs/measurements/plume-root-cause.md` §2).

Test này khoá lại đại lượng **duy nhất** mà bảng `cal` hứa: số cụm sống trong
một frame. Nó chạy thẳng ``spawn``/``advance``/``prune`` (không materialise điểm)
nên rẻ, và dùng nhiều seed vì ``ttl`` được sample ``N(T, 0.2 s)``.
"""

from __future__ import annotations

import contextlib
import io

import numpy as np
import pytest

from spray.plume import (
    cluster_visible_target_for_speed,
    lifetime_time_constant,
    steady_state_alive_factor,
    steady_state_cluster_factor,
)
from spray.plume_context import PlumeContext
from spray.plume_state import PlumeState, cluster_spawn_rate_for_speed_abs

DT = 0.1
SPEEDS_KMH = (60.0, 100.0, 120.0)
WARMUP_FRAMES = 260  # > 3× tuổi thọ cụm dài nhất (4T/Δt + 1 = 73 frame ở 130)
MEASURE_FRAMES = 60
SEEDS = 3


def _context(speed_kmh: float, frame_index: int) -> PlumeContext:
    speed_mps = speed_kmh / 3.6
    return PlumeContext(
        scene_token="budget",
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=speed_mps,
        object_speed_mps=speed_mps,
        wfh_mm=1.0,
        road_z_m=-1.6,
    )


def _alive_mean(speed_kmh: float, seed: int) -> float:
    """Số cụm sống trung bình ở trạng thái dừng, một seed."""
    state = PlumeState()
    speed_mps = speed_kmh / 3.6
    ego_velocity = np.array([speed_mps, 0.0, 0.0], dtype=np.float64)
    center = np.array([20.0, 0.0, 0.5], dtype=np.float64)
    extents = np.array([1.2, 1.7, 0.9], dtype=np.float64)
    rng = np.random.default_rng(seed)

    alive: list[int] = []
    with contextlib.redirect_stdout(io.StringIO()):
        for frame in range(WARMUP_FRAMES + MEASURE_FRAMES):
            state.advance(DT, ego_velocity=ego_velocity)
            state.prune()
            state.spawn(
                _context(speed_kmh, frame),
                object_id=0,
                rng=rng,
                dt=DT,
                center=center,
                extents=extents,
            )
            if frame >= WARMUP_FRAMES:
                alive.append(len(state.all_alive()))
    return float(np.mean(alive))


@pytest.mark.parametrize("speed_kmh", SPEEDS_KMH)
def test_alive_cluster_count_matches_the_calibration_table(speed_kmh: float):
    target = cluster_visible_target_for_speed(speed_kmh)
    assert target > 0.0

    alive = float(np.mean([_alive_mean(speed_kmh, seed) for seed in range(SEEDS)]))
    ratio = alive / target

    # Dung sai ±10 %: bảng `cal` gốc có CV giữa scene ≈ 0,48 nên siết hơn nữa là
    # giả chính xác; ±10 % là đủ để bắt lại đúng lỗi 4× (400 %).
    assert 0.9 <= ratio <= 1.1, (
        f"{speed_kmh:.0f} km/h: alive={alive:.1f} vs bảng cal {target:.1f} "
        f"(ratio {ratio:.2f})"
    )


def test_alive_factor_is_hard_prune_lifetime_not_the_geometric_k():
    """Hệ số tích luỹ là ``4T/Δt + 1``, không phải ``K``.

    Đây là regression guard cho đúng lỗi ticket 29f: hai hệ số này lệch nhau
    đúng ``max_age_factor`` lần, nên nhầm lại là plume thừa 4× số cụm.
    """
    for speed_kmh in SPEEDS_KMH:
        time_constant = lifetime_time_constant(speed_kmh)
        expected = 4.0 * time_constant / DT + 1.0
        assert steady_state_alive_factor(speed_kmh) == pytest.approx(expected)

        alive_factor = steady_state_alive_factor(speed_kmh)
        geometric = steady_state_cluster_factor(speed_kmh)
        assert alive_factor == pytest.approx(4.0 * geometric, rel=0.15)


def test_spawn_rate_is_consistent_with_the_alive_factor():
    """``rate × alive_factor`` phải trả lại đúng bảng, tức phép đổi là đóng."""
    for speed_kmh in SPEEDS_KMH:
        rate = cluster_spawn_rate_for_speed_abs(speed_kmh)
        recovered = rate * steady_state_alive_factor(speed_kmh)
        assert recovered == pytest.approx(
            cluster_visible_target_for_speed(speed_kmh), rel=1e-6
        )
