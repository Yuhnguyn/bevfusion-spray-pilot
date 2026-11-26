from scripts.probe_sspp_plume import build_markdown


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
