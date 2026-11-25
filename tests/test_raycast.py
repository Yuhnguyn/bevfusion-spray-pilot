"""Ticket 29b/29c: beam ray casting, attenuation and strongest return."""

import re

import numpy as np
import pytest

from spray.beam_model import (
    load_beam_table,
    ray_directions,
    ray_sphere_intersect,
)
from spray.plume_state import SprayCluster
from spray.raycast import RaycastConfig, raycast_frame

ROAD_Z_M = -0.411
RING = 12  # measured elevation +0.020315 deg, close to the horizon
AZIMUTH_INDEX = 0
CLUSTER_RADIUS_M = 0.3


def _table():
    return load_beam_table()


def _cluster(position, radius=CLUSTER_RADIUS_M, age=0.0, ttl=1.0):
    return SprayCluster(
        pos=np.asarray(position, dtype=np.float64),
        vel=np.zeros(3, dtype=np.float64),
        radius=radius,
        age=age,
        ttl=ttl,
        drag=-0.15,
        object_id=0,
        cluster_id=0,
    )


def _beam(ring=RING, azimuth_index=AZIMUTH_INDEX, table=None):
    table = table or _table()
    elevation = table.elevation_deg[ring]
    azimuth = azimuth_index * table.azimuth_step_deg
    return ray_directions(
        np.array([elevation]), np.array([azimuth])
    )[0]


def _point_on_beam(distance, intensity, ring=RING, azimuth_index=AZIMUTH_INDEX):
    direction = _beam(ring, azimuth_index)
    return np.array(
        [[
            distance * direction[0],
            distance * direction[1],
            distance * direction[2],
            intensity,
            ring,
        ]],
        dtype=np.float64,
    )


def _beam_of(detection, table):
    ring = int(detection[4])
    step = table.azimuth_step_deg
    azimuth = np.degrees(np.arctan2(detection[1], detection[0])) % 360.0
    azimuth_index = int(round(azimuth / step)) % int(round(360.0 / step))
    direction = _beam(ring, azimuth_index, table)
    return ring, azimuth_index, direction


def test_cluster_outside_the_beam_fan_gives_no_hit():
    # A 0.3 m sphere at (20, 5, 0) is crossed by many beams: the measured grid
    # has a 0.197 deg azimuth step, so its 0.83 deg angular radius spans ~4 x 4
    # beams. Keeping the ticket's intent (no intersection) means moving the
    # cluster above the measured fan, whose top elevation is +0.109 deg.
    points = _point_on_beam(30.0, 100.0)
    result = raycast_frame(
        points,
        [_cluster((20.0, 5.0, 5.0))],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(0),
    )

    assert result.stats.beams_hit == 0
    assert result.detections.shape == (0, 5)
    assert result.real_points[0, 3] == pytest.approx(100.0)


def test_intersecting_beam_spawns_one_detection_with_certain_probability():
    table = _table()
    result = raycast_frame(
        np.zeros((0, 5)),
        [_cluster((20.0, 0.0, 0.0))],
        table=table,
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(2),
        config=RaycastConfig(p_det_mu=10.0),
    )

    assert result.stats.beams_hit > 0
    assert result.stats.det == result.stats.beams_hit
    assert len(result.detections) == result.stats.det

    center = np.array([20.0, 0.0, 0.0])
    for detection in result.detections:
        _, _, direction = _beam_of(detection, table)
        t0, t1 = ray_sphere_intersect(
            direction[np.newaxis, :], center, CLUSTER_RADIUS_M
        )
        distance = float(np.linalg.norm(detection[:3]))
        assert t0[0] - 1e-6 < distance < t1[0] + 1e-6


def test_every_detection_lies_on_its_beam():
    table = _table()
    result = raycast_frame(
        np.zeros((0, 5)),
        [_cluster((20.0, 0.0, 0.0))],
        table=table,
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(1),
        config=RaycastConfig(p_det_mu=10.0),
    )

    assert len(result.detections) > 0
    step = table.azimuth_step_deg
    for detection in result.detections:
        ring = int(detection[4])
        elevation = np.degrees(
            np.arctan2(detection[2], float(np.hypot(detection[0], detection[1])))
        )
        azimuth = np.degrees(np.arctan2(detection[1], detection[0])) % 360.0
        beam_azimuth = int(round(azimuth / step)) * step
        azimuth_error = abs((azimuth - beam_azimuth + 180.0) % 360.0 - 180.0)

        assert abs(elevation - table.elevation_deg[ring]) < 1e-9
        assert azimuth_error < 1e-9


def test_zero_probability_keeps_real_point_but_attenuates_it():
    table = _table()
    points = _point_on_beam(30.0, 100.0)
    result = raycast_frame(
        points,
        [_cluster((20.0, 0.0, 0.0))],
        table=table,
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(2),
        config=RaycastConfig(p_det_mu=-10.0),
    )

    assert result.stats.det == 0
    assert len(result.detections) == 0
    assert result.stats.att_real_points > 0
    assert result.real_points[0, 3] < 100.0


def test_attenuation_matches_exp_of_the_measured_path_length():
    table = _table()
    config = RaycastConfig(p_det_mu=-10.0)
    points = _point_on_beam(30.0, 100.0)
    center = np.array([20.0, 0.0, 0.0])
    direction = _beam()
    t0, t1 = ray_sphere_intersect(
        direction[np.newaxis, :], center, CLUSTER_RADIUS_M
    )
    expected_length = float(t1[0] - t0[0])

    result = raycast_frame(
        points,
        [_cluster(center)],
        table=table,
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(3),
        config=config,
    )

    ratio = float(result.real_points[0, 3] / points[0, 3])
    expected = np.exp(-2.0 * config.mean_attenuation_per_m * expected_length)
    assert ratio == pytest.approx(expected, abs=1e-12)
    assert result.stats.att_m_total == pytest.approx(expected_length, abs=1e-9)


def test_strongest_return_keeps_the_real_point_when_it_is_brighter():
    points = _point_on_beam(30.0, 255.0)
    result = raycast_frame(
        points,
        [_cluster((20.0, 0.0, 0.0))],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(4),
        config=RaycastConfig(p_det_mu=10.0),
    )

    assert result.stats.real_dropped_plume_stronger == 0
    assert result.stats.det_dropped_stronger_real >= 1
    assert len(result.real_points) == 1
    assert result.real_points[0, 3] > 0.0


def test_strongest_return_drops_the_zero_intensity_real_point():
    # Ticket 29c mục 1: detection intensity is 0, so it can only win against a
    # real return of intensity 0 (a tie keeps the real point; score > 0 wins).
    points = _point_on_beam(30.0, 0.0)
    result = raycast_frame(
        points,
        [_cluster((20.0, 0.0, 0.0))],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(5),
        config=RaycastConfig(p_det_mu=10.0),
    )

    assert result.stats.real_dropped_plume_stronger >= 1
    assert len(result.real_points) == 0
    assert len(result.detections) >= 1
    assert np.any(result.detections[:, 4] == RING)


def test_every_generated_detection_has_intensity_zero():
    result = raycast_frame(
        np.zeros((0, 5)),
        [_cluster((20.0, 0.0, 0.0))],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(6),
        config=RaycastConfig(p_det_mu=10.0),
    )

    assert result.detections.shape[0] > 0
    assert np.all(result.detections[:, 3] == 0.0)
    assert result.stats.att_m_total >= 0.0


def test_marker_has_the_six_required_keys(capsys):
    regex = re.compile(
        r"PLUME_RAYCAST beams=(\d+) hit=(\d+) det=(\d+) "
        r"att_m=([0-9.]+) capped=(\d+) ms=([0-9.]+)"
    )

    raycast_frame(
        np.zeros((0, 5)),
        [_cluster((20.0, 0.0, 0.0))],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(7),
        config=RaycastConfig(p_det_mu=10.0),
        capped=42,
    )

    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("PLUME_RAYCAST")
    ]
    assert len(lines) == 1
    match = regex.fullmatch(lines[0])
    assert match is not None
    assert match.group(5) == "42"


# --- P_det: lognormal rút một lần cho mỗi CỤM (paper Eq. 7 + Fig. 7) ---------
class _SpyRng:
    """Bọc Generator để ghi lại ``size`` của lần gọi ``standard_normal``.

    ``raycast_frame`` rút z-score ``N(0, 1)`` một lần cho mỗi cụm (khi cụm chưa
    mang ``p_det_z``) bằng ``standard_normal`` rồi dựng
    ``P_det0 = exp(mu + sigma·z)``. Đơn vị đo "một lần rút cho mỗi cụm" là số
    phần tử của lần gọi đó — ``normal`` không dùng được vì distance và ranking
    score cũng đi qua nó.
    """

    def __init__(self, seed):
        self._rng = np.random.default_rng(seed)
        self.standard_normal_sizes = []

    def standard_normal(self, size=None):
        self.standard_normal_sizes.append(None if size is None else int(size))
        return self._rng.standard_normal(size=size)

    def normal(self, *args, size=None, **kwargs):
        return self._rng.normal(*args, size=size, **kwargs)

    def lognormal(self, *args, size=None, **kwargs):
        return self._rng.lognormal(*args, size=size, **kwargs)

    def random(self, *args, **kwargs):
        return self._rng.random(*args, **kwargs)


def test_pdet_lognormal_is_drawn_once_per_cluster_not_per_beam():
    # Fig. 7 của paper fit lognormal trên phân bố P_det *giữa các cụm*: một
    # cụm có một P_det, mọi tia cắt cụm bốc Bernoulli với cùng giá trị đó.
    # Một cụm duy nhất bị nhiều tia cắt ⇒ nếu rút theo tia thì size = beams_hit;
    # theo paper thì size = 1.
    spy = _SpyRng(0)
    result = raycast_frame(
        np.zeros((0, 5)),
        [_cluster((20.0, 0.0, 0.0))],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=spy,
    )

    assert result.stats.beams_hit > 1
    assert spy.standard_normal_sizes == [1]


def test_two_clusters_get_two_independent_lognormal_draws():
    spy = _SpyRng(1)
    raycast_frame(
        np.zeros((0, 5)),
        [_cluster((15.0, 0.0, 0.0)), _cluster((20.0, 0.0, 0.0))],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=spy,
    )

    assert spy.standard_normal_sizes == [2]


def test_cluster_pdet_z_is_reused_across_frames_instead_of_redrawn():
    # Nháy sáng/tắt (viz 0072 frame 35): P_det0 phải là hằng số của cụm suốt
    # đời nó, không rút lại mỗi frame. Cụm sinh ra mang ``p_det_z`` ⇒ raycast
    # KHÔNG được rút thêm z nào.
    cluster = _cluster((20.0, 0.0, 0.0))
    cluster.p_det_z = 0.0  # ⇒ P_det0 = exp(mu) = median, không phụ thuộc frame
    spy = _SpyRng(0)
    first = raycast_frame(
        np.zeros((0, 5)),
        [cluster],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=spy,
        config=RaycastConfig(p_det_mu=10.0),
    )
    second = raycast_frame(
        np.zeros((0, 5)),
        [cluster],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=spy,
        config=RaycastConfig(p_det_mu=10.0),
    )

    assert spy.standard_normal_sizes == []  # không rút lại z
    # p_det_mu = 10 ⇒ P_det0 ≈ e^10, xác suất kẹp 1 ⇒ mọi tia trúng đều nổ.
    assert first.stats.det == first.stats.beams_hit
    assert second.stats.det == second.stats.beams_hit


def test_config_p_det_mu_still_steers_a_spawned_cluster():
    # Lưu z (chuẩn hoá) chứ không lưu P_det0 tuyệt đối: đổi ``p_det_mu`` trong
    # config vẫn phải đổi kết quả với CÙNG một cụm đã sinh.
    cluster = _cluster((20.0, 0.0, 0.0))
    cluster.p_det_z = 0.0
    high = raycast_frame(
        np.zeros((0, 5)),
        [cluster],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(3),
        config=RaycastConfig(p_det_mu=10.0),
    )
    low = raycast_frame(
        np.zeros((0, 5)),
        [cluster],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(3),
        config=RaycastConfig(p_det_mu=-10.0),
    )

    assert high.stats.det == high.stats.beams_hit
    assert low.stats.det == 0


# --- P_det(R): hiệu chỉnh cự ly của xác suất phát hiện (2026-11-19) ---------
# Nguồn số: docs/measurements/pdet-vs-range.md §11. Các test dưới đây chỉ khoá
# **cơ chế** (đúng luật R^b, đúng R0 = 25 m, mặc định tắt, env override), không
# khoá giá trị b đã fit — giá trị đó là tham số hiệu chỉnh, đổi được bằng config.
def _detections_at(position, exponent, seed=11, mu=-2.3):
    result = raycast_frame(
        np.zeros((0, 5)),
        [_cluster(position)],
        table=_table(),
        road_z_m=ROAD_Z_M,
        rng=np.random.default_rng(seed),
        config=RaycastConfig(p_det_mu=mu, pdet_range_exponent=exponent),
    )
    return result.detections


def test_pdet_range_exponent_is_off_by_default():
    assert RaycastConfig().pdet_range_exponent == 0.0


def test_pdet_range_exponent_env_override(monkeypatch):
    monkeypatch.setenv("PLUME_PDET_RANGE_EXPONENT", "0.75")
    assert RaycastConfig().pdet_range_exponent == pytest.approx(0.75)
    # config tường minh luôn thắng env
    assert RaycastConfig(pdet_range_exponent=0.0).pdet_range_exponent == 0.0
    monkeypatch.setenv("PLUME_PDET_RANGE_EXPONENT", "không-phải-số")
    with pytest.raises(ValueError):
        RaycastConfig()


def test_pdet_range_law_is_anchored_at_the_paper_distance():
    from spray.raycast import _range_factor

    def factor(metres, exponent):
        return float(_range_factor([_cluster((metres, 0.0, 0.0))], exponent)[0])

    assert factor(25.0, 2.0) == pytest.approx(1.0, abs=1e-12)
    assert factor(2.0, 2.0) == pytest.approx((2.0 / 25.0) ** 2, rel=1e-12)
    assert factor(5.0, 1.0) == pytest.approx(0.2, rel=1e-12)
    assert factor(5.0, 0.0) == pytest.approx(1.0, rel=1e-12)


def test_pdet_at_paper_distance_does_not_depend_on_the_exponent():
    # P_det(R0) = P_det0: ở đúng 25 m, luật cự ly là phép nhân với 1,0 nên
    # chuỗi ngẫu nhiên và kết quả phải TRÙNG TUYỆT ĐỐI với P_det hằng.
    base = _detections_at((25.0, 0.0, 0.0), 0.0)
    scaled = _detections_at((25.0, 0.0, 0.0), 1.5)

    assert base.shape[0] > 0
    assert np.array_equal(base, scaled)


def test_positive_exponent_suppresses_a_near_cluster():
    near = (4.0, 0.0, 0.0)
    base = np.mean([_detections_at(near, 0.0, seed=seed).shape[0]
                    for seed in range(6)])
    damped = np.mean([_detections_at(near, 1.0, seed=seed).shape[0]
                      for seed in range(6)])

    assert base > 0.0
    # factor = (4/25)^1 = 0,16 ⇒ tỉ lệ phải cùng bậc 0,16, không phải 1,0.
    assert damped < 0.5 * base
