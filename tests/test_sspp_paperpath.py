"""The full paper chain wired end to end on a synthetic mini scene.

No dataset is read: a two-frame scene with one box at 80 km/h and 200 synthetic
background points is enough to pin the four properties the wiring must have.

The chain under test is the same one ``scripts/smoke_sspp_paperpath.py`` runs:
``inject_plume_stateful`` (wet ground + clusters) followed by ``raycast_frame``
through a small :class:`~spray.beam_model.BeamTable`.
"""

from __future__ import annotations

import numpy as np

from spray.beam_model import BeamTable
from spray.plume import inject_plume_stateful
from spray.plume_context import PlumeContext, seed_for
from spray.plume_state import PlumeState
from spray.raycast import raycast_frame
from spray.wet_ground import WetGroundConfig

ROAD_Z_M = -0.411
SPEED_MPS = 80.0 / 3.6
SCENE_TOKEN = "mini-scene"
FRAME_TOKEN = "mini-scene/000000"
FRAME_COUNT = 2
BACKGROUND_POINTS = 200
PAVEMENT_POINTS = 12
BOX_X_M = 10.0
BOX = np.array(
    [[BOX_X_M, 0.0, ROAD_Z_M, 6.8, 2.4, 2.6, 0.0, SPEED_MPS, 0.0]],
    dtype=np.float32,
)

# 8 rings over -5..5 deg x 64 azimuth columns: small enough to run in a test,
# dense enough that the clusters behind the box always catch at least one beam.
TABLE = BeamTable(
    elevation_deg=tuple(float(value) for value in np.linspace(-5.0, 5.0, 8)),
    azimuth_step_deg=5.625,
)


def background_points(seed: int = 2024) -> np.ndarray:
    """200 background points, 12 of them on wet pavement inside the y window."""

    rng = np.random.default_rng(seed)
    xyz = np.column_stack(
        [
            rng.uniform(-20.0, 20.0, BACKGROUND_POINTS),
            rng.uniform(-20.0, 20.0, BACKGROUND_POINTS),
            rng.uniform(ROAD_Z_M + 0.1, 4.0, BACKGROUND_POINTS),
        ]
    )
    xyz[:PAVEMENT_POINTS, 0] = rng.uniform(6.0, 25.0, PAVEMENT_POINTS)
    xyz[:PAVEMENT_POINTS, 1] = rng.uniform(2.5, 6.5, PAVEMENT_POINTS)
    xyz[:PAVEMENT_POINTS, 2] = ROAD_Z_M + 0.05

    intensity = rng.uniform(60.0, 220.0, BACKGROUND_POINTS)
    ring = rng.integers(0, len(TABLE.elevation_deg), BACKGROUND_POINTS).astype(float)
    return np.column_stack([xyz, intensity, ring]).astype(np.float32)


def context(frame_index: int) -> PlumeContext:
    return PlumeContext(
        scene_token=SCENE_TOKEN,
        frame_index=frame_index,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=SPEED_MPS,
        object_speed_mps=SPEED_MPS,
        wfh_mm=1.0,
        road_z_m=ROAD_Z_M,
    )


def run_scene(
    points: np.ndarray,
    *,
    wet_ground: WetGroundConfig | None,
    token: str = FRAME_TOKEN,
    seed: int = 0,
) -> list[dict]:
    """Two frames through the chain, sharing one ``PlumeState`` (one per scene)."""

    state = PlumeState()
    frames: list[dict] = []
    for frame_index in range(FRAME_COUNT):
        result = inject_plume_stateful(
            points,
            BOX,
            context(frame_index),
            state,
            seed=seed,
            token=token,
            wet_ground=wet_ground,
            vehicle_class="crafter",
        )
        raycast = raycast_frame(
            result.points,
            state.all_alive(),
            table=TABLE,
            road_z_m=ROAD_Z_M,
            rng=np.random.default_rng(seed_for(token, frame_index, 0)),
        )
        frames.append(
            {
                "spawned": int(state.counters.spawned),
                "alive": len(state.all_alive()),
                "det": int(raycast.stats.det),
                "detections": raycast.detections.copy(),
                "points": result.points.copy(),
                "background": result.points[: len(points)].copy(),
                "wet_points_in": int(result.stats.wet_points_in),
            }
        )
    return frames


def test_clusters_survive_into_the_second_frame():
    frames = run_scene(background_points(), wet_ground=WetGroundConfig(enabled=True))

    assert frames[0]["alive"] == frames[0]["spawned"]
    assert frames[1]["alive"] > frames[1]["spawned"]


def test_raycast_produces_detections():
    frames = run_scene(background_points(), wet_ground=WetGroundConfig(enabled=True))

    assert sum(frame["det"] for frame in frames) > 0
    assert all(frame["detections"].shape[1] == 5 for frame in frames if frame["det"])


def test_the_same_token_is_deterministic():
    first = run_scene(background_points(), wet_ground=WetGroundConfig(enabled=True))
    second = run_scene(background_points(), wet_ground=WetGroundConfig(enabled=True))

    for left, right in zip(first, second):
        assert np.array_equal(left["points"], right["points"])
        assert np.array_equal(left["detections"], right["detections"])
        assert left["det"] == right["det"]
        assert left["alive"] == right["alive"]


def test_wet_ground_lowers_background_intensity():
    points = background_points()
    wet = run_scene(points, wet_ground=WetGroundConfig(enabled=True))
    dry = run_scene(points, wet_ground=None)

    for wet_frame, dry_frame in zip(wet, dry):
        assert wet_frame["wet_points_in"] > 0
        assert dry_frame["wet_points_in"] == 0
        assert np.array_equal(
            wet_frame["background"][:, :3], dry_frame["background"][:, :3]
        )
        assert (
            wet_frame["background"][:, 3].sum()
            < dry_frame["background"][:, 3].sum()
        )
