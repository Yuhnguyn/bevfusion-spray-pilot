"""Bảng mật độ plume cho kịch bản cố định 3 box (ticket 22).

Kịch bản: 3 box ở 12 / 22 / 38 m phía trước, 80 km/h, seed 0–4, cùng một frame
nền tổng hợp 1.000 điểm. Chỉ dùng numpy, không cần GPU/checkpoint.

In bảng điểm **trước → sau** khi inject (ticket 22: bỏ dropout, dùng hệ số tích
luỹ K) và in cạnh bảng cũ trong docs để thấy chênh. Bảng cũ (1.330 → 1.057,
−21%) sinh bằng công thức trước ticket 21–22, chỉ giữ làm đối chiếu.
"""

from __future__ import annotations

import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from spray.plume import PlumeConfig, inject_plume  # noqa: E402

SPEED_KMH = 80.0
DISTANCES_M = (12.0, 22.0, 38.0)
SEEDS = tuple(range(5))
CLEAN_POINTS = 1000

# Bảng cũ trong docs: sinh bằng công thức trước ticket 21–22 (ticket 17).
LEGACY_TOTAL_BEFORE = 1330
LEGACY_TOTAL_AFTER = 1057


def _clean_frame(count: int = CLEAN_POINTS) -> np.ndarray:
    rng = np.random.default_rng(1234)
    x = rng.uniform(5.0, 50.0, count)
    y = rng.uniform(-20.0, 20.0, count)
    z = rng.uniform(-1.0, 1.0, count)
    return np.column_stack(
        [x, y, z, np.zeros(count), np.zeros(count)]
    ).astype(np.float32)


def _boxes() -> np.ndarray:
    speed = SPEED_KMH / 3.6
    return np.array(
        [
            [distance, 0.0, 0.0, 4.5, 1.9, 1.5, 0.0, speed, 0.0]
            for distance in DISTANCES_M
        ],
        dtype=np.float32,
    )


def build_rows(config: PlumeConfig | None = None, token: str = "density") -> list[dict]:
    points = _clean_frame()
    boxes = _boxes()
    rows: list[dict] = []
    for seed in SEEDS:
        result = inject_plume(points, boxes, seed=seed, token=token, config=config)
        rows.append(
            {
                "seed": seed,
                "before": int(len(result.points_clean)),
                "after": int(len(result.points)),
                "injected": int(len(result.injected)),
                "clusters": int(result.stats.clusters),
            }
        )
    return rows


def totals(rows: list[dict]) -> dict:
    return {key: sum(row[key] for row in rows) for key in ("before", "after", "injected", "clusters")}


def render(rows: list[dict]) -> str:
    total = totals(rows)
    lines = [
        f"Kịch bản: 3 box {DISTANCES_M[0]:.0f}/{DISTANCES_M[1]:.0f}/{DISTANCES_M[2]:.0f} m, "
        f"{SPEED_KMH:.0f} km/h, seed 0–{SEEDS[-1]}, cùng frame nền {CLEAN_POINTS} điểm.",
        "",
        "| seed | điểm trước | điểm sau | thêm | cụm |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['seed']} | {row['before']} | {row['after']} | "
            f"{row['injected']} | {row['clusters']} |"
        )
    lines.append(
        f"| **tổng** | **{total['before']}** | **{total['after']}** | "
        f"**{total['injected']}** | **{total['clusters']}** |"
    )
    before = f"{LEGACY_TOTAL_BEFORE:,}".replace(",", ".")
    after = f"{LEGACY_TOTAL_AFTER:,}".replace(",", ".")
    legacy = (
        "Bảng cũ trong docs — **công thức trước ticket 21–22** (ticket 17), chỉ để đối chiếu: "
        f"{before} → {after} điểm "
        f"({(LEGACY_TOTAL_AFTER - LEGACY_TOTAL_BEFORE) / LEGACY_TOTAL_BEFORE:+.0%})."
    )
    lines += [
        "",
        legacy,
        "Bảng mới ở trên dùng công thức ticket 22 (round(mean × K), không dropout) — không trộn nhãn.",
    ]
    return "\n".join(lines)


def main() -> None:
    print(render(build_rows()))


if __name__ == "__main__":
    main()
