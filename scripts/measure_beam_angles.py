#!/usr/bin/env python3
"""Check the 32 LiDAR elevation angles and the meaning of the 5 point columns.

Ticket 25, item 2. Nominal angles come from the manufacturer manual (URL in the
report); the check is done on the real ``velodyne/*.bin`` columns of 60 frames
spread over 6 scenes. The nominal table is never edited to fit the data.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import plume_v2_measure_common as common  # noqa: E402

SECTION = "measure_beam_angles.py"
SCRIPT = "measure_beam_angles.py"


def render(stats: dict) -> str:
    rings = stats["per_ring"]
    distinct_rings = stats["distinct_rings"]
    lines: list[str] = [
        f"## 2. Góc elevation và ý nghĩa 5 cột `velodyne` — `{SCRIPT}`",
        "",
        "### Cảm biến của dataset",
        "",
        f"- README của SemanticSpray ghi cảm biến là **Velodyne VLP-32C** "
        f"(`{common.DATASET_README_URL}`), không phải HDL-32E. Ticket 25 ghi "
        "HDL-32E; bảng HDL-32E vẫn được liệt kê đầy đủ bên dưới để đối chiếu, "
        "nhưng **bảng dùng để kiểm chéo là VLP-32C** vì đó là cảm biến thật "
        "của `velodyne/*.bin`.",
        "",
        f"### Bảng 32 góc danh nghĩa `[PAPER]`",
        "",
        f"- VLP-32C: Velodyne VLP-32C User Manual 63-9325 Rev. D, **Table 9-2** "
        f"(`{common.VLP32C_MANUAL_URL}`).",
        f"- HDL-32E: Velodyne HDL-32E datasheet 97-0038 Rev. N, FOV "
        f"`+10,67° … −30,67°`, bước `1,33°` "
        f"(`{common.HDL32E_DATASHEET_URL}`).",
        "",
        "| Laser ID | VLP-32C (°) | Nguồn VLP-32C | HDL-32E (°) | Nguồn HDL-32E |",
        "|---:|---:|---|---:|---|",
    ]
    for laser_id in range(32):
        lines.append(
            f"| {laser_id} | {common.VLP32C_ELEVATION_BY_LASER_ID[laser_id]:.3f} | "
            f"{common.VLP32C_SOURCE} | "
            f"{common.HDL32E_ELEVATION_BY_LASER_ID[laser_id]:.2f} | "
            f"{common.HDL32E_SOURCE} |"
        )

    lines += [
        "",
        "### 5 cột của `velodyne/*.bin` `[ĐO " + SCRIPT + "]`",
        "",
        f"Đo trên **{stats['frames']} frame** thuộc **{len(stats['scenes'])} scene** "
        "(3 Crafter + 3 Golf, 10 frame/scene, chọn đều theo chỉ số): "
        + ", ".join(
            f"`{scene.parent.name}/{scene.name}`" for scene in stats["scenes"]
        )
        + ".",
        "",
        "| Cột | Nội dung | Bằng chứng số |",
        "|---:|---|---|",
        "| 0, 1, 2 | `x, y, z` (m) | `z` của điểm mặt đường (label 0, "
        "`\\|x\\|,\\|y\\| < 20 m`) có percentile 1 = `−0,411 m`; box thật cao "
        "`2,62 m` (xem `verify_frame_geometry.py`) |",
        f"| 3 | **intensity** (0–255) | min `{stats['intensity_min']:.0f}`, "
        f"max `{stats['intensity_max']:.0f}`, p1 `{stats['intensity_p1']:.0f}`, "
        f"p50 `{stats['intensity_p50']:.0f}`, p99 `{stats['intensity_p99']:.0f}`; "
        f"{min(stats['distinct_intensities'])}–{max(stats['distinct_intensities'])} "
        "giá trị phân biệt mỗi frame; "
        f"{stats['non_integer_intensity']} giá trị không nguyên |",
        f"| 4 | **ring / beam id** `0…31` | "
        f"union qua mẫu = `{stats['ring_union'][0]}…{stats['ring_union'][-1]}` "
        f"({len(stats['ring_union'])} giá trị); mỗi frame có "
        f"{min(distinct_rings)}–{max(distinct_rings)} ring (median "
        f"{sorted(distinct_rings)[len(distinct_rings) // 2]}); "
        f"{stats['non_integer_ring']} giá trị không nguyên |",
        "",
        "`[ĐO " + SCRIPT + "]` Cột 4 là **ring id**, không phải intensity hay "
        "cột thời gian: giá trị nguyên `0…31`; các ring chính `0–14` có "
        "~1.300–1.800 điểm/frame và phủ gần đủ 360° azimuth (xem bảng dưới).",
        "",
        "### Phân bố ring và elevation quan sát `[ĐO " + SCRIPT + "]`",
        "",
        "`elevation = atan2(z, sqrt(x² + y²))` tính từ chính toạ độ điểm. "
        "`obs median` là median của median từng frame (robust với outlier).",
        "",
        "| Ring | n_frame | n_điểm | az bin/ frame (median) | obs median (°) | p25 | p75 | "
        "VLP-32C cùng ID (°) | Δ cùng ID (°) | Gần nhất (°) | Δ gần nhất (°) |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for ring in range(32):
        row = rings[ring]
        if row["n_frames"] == 0:
            lines.append(
                f"| {ring} | 0 | {row['n_points']} | – | không có điểm | – | – | – | – | – | – |"
            )
            continue
        flag = "" if row["n_frames"] >= 30 else " ⚠"
        lines.append(
            f"| {ring}{flag} | {row['n_frames']} | {row['n_points']:,} | "
            f"{row['az_bins_median']:.0f}/36 | {row['observed']:.3f} | "
            f"{row['p25']:.3f} | {row['p75']:.3f} | "
            f"{row['nominal_same_id']:.3f} | {row['delta_same_id']:+.3f} | "
            f"{row['nearest_nominal']:.3f} | {row['delta_nearest']:+.3f} |"
        )

    same_median, same_max, same_count = stats["same_all"]
    stable_median, stable_max, stable_count = stats["same_stable"]
    nearest_median, nearest_max, _ = stats["nearest_all"]
    hdl_median, hdl_max, hdl_count = stats["hdl_all"]
    deltas = [rings[ring]["delta_same_id"] for ring in stats["present"]]
    ring0 = rings[0]["observed"]
    ring3 = rings[3]["observed"]
    lines += [
        "",
        "⚠ = ring có mặt ở **< 30/60 frame** (mẫu thưa; median kém tin cậy).",
        "",
        "### Kết luận kiểm chéo `[ĐO " + SCRIPT + "]`",
        "",
        f"- **Theo cùng ring ID** (kiểm tra ring id có đúng là Laser ID của "
        f"manual): median `|Δ| = {same_median:.2f}°`, max `{same_max:.2f}°`, "
        f"**{same_count}/{len(stats['present'])}** ring lệch `≥ 0,5°` "
        f"→ **KHÔNG KHỚP**. Chỉ xét {len(stats['stable'])} ring có mặt ở "
        f"≥ 30/60 frame: median `|Δ| = {stable_median:.2f}°`, max "
        f"`{stable_max:.2f}°`, {stable_count}/{len(stats['stable'])} ring "
        "lệch `≥ 0,5°`.",
        f"- Không phải lệch hằng số do nghiêng frame: `Δ cùng ID` trải từ "
        f"`{min(deltas):+.2f}°` đến `{max(deltas):+.2f}°`.",
        f"- **Theo tiêu chí \"góc danh nghĩa gần nhất\"** (đúng chữ của "
        f"ticket): median `|Δ| = {nearest_median:.2f}°` `< 0,5°` ⇒ *khớp về độ "
        f"lớn*, max `{nearest_max:.2f}°` (các ring 27–31 thưa điểm). Nhưng "
        "con số nhỏ này **chỉ vì bảng VLP-32C dày** quanh đường chân trời "
        "(bước ~0,33°), không chứng minh ring id trùng Laser ID: ring `0` "
        f"quan sát `{ring0:.2f}°` nhưng Laser ID `0` danh nghĩa `−25,00°`; "
        f"ring `3` quan sát `{ring3:.2f}°` nhưng Laser ID `3` danh nghĩa "
        "`−15,64°`.",
        f"- **Nếu dùng bảng HDL-32E** (ticket ghi tên cảm biến này): median "
        f"`|Δ| = {hdl_median:.2f}°`, max `{hdl_max:.2f}°`, "
        f"{hdl_count}/{len(stats['present'])} ring lệch `≥ 0,5°` → cũng "
        "**KHÔNG KHỚP**; dataset là VLP-32C theo README.",
        "- **Không sửa bảng góc, không suy ra cảm biến khác.** Kết luận cho "
        "bước ray casting: **không dùng ring id làm góc elevation**; phải tính "
        "`atan2(z, sqrt(x² + y²))` từ toạ độ điểm của chính frame đó.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    stats = common.beam_stats(frames_per_scene=10)
    body = render(stats)
    common.replace_section(SECTION, body)
    print(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
