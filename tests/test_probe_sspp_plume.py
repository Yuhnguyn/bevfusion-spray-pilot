import numpy as np

from scripts.probe_sspp_plume import build_markdown, count_clusters
from spray.plume import PlumeConfig, inject_plume


def _synthetic_frame():
    """800 random points plus one 60 km/h box placed behind the sensor."""

    rng = np.random.default_rng(1234)
    xyz = rng.uniform((-8.0, -8.0, 0.2), (8.0, 8.0, 1.6), size=(800, 3))
    points = np.column_stack(
        [xyz, np.zeros(800, dtype=np.float64), np.zeros(800, dtype=np.float64)]
    ).astype(np.float32)
    box = np.array(
        [[15.0, 0.0, 0.5, 4.5, 1.8, 1.8, 0.0, 60.0 / 3.6, 0.0]],
        dtype=np.float32,
    )
    return points, box


def _side(frames, clusters, points, p50, mean, height, capped=0):
    return {
        "frames": frames,
        "clusters_total": int(round(clusters * frames)),
        "points_total": int(round(points * frames)),
        "clusters_per_frame": clusters,
        "points_per_frame": points,
        "det_per_cluster_p50": p50,
        "det_per_cluster_mean": mean,
        "height_p5": height,
        "capped": capped,
        "skipped_no_velocity": 0,
        "skipped_low_speed": 0,
        "eligible_boxes": frames,
    }


def test_cluster_counter_finds_dense_injected_plume():
    points, box = _synthetic_frame()

    result = inject_plume(
        points, box, seed=0, token="Crafter_dynamic/scene/000000",
        config=PlumeConfig(),
    )
    clusters, sizes = count_clusters(result.injected)

    assert result.injected.shape[0] > 0
    assert clusters > 0
    assert sizes.size == clusters
    assert sizes.min() >= 3


def test_same_token_is_deterministic():
    points, box = _synthetic_frame()

    first = inject_plume(
        points, box, seed=0, token="Crafter_dynamic/scene/000000",
        config=PlumeConfig(),
    )
    second = inject_plume(
        points, box, seed=0, token="Crafter_dynamic/scene/000000",
        config=PlumeConfig(),
    )

    assert np.array_equal(first.points, second.points)
    assert np.array_equal(first.injected, second.injected)
    assert first.stats.injected == second.stats.injected
    assert first.stats.capped == second.stats.capped


def test_markdown_has_real_and_gen_columns():
    rows = {
        ("Crafter_dynamic", 60.0): {
            "real": _side(2, 5.0, 120.0, 8.0, 9.0, 0.4),
            "gen": _side(2, 7.0, 150.0, 10.0, 11.0, 0.5, capped=3),
        },
        ("Crafter_dynamic", 100.0): {
            "real": _side(2, 9.0, 300.0, 12.0, 13.0, 0.6),
            "gen": _side(2, 6.0, 200.0, 14.0, 15.0, 0.7),
        },
    }

    text = build_markdown(
        rows,
        dataset_root="/tmp/SemanticSprayDataset",
        split="train",
        scenes=2,
        frames=4,
        frames_per_scene=2,
    )

    assert "cụm/frame real `[ĐO]`" in text
    assert "cụm/frame gen `[ĐO]`" in text
    assert "| Crafter_dynamic | 60 | 2 | 5,00 | 7,00 |" in text
    assert "| Crafter_dynamic | 100 | 2 | 9,00 | 6,00 |" in text
    assert "Fig. 4 @25 m" in text
    assert "`[PAPER-graph]`" in text
