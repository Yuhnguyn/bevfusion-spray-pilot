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
