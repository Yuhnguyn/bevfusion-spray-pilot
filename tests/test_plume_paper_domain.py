"""Miền hợp lệ "Cách A" của generator (ADR-0006 §5.7)."""

import numpy as np

from spray.plume_state import (
    DIFFUSION_ALPHA,
    PlumeState,
    PlumeStateConfig,
    SprayCluster,
)


def _cluster(x: float) -> SprayCluster:
    return SprayCluster(
        pos=np.array([x, 0.0, 0.0], dtype=np.float64),
        vel=np.zeros(3, dtype=np.float64),
        radius=0.30,
        age=0.0,
        ttl=1.0,
        drag=0.0,
        object_id=0,
        cluster_id=0,
    )


def test_domain_off_returns_all_alive():
    """min_range_m=0, max_range_m=inf => select_alive() == all_alive() (cùng list)."""
    state = PlumeState(PlumeStateConfig())
    state._clusters[(state._scene_token, 0)] = [_cluster(1.0), _cluster(80.0)]

    alive = state.all_alive()
    selected = state.select_alive()

    assert len(selected) == len(alive)
    assert all(kept is original for kept, original in zip(selected, alive))


def test_domain_filters_by_radius():
    """3 cụm ở |pos| = 1.0, 10.0, 80.0 m với min=2.5/max=50 => chỉ còn cụm 10 m."""
    state = PlumeState(PlumeStateConfig(min_range_m=2.5, max_range_m=50.0))
    state._clusters[(state._scene_token, 0)] = [
        _cluster(1.0),
        _cluster(10.0),
        _cluster(80.0),
    ]

    kept = state.select_alive()

    assert [float(np.linalg.norm(cluster.pos)) for cluster in kept] == [10.0]


def test_domain_env_switch_does_not_change_default(monkeypatch):
    """Không set PLUME_PAPER_DOMAIN => default không bị đổi."""
    monkeypatch.delenv("PLUME_PAPER_DOMAIN", raising=False)

    cfg = PlumeStateConfig()

    assert cfg.min_range_m == 0.0
    assert cfg.max_range_m == float("inf")
    assert cfg.diffusion_alpha == DIFFUSION_ALPHA == 0.06


def _cluster_radius(x: float, radius: float) -> SprayCluster:
    cluster = _cluster(x)
    cluster.radius = radius
    return cluster


def test_domain_min_range_uses_sphere_surface_not_centre():
    """Tâm ở 3 m nhưng bán kính 2 m => MẶT CẦU ở 1 m, phải bị loại.

    Đây là ca mà lọc-theo-tâm bỏ sót: đo trên 40 frame alpha=0, 7,3 % cụm có mặt
    cầu dưới 2,5 m lọt qua nếu so ``‖pos‖`` thay vì ``‖pos‖ − radius``.
    """
    state = PlumeState(PlumeStateConfig(min_range_m=2.5, max_range_m=50.0))
    state._clusters[(state._scene_token, 0)] = [
        _cluster_radius(3.0, 2.0),   # mặt cầu 1.0 m -> LOẠI
        _cluster_radius(12.0, 2.0),  # mặt cầu 10.0 m -> GIỮ
    ]

    kept = state.select_alive()

    assert [float(np.linalg.norm(c.pos)) for c in kept] == [12.0]


def test_domain_max_range_still_uses_centre():
    """``max_range_m`` so với TÂM (đó là đại lượng paper đánh giá ở Fig. 11/12)."""
    state = PlumeState(PlumeStateConfig(min_range_m=0.0, max_range_m=50.0))
    state._clusters[(state._scene_token, 0)] = [
        _cluster_radius(49.0, 4.0),  # tâm 49 m <= 50 -> GIỮ (dù mặt cầu 45 m)
        _cluster_radius(52.0, 4.0),  # tâm 52 m > 50 -> LOẠI
    ]

    kept = state.select_alive()

    assert [float(np.linalg.norm(c.pos)) for c in kept] == [49.0]
