"""Time-varying state of spray clusters: spawn, advect and expire.

The v1 generator rebuilds the plume from scratch every frame, so no cluster has
an age and there is no trail behind the lead vehicle. This module keeps the
clusters alive across frames.

Frames of reference (corrected in ticket 28c):

- clusters carry their velocity in the **ground frame**, not relative to the
  ego. The paper sets the object velocity as the initial cluster velocity and
  the reference implementation advects in world coordinates, rendering into
  the sensor frame only afterwards (``dee.cpp:396-426``, ``:250``).
- drag acts in the ground frame: ``v_air = v_ground - wind``.
- positions live in the **ego frame**: ``pos += (vel - ego_velocity) * dt``.
  The ego is what the LiDAR sees, so this is the render frame.

What makes the trail long is the drag, not the relative speed: ``|v_air|^2``
for a cluster moving at road speed is of order 1300 m^2/s^2, so ``-0.15 * |air|^2``
removes tens of m/s within the first cycles. A cluster spawned while ego and
lead vehicle move at the same speed ends up ~0 relative velocity at birth and
then falls far behind in the ego frame.

Two speeds, two roles:

- ``v_abs`` = ``context.object_speed_mps``, the lead vehicle's speed over the
  road. It drives the number of clusters spawned per cycle and the lifetime
  ``T``: the amount of water thrown up scales with the wet road the tyres cross
  every second.
- the ground velocity is ``object_velocity_ego_mps + [ego_speed, 0, 0]``: the
  object's own velocity carried into the ground frame by the ego's motion.

``wfh_mm`` is in millimetres for both the cluster count and ``T``. Passing
metres by mistake gives a different count on purpose (pinned by a test).

Sign conventions follow the reference implementation
``DetectionEnvironmentalEffects.cpp`` (openMSL/sl-1-2, MPL-2.0):

- clusters spawn with ``age = -dt`` so they are not active on their birth frame;
- ``T ~ N(wfh_mm*0.02*(v_abs_kmh - 50) + 0.2, 0.2)``, clamped at zero;
- drag uses the paper's constant coefficient ``C = -0.15 1/m`` [PAPER] arXiv
  2212.08558, acting as ``v += C * v_air_hat * |v_air|^2 * dt`` with
  ``v_air = v_cluster - wind``. The reference code (``dee.cpp:542``) draws
  ``N(-0.12; 0.04)`` per cluster instead; we deliberately follow the paper and
  default the sampling knobs to a constant.
- a cluster is removed once ``age > 4*T``;
- the displayed survival probability is ``P_t = exp(-age/T)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import numpy as np

from spray.plume import (
    PlumeConfig,
    cluster_rate_for_speed,
    steady_state_cluster_factor,
)

# [CODE] dee.cpp:509-512 and the VLP-32 profile (num_clusters_velocity_offset_kmh).
CLUSTER_COUNT_WFH_COEFF = 0.2
CLUSTER_COUNT_BASE = 0.1
VELOCITY_OFFSET_KMH = 50.0
# [CODE] DetectionEnvironmentalEffects.cpp: activate above 40 km/h and wfh > 0.
ACTIVATION_SPEED_KMH = 40.0
# [CODE] dee.cpp:530 and hpp:47.
LIFETIME_WFH_COEFF = 0.02
LIFETIME_BASE_S = 0.2
LIFETIME_SIGMA_S = 0.2
# [CODE] dee.cpp:446.
MAX_AGE_FACTOR = 4.0
# [ĐO 2026-11-11] Lognormal MLE of ``r_cl`` on the ``cal`` split, per vehicle
# class (``scripts/measure_29ed.py``, ``docs/measurements/29ed-real-distributions.md``).
# The paper's fixed -1.2/0.8 was measured on a VW Crafter with a VLP-32C; on our
# label-2 clusters DBSCAN chains points along scan lines, so the fitted tail is
# heavier (sigma 1.69/1.81) and p99 (~12 m) far exceeds the 1.0 m cap. The cap
# stays because a 12 m sphere is not a plume cluster; the tail is reported, not
# re-created.
RADIUS_MU_BY_CLASS = {"crafter": -0.928, "golf": -0.850}
RADIUS_SIGMA_BY_CLASS = {"crafter": 1.686, "golf": 1.811}
# Fallback for a class without a measurement; still the published profile.
RADIUS_MU = -1.2
RADIUS_SIGMA = 0.8
RADIUS_MAX_M = 1.0
# [ĐO] p95(|y - y_block|) on the real `cal` labels is 2.43 m. Clusters may
# drift sideways with the wind, so the lateral offset from the block centre is
# clamped every step; the paper puts clusters uniformly behind the object and
# does not model lateral drift beyond the measured plume width.
LATERAL_CLAMP_M = 2.43
# [CODE] dee.cpp:540.
INITIAL_VZ_MAX_MPS = 5.0
# [PAPER] arXiv 2212.08558, Sec. III-C: drag coefficient C = -0.15 1/m,
# constant. See the module docstring for how this differs from dee.cpp:542.
DRAG_MEAN = -0.15
DRAG_STD = 0.0
# [CODE] dee.cpp wind: 2 m/s from 208 deg in meteorological convention.
WIND_SPEED_MPS = 2.0
WIND_FROM_DEG = 208.0
# [CODE] profile VLP-32 update_cycle_time.
DEFAULT_DT_S = 0.1

# Placeholder spawn jitter around the sensor origin; 28b replaces it with the
# real block behind the vehicle tail. Only seed determinism matters here.
_SPAWN_JITTER_HALF_M = 0.5


@dataclass(frozen=True)
class PlumeStateConfig:
    """Stochastic knobs of the cluster state, with reference defaults.

    The model constants live in the module; this config only lets tests and
    the caller pin distributions or change the wind. Drag defaults to the
    paper's constant (``drag_std = 0``), but the knobs stay so a caller can
    still sample it.

    ``radius_mu`` / ``radius_sigma`` are keyed by vehicle class: the measured
    ``r_cl`` fits differ between the Crafter and the Golf (ticket 29e-d).
    """

    lifetime_sigma_s: float = LIFETIME_SIGMA_S
    max_age_factor: float = MAX_AGE_FACTOR
    radius_mu: Mapping[str, float] = field(
        default_factory=lambda: dict(RADIUS_MU_BY_CLASS)
    )
    radius_sigma: Mapping[str, float] = field(
        default_factory=lambda: dict(RADIUS_SIGMA_BY_CLASS)
    )
    radius_max_m: float = RADIUS_MAX_M
    initial_vz_max_mps: float = INITIAL_VZ_MAX_MPS
    drag_mean: float = DRAG_MEAN
    drag_std: float = DRAG_STD
    wind_speed_mps: float = WIND_SPEED_MPS
    wind_from_deg: float = WIND_FROM_DEG


@dataclass
class SprayCluster:
    """One cluster with its own position, velocity and age.

    ``pos`` is in the ego (sensor) frame, the frame the LiDAR renders in.
    ``vel`` is in the **ground frame** (m/s): drag and wind live there, and
    the ego velocity is subtracted only when integrating ``pos``.
    """

    pos: np.ndarray
    vel: np.ndarray
    radius: float
    age: float
    ttl: float
    drag: float
    object_id: int
    cluster_id: int
    velocity_assumed: bool = False
    # ``y`` of the spray block centre in the ego frame; the lateral clamp in
    # :meth:`PlumeState.advance` keeps ``|pos[1] - lateral_center_y|`` inside
    # :data:`LATERAL_CLAMP_M`. ``None`` disables the clamp (hand-built clusters
    # in tests).
    lateral_center_y: float | None = None

    def probability(self) -> float:
        """Displayed survival probability ``P_t = exp(-age/T)`` [PAPER] III-C.

        A newborn cluster has ``age = -dt``, so the raw value is slightly above
        one; the displayed probability is clamped to ``[0, 1]``.
        """
        if self.ttl <= 0.0:
            return 0.0
        return float(min(1.0, np.exp(-self.age / self.ttl)))


@dataclass
class PlumeCounters:
    """Counts for the cycle that just ran, for the 28b marker."""

    spawned: int = 0
    alive: int = 0
    expired: int = 0


def cluster_spawn_rate_for_speed_abs(
    v_abs_kmh: float, vehicle_class: str = "crafter"
) -> float:
    """Clusters **spawned per 0.1 s cycle**, from the ``cal`` table (29e).

    ``rate(v) = visible_ref(v) / K(T_ref(v))`` is independent of ``wfh``; the
    humidity only changes how long a cluster lives (through ``T``). Keeping the
    rate fractional matters at low speed: rounding 1.44 to 1 would undershoot
    Golf at 50 km/h by 30 %. :class:`PlumeState` accumulates the fraction over
    frames, so the long-run spawn rate stays exact while each frame still
    spawns an integer number of clusters.
    """
    if v_abs_kmh <= ACTIVATION_SPEED_KMH:
        return 0.0
    return cluster_rate_for_speed(v_abs_kmh, PlumeConfig(), vehicle_class)


def cluster_count_for_speed_abs(
    v_abs_kmh: float, wfh_mm: float, vehicle_class: str = "crafter"
) -> int:
    """Clusters **alive in one frame** at steady state.

    ``visible = round(rate * K(T(wfh, v)))`` — the same table as
    :func:`spray.plume.visible_cluster_count_for_speed`, so the stateful path
    and the per-frame generator report the same number. The lifetime ``T`` is
    unchanged (``[CODE] dee.cpp:530``). ``wfh_mm`` is in millimetres.
    """
    if v_abs_kmh <= ACTIVATION_SPEED_KMH or wfh_mm <= 0.0:
        return 0
    rate = cluster_spawn_rate_for_speed_abs(v_abs_kmh, vehicle_class)
    if rate <= 0.0:
        return 0
    config = PlumeConfig(water_film_height_m=wfh_mm / 1000.0)
    visible = rate * steady_state_cluster_factor(v_abs_kmh, config)
    return int(np.floor(visible + 0.5))


def lifetime_mean_s(v_abs_kmh: float, wfh_mm: float) -> float:
    """Mean lifetime ``T = 0.02*wfh_mm*(v_abs_kmh - 50) + 0.2`` seconds."""
    return (
        LIFETIME_WFH_COEFF * wfh_mm * (v_abs_kmh - VELOCITY_OFFSET_KMH)
        + LIFETIME_BASE_S
    )


def wind_vector(config: PlumeStateConfig | None = None) -> np.ndarray:
    """Wind velocity in the ego frame, forward horizontal plane only.

    Meteorological direction 208 deg is where the wind blows *from*, so the
    velocity points toward 28 deg. Assuming ``+x`` east and ``+y`` north.
    """
    cfg = config or PlumeStateConfig()
    heading_from = np.deg2rad(cfg.wind_from_deg)
    east = -cfg.wind_speed_mps * np.sin(heading_from)
    north = -cfg.wind_speed_mps * np.cos(heading_from)
    return np.array([east, north, 0.0], dtype=np.float64)


class PlumeState:
    """Clusters keyed by ``(scene_token, object_id)``, reset per scene."""

    def __init__(self, config: PlumeStateConfig | None = None) -> None:
        self._config = config or PlumeStateConfig()
        self._clusters: dict[tuple[str, int], list[SprayCluster]] = {}
        self._spawn_credit: dict[tuple[str, int], float] = {}
        self._scene_token: str | None = None
        self._next_cluster_id = 0
        self._counters = PlumeCounters()

    @property
    def counters(self) -> PlumeCounters:
        return self._counters

    @property
    def wind(self) -> np.ndarray:
        return wind_vector(self._config)

    def spawn(
        self,
        context,
        *,
        object_id: int,
        rng: np.random.Generator,
        dt: float = DEFAULT_DT_S,
        center: np.ndarray | None = None,
        extents: np.ndarray | None = None,
        config: PlumeStateConfig | None = None,
        vehicle_class: str = "crafter",
    ) -> list[SprayCluster]:
        """Spawn this cycle's clusters for one object.

        ``n`` follows the measured ``cal`` table (ticket 29e): the per-cycle
        rate is fractional and carried over through ``_spawn_credit`` so the
        long-run number of live clusters matches the table. ``T`` still uses
        ``v_abs`` (``object_speed_mps``). The initial velocity is the
        **ground** velocity: ``object_velocity_ego_mps`` plus the ego velocity
        ``[ego_speed_mps, 0, 0]``. When the caller did not supply the object
        velocity, it falls back to the object moving along ``+x`` in the ego
        frame at spawn time, so ``v_ground = [object_speed_mps, 0, 0]``, and
        the cluster is flagged ``velocity_assumed``. ``age`` starts one cycle
        behind so the cluster is inactive on its birth frame.

        ``center`` and ``extents`` describe the spray block (centre and half
        sizes in metres); positions are uniform inside it. Passing ``None``
        keeps the 28a placeholder jitter around the sensor origin.
        """
        cfg = config or self._config
        if config is not None:
            self._config = config

        if context.scene_token != self._scene_token:
            self._clusters.clear()
            self._spawn_credit.clear()
            self._scene_token = context.scene_token
            self._next_cluster_id = 0
            self._counters = PlumeCounters()

        v_abs_kmh = context.object_speed_mps * 3.6
        rate = cluster_spawn_rate_for_speed_abs(v_abs_kmh, vehicle_class)
        credit_key = (context.scene_token, object_id)
        credit = self._spawn_credit.get(credit_key, 0.0) + rate
        count = int(np.floor(credit + 1e-9))
        self._spawn_credit[credit_key] = credit - count
        mean_ttl = lifetime_mean_s(v_abs_kmh, context.wfh_mm)
        origin = np.asarray(context.sensor_origin, dtype=np.float64)

        ego_velocity = np.array(
            [context.ego_speed_mps, 0.0, 0.0], dtype=np.float64
        )
        velocity = context.object_velocity_ego_mps
        if velocity is None:
            base_vel = np.array(
                [context.object_speed_mps, 0.0, 0.0], dtype=np.float64
            )
            velocity_assumed = True
        else:
            base_vel = np.asarray(velocity, dtype=np.float64) + ego_velocity
            velocity_assumed = False

        if (center is None) != (extents is None):
            raise ValueError("center and extents must be provided together")
        if center is not None:
            block_center = _vec3("center", center)
            block_extents = _vec3("extents", extents)

        bucket = self._clusters.setdefault(
            (context.scene_token, object_id), []
        )
        lateral_center = (
            float(block_center[1]) if center is not None else float(origin[1])
        )
        created: list[SprayCluster] = []
        class_key = vehicle_class.lower()
        radius_mu = float(cfg.radius_mu.get(class_key, RADIUS_MU))
        radius_sigma = float(cfg.radius_sigma.get(class_key, RADIUS_SIGMA))
        for _ in range(count):
            radius = min(
                cfg.radius_max_m,
                float(np.exp(rng.normal(radius_mu, radius_sigma))),
            )
            ttl = max(
                0.0, float(rng.normal(mean_ttl, cfg.lifetime_sigma_s))
            )
            drag = float(rng.normal(cfg.drag_mean, cfg.drag_std))
            vz = float(rng.uniform(0.0, cfg.initial_vz_max_mps))
            if center is None:
                pos = origin + rng.uniform(
                    -_SPAWN_JITTER_HALF_M, _SPAWN_JITTER_HALF_M, size=3
                )
            else:
                pos = block_center + rng.uniform(-1.0, 1.0, size=3) * block_extents
            vel = base_vel.copy()
            vel[2] += vz
            cluster = SprayCluster(
                pos=pos,
                vel=vel,
                radius=radius,
                age=-dt,
                ttl=ttl,
                drag=drag,
                object_id=object_id,
                cluster_id=self._next_cluster_id,
                velocity_assumed=velocity_assumed,
                lateral_center_y=lateral_center,
            )
            self._next_cluster_id += 1
            bucket.append(cluster)
            created.append(cluster)

        self._counters.spawned = len(created)
        self._counters.expired = 0
        self._counters.alive = self._total_alive()
        return created

    def advance(
        self, dt: float, ego_velocity: np.ndarray | None = None
    ) -> None:
        """Advect every cluster with drag and wind, then age it by ``dt``.

        Drag is applied in the ground frame (``vel`` is a ground velocity).
        Positions are integrated in the ego frame, so the ego velocity is
        subtracted there: a cluster keeping its ground speed falls behind at
        ``|vel - ego_velocity|``. ``ego_velocity`` defaults to zero so callers
        that do not model ego motion get the 28a behaviour.

        Drag may only dissipate air speed. At road speed ``|v_air|^2`` is of
        order 1000 m^2/s^2, so a positive ``drag`` (the default is the paper's
        constant ``-0.15``, but the config can pin any value) would otherwise
        grow as ``v' = +c*v^2`` and reach inf inside one cluster lifetime. The
        guard skips the update in that case; for every dissipative value the
        formula is unchanged.
        """
        wind = self.wind
        if ego_velocity is None:
            ego_velocity = np.zeros(3, dtype=np.float64)
        else:
            ego_velocity = np.asarray(ego_velocity, dtype=np.float64)
        for clusters in self._clusters.values():
            for cluster in clusters:
                air = cluster.vel - wind
                air_speed = float(np.linalg.norm(air))
                if air_speed > 0.0:
                    speed_after = air_speed + cluster.drag * air_speed**2 * dt
                    if speed_after < air_speed:
                        cluster.vel = cluster.vel + (
                            cluster.drag
                            * (air / air_speed)
                            * (air_speed**2)
                            * dt
                        )
                cluster.pos = cluster.pos + (cluster.vel - ego_velocity) * dt
                if cluster.lateral_center_y is not None:
                    cluster.pos[1] = np.clip(
                        cluster.pos[1],
                        cluster.lateral_center_y - LATERAL_CLAMP_M,
                        cluster.lateral_center_y + LATERAL_CLAMP_M,
                    )
                cluster.age += dt
        self._counters.alive = self._total_alive()

    def prune(
        self, ceilings: dict[int, float] | None = None
    ) -> int:
        """Remove expired clusters and clusters that rose above the block.

        Two rules: ``age > max_age_factor * T`` (``[CODE] dee.cpp:445-450``)
        and, when ``ceilings`` is given, ``pos[2] > ceiling[object_id]``. The
        second rule bounds the tail block geometrically: a cluster with
        ``initial_vz`` up to 5 m/s and no gravity would otherwise drift far
        above the vehicle (ticket 29e measured h p95 3.216 m against a real
        2.264 m) instead of dissolving inside the plume.
        """
        removed = 0
        for key, clusters in list(self._clusters.items()):
            object_id = key[1]
            ceiling = None if ceilings is None else ceilings.get(object_id)
            kept = []
            for cluster in clusters:
                expired = cluster.age > self._config.max_age_factor * cluster.ttl
                above = ceiling is not None and cluster.pos[2] > ceiling
                if expired or above:
                    removed += 1
                else:
                    kept.append(cluster)
            self._clusters[key] = kept
        self._counters.expired = removed
        self._counters.alive = self._total_alive()
        return removed

    def alive(self, object_id: int) -> list[SprayCluster]:
        """Clusters currently alive for one object in the active scene."""
        key = (self._scene_token, object_id)
        return list(self._clusters.get(key, []))

    def all_alive(self) -> list[SprayCluster]:
        """Every live cluster in the active scene, across all objects."""
        return [
            cluster
            for clusters in self._clusters.values()
            for cluster in clusters
        ]

    def _total_alive(self) -> int:
        return sum(len(clusters) for clusters in self._clusters.values())


def _vec3(field: str, value) -> np.ndarray:
    array = np.asarray(value, dtype=np.float64)
    if array.shape != (3,):
        raise ValueError(f"{field} must have shape (3,), got {array.shape}")
    if not np.isfinite(array).all():
        raise ValueError(f"{field} must be finite")
    return array
