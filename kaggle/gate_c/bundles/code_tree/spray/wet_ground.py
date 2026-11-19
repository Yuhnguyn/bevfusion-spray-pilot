"""Wet-pavement return attenuation for the spray augmentation.

Paper method
------------
This is a port of the wet-ground model of Hahner et al. (2022), "LiDAR Snowfall
Simulation for 3D Object Detection", arXiv 2203.15118, section 3.1 and
Algorithm 2 -- the same model Linnhoff et al. (2022) use for the wet road
surface.  The previous version of this module ported
``simulate_wet_pavement`` from ``openMSL/.../DetectionEnvironmentalEffects.cpp``
instead, which is a *different* reference implementation and is not what the
paper does.  That port is gone.

For every point ``p`` whose distance to the road plane ``|p . w - h|`` is below
``epsilon_g`` the model rebuilds the intensity that would come back from a thin
water film of depth ``d_w`` on pavement of depth ``d_p``:

* Eq. 12 (Snell): ``sin(alpha_out) = n_air / n_water * sin(alpha_in)``.
* Eq. 13-14 (Fresnel, both polarizations ``p in {perp, par}``)::

      R_k^p = (r_k^p)^2
      T_k^p = (n_in cos a_in) / (n_out cos a_out) * (t_k^p)^2

  with the amplitudes for the air -> water and water -> air transitions.
* Eq. 15-16 (geometric series of the rays bouncing inside the film)::

      T_total^p = T_air^p * rho0 * T_water^p
                  * sum_k (rho0 * R_water^p)^k
                = T_air^p * rho0 * T_water^p / (1 - rho0 * R_water^p)

* Eq. 17: ``T_total = max(T_total^par, T_total^perp)``.
* Eq. 19 (gamma) and Eq. 20 (weighting dry and wet reflectivities)::

      gamma = clip(d_w / d_p, 0, 1)
      rho_w = (1 - gamma) * rho0 + gamma * T_total / cos(alpha_in)

* Algorithm 2 keeps the point only when the rebuilt intensity is above the
  sensor noise floor ``i_n(R_0)``; otherwise the point is *lost*.

[CHỌN] assumptions caused by the missing sensor model
------------------------------------------------------
The paper estimates the dry reflectivity ``rho0`` per point from the raw
intensity with Eq. 18, ``rho0 = i / (cos(alpha_in) * P(R_0))``, and rebuilds the
intensity as ``i = rho_w * cos(alpha_in) * P_T(R_0)``.  ``P_T`` is the
power-range response of the specific sensor and is not published for the
VLP-32C of SemanticSpray, so it cannot be evaluated here.  We therefore work
with the wet/dry ratio and keep the 0-255 scale:

    ratio = i_out / i_in = rho_w / rho0_dry

``rho0_dry`` is approximated by the observed intensity normalised to ``[0, 1]``
(``clip(i_in / 255, 0, 1)``), which is the only reflectance estimate available
without ``P(R_0)``.  Substituting Eq. 20 gives

    ratio = (1 - gamma) + gamma * T_total / (rho0 * cos(alpha_in))

and ``T_total = rho0 * (t_aw * t_wa)^2 / (1 - rho0 * R_water)``, so the
``rho0`` of the numerator cancels and only the multiple-reflection denominator
keeps it.  We **drop the remaining ``1 / cos(alpha_in)`` factor**.  It comes
from turning the reflectivity ``rho_w`` back into a measured intensity, but
``T_air * T_water = (t_aw * t_wa)^2`` is a power fraction, not a radiance:
dividing it by ``cos(alpha_in)`` makes the ratio exceed 1 at grazing incidence
for bright road points, i.e. it would *increase* the intensity (up to ~8x at
89 deg, measured), which contradicts the paper's own observation that wet
roads cause "significant amounts of lost ground points" and the repo's
measured requirement that pavement returns must not be boosted.  The final
ratio is therefore::

    ratio = (1 - gamma) + gamma * (t_aw * t_wa)^2 / (1 - rho0 * R_water)

For ``gamma = 0`` this is exactly 1 (dry road, intensity unchanged); for
``gamma = 1`` it is a number in ``(0, 1)`` that decreases with the incidence
angle, so grazing road points lose more than close ones -- the monotonicity the
Fresnel equations are supposed to produce.

Intensity is rebuilt as ``i_out = clip(i_in * ratio, 0, 255)``.  A point is
removed when ``i_out <= intensity_floor`` and ``i_in > 0``; the paper's
``i_n(R_0)`` noise floor is not available, so ``intensity_floor`` defaults to
``0`` and no point is removed unless the caller supplies a threshold.

The matching config defaults live in ``spray/config/wet_ground_default.yaml``.
This module does not read the YAML or the environment; ``plume.py`` owns the
wiring and only forwards ``road_z_m`` / ``wfh_mm`` from
:class:`~spray.plume_context.PlumeContext`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["WetGroundConfig", "WetGroundStats", "apply_wet_ground"]

# Road plane normal ``w`` of Algorithm 2, in the ego frame (z up).
_ROAD_NORMAL = np.array([0.0, 0.0, 1.0])
# Column 3 is raw Velodyne intensity in 0..255; the dry reflectivity proxy
# normalises by this range.
_INTENSITY_SCALE = 255.0


@dataclass(frozen=True)
class WetGroundConfig:
    """Parameters of Hahner et al. (2022), Algorithm 2.

    ``epsilon_g_m``, ``pavement_depth_m``, ``n_air`` and ``n_water`` are the
    values used by the paper (``epsilon_g = 0.5 m``, ``d_p = 1.2 mm``,
    ``n_air = 1.0003``, ``n_water = 1.33``).  ``water_film_mm`` is the ``d_w``
    default consulted when :func:`apply_wet_ground` is called without
    ``wfh_mm``.  ``intensity_floor`` replaces the paper's ``i_n(R_0)`` noise
    floor; the default of ``0`` keeps every point.
    """

    enabled: bool = False
    epsilon_g_m: float = 0.5
    pavement_depth_m: float = 0.0012
    water_film_mm: float = 0.0
    n_air: float = 1.0003
    n_water: float = 1.33
    intensity_floor: float = 0.0


@dataclass
class WetGroundStats:
    """What happened to one frame.

    ``points_in`` is the number of points inside the road band
    ``|p . w - h| < epsilon_g``.  ``points_removed`` counts the points dropped
    because their rebuilt intensity fell to ``intensity_floor`` or below.
    ``mean_ratio`` is the mean of ``i_out / i_in`` over the in-band points with
    positive input intensity (``0.0`` when nothing was processed) and
    ``mean_alpha_deg`` the mean incidence angle in degrees over the same band.
    """

    points_in: int = 0
    points_removed: int = 0
    mean_ratio: float = 0.0
    mean_alpha_deg: float = 0.0


def apply_wet_ground(
    points: np.ndarray,
    *,
    road_z_m: float,
    wfh_mm: float | None = None,
    config: WetGroundConfig | None = None,
) -> tuple[np.ndarray, WetGroundStats]:
    """Attenuate pavement returns for one ``(N, 5)`` point cloud.

    ``road_z_m`` is the road plane intercept ``h`` in the ego frame and
    ``wfh_mm`` the water film depth ``d_w`` in millimetres; when ``wfh_mm`` is
    ``None`` the config's ``water_film_mm`` is used.  The input array is never
    mutated.  The returned array is a copy with only column 3 (intensity)
    changed in the road band, except for points removed by a non-zero
    ``intensity_floor``, which disappear from it.

    When ``config.enabled`` is false the copy is returned unchanged and all
    stats are zero.  Either way exactly one line is printed::

        WET_GROUND_STATS points_in=<n> removed=<n> mean_ratio=<x.xxx> mean_alpha_deg=<x.x>
    """
    config = config or WetGroundConfig()
    arr = np.asarray(points)
    if arr.ndim != 2 or arr.shape[1] != 5:
        raise ValueError(f"points must have shape (N, 5), got {arr.shape}")

    out = arr.copy()

    if not config.enabled:
        stats = WetGroundStats()
        _print_marker(stats)
        return out, stats

    film_mm = config.water_film_mm if wfh_mm is None else float(wfh_mm)
    xyz = arr[:, :3].astype(np.float64)
    intensity_in = arr[:, 3].astype(np.float64)

    plane_distance = np.abs(xyz @ _ROAD_NORMAL - float(road_z_m))
    band = plane_distance < config.epsilon_g_m

    gamma = _gamma(film_mm, config)
    intensity_out = intensity_in.copy()
    alpha_deg = np.zeros(arr.shape[0], dtype=np.float64)

    if band.any():
        p = xyz[band]
        norm = np.clip(np.linalg.norm(p, axis=1), 1e-12, None)
        cos_alpha = np.clip(
            np.abs(p @ _ROAD_NORMAL) / (norm * np.linalg.norm(_ROAD_NORMAL)),
            0.0,
            1.0,
        )
        alpha_deg[band] = np.degrees(np.arccos(cos_alpha))

        rho0 = np.clip(intensity_in[band] / _INTENSITY_SCALE, 0.0, 1.0)
        ratio = (1.0 - gamma) + gamma * _wet_dry_ratio(cos_alpha, rho0, config)
        ratio = np.clip(ratio, 0.0, 1.0)
        intensity_out[band] = np.clip(
            intensity_in[band] * ratio, 0.0, _INTENSITY_SCALE
        )

    out[:, 3] = intensity_out.astype(out.dtype)

    removed = band & (intensity_in > 0.0) & (intensity_out <= config.intensity_floor)
    ratio_mask = band & (intensity_in > 0.0)
    mean_ratio = (
        float(np.mean(intensity_out[ratio_mask] / intensity_in[ratio_mask]))
        if ratio_mask.any()
        else 0.0
    )

    stats = WetGroundStats(
        points_in=int(band.sum()),
        points_removed=int(removed.sum()),
        mean_ratio=mean_ratio,
        mean_alpha_deg=float(np.mean(alpha_deg[band])) if band.any() else 0.0,
    )

    if removed.any():
        out = out[~removed]

    _print_marker(stats)
    return out, stats


def _gamma(film_mm: float, config: WetGroundConfig) -> float:
    """Eq. 19: water depth as a fraction of the pavement thread depth."""

    if config.pavement_depth_m <= 0.0:
        return 0.0
    return float(
        np.clip(film_mm / 1000.0 / config.pavement_depth_m, 0.0, 1.0)
    )


def _wet_dry_ratio(
    cos_alpha: np.ndarray,
    rho0: np.ndarray,
    config: WetGroundConfig,
) -> np.ndarray:
    """``T_total / rho0`` of Eq. 15-17, i.e. the wet/dry returned-power ratio.

    ``T_air^p * T_water^p = (t_aw^p * t_wa^p)^2`` because the ``n cos``
    prefactors of Eq. 14 cancel between the two crossings, so only the Fresnel
    amplitudes and the multiple-reflection denominator remain.  The larger
    polarization is returned (Eq. 17).
    """

    n_air = config.n_air
    n_water = config.n_water
    ca = cos_alpha
    sin_out = np.clip(
        n_air / n_water * np.sqrt(np.clip(1.0 - ca * ca, 0.0, 1.0)), -1.0, 1.0
    )
    cw = np.sqrt(np.clip(1.0 - sin_out * sin_out, 0.0, 1.0))

    # Perpendicular polarization, air -> water then water -> air.
    t_aw_perp = 2.0 * n_air * ca / (n_air * ca + n_water * cw)
    t_wa_perp = 2.0 * n_water * cw / (n_water * cw + n_air * ca)
    r_wa_perp = (n_water * cw - n_air * ca) / (n_water * cw + n_air * ca)

    # Parallel polarization.
    t_aw_par = 2.0 * n_air * ca / (n_water * ca + n_air * cw)
    t_wa_par = 2.0 * n_water * cw / (n_air * cw + n_water * ca)
    r_wa_par = (n_air * cw - n_water * ca) / (n_air * cw + n_water * ca)

    # Eq. 15-16 with the dry reflectivity factored out of T_total.
    ratio_perp = (t_aw_perp * t_wa_perp) ** 2 / np.clip(
        1.0 - rho0 * r_wa_perp**2, 1e-12, None
    )
    ratio_par = (t_aw_par * t_wa_par) ** 2 / np.clip(
        1.0 - rho0 * r_wa_par**2, 1e-12, None
    )
    return np.maximum(ratio_perp, ratio_par)


def _print_marker(stats: WetGroundStats) -> None:
    print(
        "WET_GROUND_STATS "
        f"points_in={stats.points_in} "
        f"removed={stats.points_removed} "
        f"mean_ratio={stats.mean_ratio:.3f} "
        f"mean_alpha_deg={stats.mean_alpha_deg:.1f}"
    )
