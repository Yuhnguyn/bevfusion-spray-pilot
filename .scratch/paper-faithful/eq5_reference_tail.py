"""Theo Eq.5-6 của paper (ground frame), cụm phải bị xe BỎ LẠI bao xa?

NotebookLM xác nhận:
  Eq.5: v_cl,k = C·(v_w + v_cl,k-1)²·Δt + v_cl,k-1      C = -0,15 m⁻¹
  Eq.6: p_cl,k = p_cl,k-1 + Δt·v_cl,k
  v0 = vận tốc vật thể; hệ quy chiếu = ground (suy ra từ ngữ cảnh)
  "clusters first move in the direction of the moving object, then decelerate
   due to air resistance"

Vậy trong ground frame, cụm chậm dần còn xe giữ tốc độ ⇒ khoảng cách depth tăng.
Script này tính depth(t) theo ĐÚNG Eq.5-6, rồi so với:
  - generator hiện tại (p50 = 2,5 m @100 km/h)
  - RoadSpray thật (p50 = 17,5 m @100 km/h, dải car 20-40 m)

Nếu Eq.5-6 cho depth ≈ 17-20 m thì generator SAI khi cài đặt, không phải paper sai.
"""
from __future__ import annotations

import numpy as np

C = -0.15          # [PAPER] m⁻¹
DT = 0.1           # [PAPER] 100 ms
WIND_SPEED = 2.0   # [CODE] dee.cpp, paper không nêu số
WIND_FROM_DEG = 208.0


def simulate(speed_kmh: float, ttl: float, horizon: float = 6.0,
             wind: np.ndarray | None = None) -> list[tuple[float, float, float]]:
    """Trả [(t, depth_so_voi_duoi_xe, |p| tu ego)] theo Eq.5-6, ground frame.

    Ego đứng yên tại gốc (kịch bản static). Xe sinh spray ở car_x ban đầu,
    chạy theo +x với `speed_kmh`. Cụm sinh tại đuôi xe với v0 = vận tốc xe.
    """
    v_obj = speed_kmh / 3.6
    car_x = 24.0                      # vị trí xe lúc sinh (dải thật 20-40 m)
    rear0 = car_x - 6.829 / 2.0
    if wind is None:
        # [CODE] dee.cpp: 2 m/s from 208 deg (meteorological)
        rad = np.deg2rad(270.0 - WIND_FROM_DEG)
        wind = np.array([WIND_SPEED * np.cos(rad), WIND_SPEED * np.sin(rad), 0.0])
    vel = np.array([v_obj, 0.0, 0.0])   # [PAPER] v0 = vận tốc vật thể
    pos = np.array([rear0, 0.0, 0.0])   # sinh ngay sau mặt đuôi
    out = []
    n = int(round(horizon / DT))
    for k in range(1, n + 1):
        rel = vel - wind                # vận tốc tương đối với không khí
        rel_speed = float(np.linalg.norm(rel))
        if rel_speed > 1e-9:
            # Eq.5: cập nhật vận tốc; số hạng cản ngược chiều vận tốc tương đối
            accel = C * rel_speed**2
            vel = vel + accel * (rel / rel_speed) * DT
        # Eq.6: cập nhật vị trí
        pos = pos + DT * vel
        t = k * DT
        car_x_now = car_x + v_obj * t
        rear_now = car_x_now - 6.829 / 2.0
        depth = rear_now - pos[0]
        rng = float(np.linalg.norm(pos))
        # trọng số sống sót P_t = exp(-t/T)
        out.append((t, depth, rng, float(np.exp(-t / ttl))))
    return out


def weighted_q(rows, q: float, key: int) -> float:
    """Quantile có trọng số P_t — mô phỏng phân bố tuổi ở trạng thái dừng."""
    d = np.array([r[key] for r in rows])
    w = np.array([r[3] for r in rows])
    o = np.argsort(d)
    d, w = d[o], w[o]
    c = np.cumsum(w) / w.sum()
    return float(d[np.searchsorted(c, q / 100.0)])


def main() -> None:
    print("Eq.5-6 của paper, ground frame. Cụm sinh ở đuôi xe @ car_x = 24 m.\n")
    print(f"{'km/h':>5} {'T(s)':>6} {'depth p50':>10} {'depth p95':>10} "
          f"{'|p| p50':>9} {'|p| p95':>9}")
    print("-" * 58)
    for speed in (50, 100, 130):
        ttl = 0.02 * 1.0 * (speed - 50) + 0.2   # wfh = 1 mm
        rows = simulate(speed, ttl, horizon=8.0)
        print(f"{speed:>5} {ttl:>6.2f} {weighted_q(rows, 50, 1):>10.1f} "
              f"{weighted_q(rows, 95, 1):>10.1f} "
              f"{weighted_q(rows, 50, 2):>9.1f} {weighted_q(rows, 95, 2):>9.1f}")
    print()
    print("Đích RoadSpray thật (dải car [20,40)), p50/p95 của depth:")
    print("   50 km/h:  0,5 /  6,5 m")
    print("  100 km/h: 17,5 / 26,5 m")
    print("  130 km/h: 20,5 / 29,5 m")
    print()
    print("Generator hiện tại (gen_static, cùng dải), p50/p95:")
    print("   50 km/h:  0,5 /  1,5 m")
    print("  100 km/h:  2,5 /  9,5 m")
    print("  130 km/h:  3,5 /  9,5 m")


if __name__ == "__main__":
    main()
