"""Wet-pavement intensity attenuation for the spray augmentation (ticket 27a).

Source: ``simulate_wet_pavement`` in
``DetectionEnvironmentalEffects.cpp:305-380`` of
``openMSL/sl-1-2-reflection-based-lidar-object-model``, licensed MPL-2.0
(the same reference already used by ``spray/plume.py``).  This is **not** a
port of ``SysCV/LiDAR_snow_sim`` (CC BY-NC 4.0); that repository was only read
for cross-checking, and none of its code is vendored here because its
Attribution-NonCommercial licence is incompatible with a public research
artifact.

What the original does
----------------------
For every existing detection whose ``z`` is within ``0.2 m`` of the road plane:

* if ``y`` is inside ``(2.0, 7.0)`` (the source's hard-coded adjacent-lane
  window) the intensity is replaced by the Hahner et al. (2022) wet-pavement
  model: Fresnel/Snell transmittance through a water film of depth
  ``pavement_depth_m``, eq. 12-19.  The returned value is multiplied by the
  source's ``0.3`` damping constant.
* otherwise (same z band, ``y`` outside the window) intensity is *increased*
  by ``2/255 * 100``; this branch is kept verbatim.

No detection is removed: the source only calls ``set_intensity(...)``.  This
module therefore returns a copy of the cloud (only column 3 may change) and
reports the fraction of intensity that survives instead of a removal count.

Deliberate deviations from the C++ source
-----------------------------------------
* ``Gamma`` is normalised as ``clip(intensity / 255, 0, 1)`` because our column
  3 is raw Velodyne intensity in ``0..255``; the source normalises for its
  ``0..100`` OSI intensity scale.  (The brief marks this as ``[CHỌN]``.)
* ``wfh_mm`` arrives in millimetres from :class:`~spray.plume_context.PlumeContext`;
  the source uses metres.  ``gamma = clip(wfh_mm / 1000 / pavement_depth_m, 0, 1)``
  therefore saturates at ``wfh_mm == 0.5`` (eq. 19).
* At ``wfh_mm == 0`` the result is ``Gamma * 255 * 0.3``, i.e. a 70 % loss.
  That is the source's own constant, not a bug introduced here.

Consequences of the formula: the wet term ``t_p`` is below the dry term
``Gamma``, so increasing the water film *lowers* the surviving intensity;
``gamma`` saturates at ``0.5 mm``, after which ``mean_ratio`` is flat.

The matching config defaults live in ``spray/config/wet_ground_default.yaml``.
Ticket 27b wires this function into the stateful plume pipeline; this module
does not read the YAML or the environment.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = ["WetGroundConfig", "WetGroundStats", "apply_wet_ground"]

# ``dee.cpp`` adds ``2.0 / 255.0 * 100.0`` on its 0-100 intensity scale.  Column
# 3 here is 0-255, and the brief pins this expression verbatim, so it is used
# as-is (it is a ~0.8 count bump on a 0-255 column).
_BOOST_INTENSITY = 2.0 / 255.0 * 100.0


@dataclass(frozen=True)
class WetGroundConfig:
    """Constants of ``simulate_wet_pavement`` (``dee.cpp:305-380``).

    Every field is copied from the C++ source; ``enabled`` is the only switch
    and defaults to ``False`` so the augmentation is off until an experiment
    turns it on.
    """

    z_tolerance_m: float = 0.2
    y_window_m: tuple[float, float] = (2.0, 7.0)
    pavement_depth_m: float = 0.0005
    n_air: float = 1.0003
    n_w: float = 1.33
    intensity_scale: float = 0.3
    enabled: bool = False


@dataclass
class WetGroundStats:
    """What happened to one frame.

    ``points_in`` is the number of points in the pavement z band and equals
    ``attenuated + boosted``.  ``attenuated`` counts the ``y``-window branch and
    ``boosted`` the outside-window branch.  ``mean_ratio`` is the mean of
    ``intensity_out / intensity_in`` over ``points_in`` with a positive input
    intensity; it is ``0.0`` when nothing was processed.
    """

    points_in: int = 0
    attenuated: int = 0
    boosted: int = 0
    mean_ratio: float = 0.0


def apply_wet_ground(
    points: np.ndarray,
    *,
    road_z_m: float,
    wfh_mm: float,
    config: WetGroundConfig | None = None,
) -> tuple[np.ndarray, WetGroundStats]:
    """Attenuate pavement intensities for one ``(N, 5)`` point cloud.

    ``road_z_m`` is the road plane height in the ego frame (``-0.411`` for
    SemanticSpray) and ``wfh_mm`` the water film height in millimetres.  The
    input array is never mutated; the returned array is a copy and only
    column 3 (intensity) differs, clipped to ``[0, 255]``.

    When ``config.enabled`` is false the copy is returned unchanged and all
    stats are zero.  Either way exactly one line is printed::

        WET_GROUND_STATS points_in=<n> attenuated=<n> boosted=<n> mean_ratio=<x.xxx>
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

    road_z = float(road_z_m)
    sensor_height = -road_z
    if sensor_height <= 0.0:
        raise ValueError(
            "road_z_m must be negative (sensor above the road), "
            f"got {road_z}"
        )

    xyz = arr[:, :3].astype(np.float64)
    intensity_in = arr[:, 3].astype(np.float64)

    band = np.abs(xyz[:, 2] - road_z) <= config.z_tolerance_m
    y = xyz[:, 1]
    in_window = band & (y > config.y_window_m[0]) & (y < config.y_window_m[1])
    boost = band & ~in_window

    if in_window.any():
        out[in_window, 3] = _attenuate(
            xyz[in_window],
            intensity_in[in_window],
            sensor_height=sensor_height,
            wfh_mm=float(wfh_mm),
            config=config,
        )
    if boost.any():
        out[boost, 3] = np.clip(
            intensity_in[boost] + _BOOST_INTENSITY, 0.0, 255.0
        )

    ratio_mask = band & (intensity_in > 0.0)
    if ratio_mask.any():
        mean_ratio = float(
            np.mean(out[ratio_mask, 3].astype(np.float64) / intensity_in[ratio_mask])
        )
    else:
        mean_ratio = 0.0

    stats = WetGroundStats(
        points_in=int(band.sum()),
        attenuated=int(in_window.sum()),
        boosted=int(boost.sum()),
        mean_ratio=mean_ratio,
    )
    _print_marker(stats)
    return out, stats


def _attenuate(
    xyz: np.ndarray,
    intensity: np.ndarray,
    *,
    sensor_height: float,
    wfh_mm: float,
    config: WetGroundConfig,
) -> np.ndarray:
    """Wet-pavement model for points already selected by the z/y mask.

    Equations copied from ``dee.cpp:336-373`` (eq. 12-19); ``Gamma`` is
    normalised to the local 0-255 intensity scale, see the module docstring.
    """
    n_air = config.n_air
    n_w = config.n_w

    gamma_r = np.clip(intensity / 255.0, 0.0, 1.0)
    distance = np.linalg.norm(xyz, axis=1)

    a_in = np.arctan(distance / sensor_height)
    cos_in = np.cos(a_in)
    a_aout = np.arcsin(np.clip(np.sin(a_in) * n_air / n_w, -1.0, 1.0))
    cos_aout = np.cos(a_aout)

    # eq. 14, air -> pavement
    t_ap = (2.0 * n_air * cos_in / (n_w * cos_in + n_air * cos_aout)) ** 2
    t_ap = t_ap / (cos_in * n_air / n_w / cos_aout)

    a_wout = np.arcsin(np.clip(np.sin(a_aout) * n_w / n_air, -1.0, 1.0))
    cos_wout = np.cos(a_wout)

    # eq. 13 + 14, water -> air
    r_wp = (
        (n_air * cos_aout - n_w * cos_wout)
        / (n_air * cos_aout + n_w * cos_wout)
    ) ** 2
    t_wp = (2.0 * n_w * cos_aout / (n_air * cos_aout + n_w * cos_wout)) ** 2
    t_wp = t_wp / (cos_aout * n_w / n_air / cos_wout)

    # eq. 16; the denominator is > 0 because gamma_r <= 1 and r_wp < 1.
    t_p = t_ap * gamma_r * t_wp / np.clip(1.0 - gamma_r * r_wp, 1e-12, None)

    gamma = float(
        np.clip(wfh_mm / 1000.0 / config.pavement_depth_m, 0.0, 1.0)
    )
    attenuated = ((1.0 - gamma) * gamma_r + gamma * t_p) * 255.0
    return np.clip(attenuated * config.intensity_scale, 0.0, 255.0)


def _print_marker(stats: WetGroundStats) -> None:
    print(
        "WET_GROUND_STATS "
        f"points_in={stats.points_in} "
        f"attenuated={stats.attenuated} "
        f"boosted={stats.boosted} "
        f"mean_ratio={stats.mean_ratio:.3f}"
    )
