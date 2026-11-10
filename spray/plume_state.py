"""Time-varying state of spray clusters: spawn, advect and expire.

The v1 generator rebuilds the plume from scratch every frame, so no cluster has
an age and there is no trail behind the lead vehicle. This module keeps the
clusters alive across frames.

Two speeds, two roles (decision logged 2026-11-10):

- ``v_abs`` = ``context.object_speed_mps``, the lead vehicle's speed over the
  road. It drives the number of clusters spawned per cycle and the lifetime
  ``T``: the amount of water thrown up scales with the wet road the tyres cross
  every second.
- ``v_rel`` = ``object_speed_mps - ego_speed_mps``, the relative speed. It is
  the initial cluster velocity and the velocity advected by drag: what is seen
  moving in the point cloud is motion in the ego frame.

``wfh_mm`` is in millimetres for both the cluster count and ``T``. Passing
metres by mistake gives a different count on purpose (pinned by a test).

Sign conventions follow the reference implementation
``DetectionEnvironmentalEffects.cpp`` (openMSL/sl-1-2, MPL-2.0):

- clusters spawn with ``age = -dt`` so they are not active on their birth frame;
- ``T ~ N(wfh_mm*0.02*(v_abs_kmh - 50) + 0.2, 0.2)``, clamped at zero;
- drag ``N(-0.12, 0.04)`` acts as ``v += drag * v_air_hat * |v_air|^2 * dt``
  with ``v_air = v_cluster - wind``;
- a cluster is removed once ``age > 4*T``;
- the displayed survival probability is ``P_t = exp(-age/T)``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

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
# [CODE] dee.cpp:531.
RADIUS_MU = -1.2
RADIUS_SIGMA = 0.8
RADIUS_MAX_M = 1.0
# [CODE] dee.cpp:540 and :542.
INITIAL_VZ_MAX_MPS = 5.0
DRAG_MEAN = -0.12
DRAG_STD = 0.04
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
    the caller pin distributions (``sigma = 0``) or change the wind.
    """

    lifetime_sigma_s: float = LIFETIME_SIGMA_S
    max_age_factor: float = MAX_AGE_FACTOR
    radius_mu: float = RADIUS_MU
    radius_sigma: float = RADIUS_SIGMA
    radius_max_m: float = RADIUS_MAX_M
    initial_vz_max_mps: float = INITIAL_VZ_MAX_MPS
    drag_mean: float = DRAG_MEAN
    drag_std: float = DRAG_STD
    wind_speed_mps: float = WIND_SPEED_MPS
    wind_from_deg: float = WIND_FROM_DEG


@dataclass
class SprayCluster:
    """One cluster with its own position, velocity and age."""

    pos: np.ndarray
    vel: np.ndarray
    radius: float
    age: float
    ttl: float
    drag: float
    object_id: int
    cluster_id: int

    def probability(self) -> float:
        """Displayed survival probability ``P_t = exp(-age/T)`` [PAPER] III-C."""
        if self.ttl <= 0.0:
            return 0.0
        return float(np.exp(-self.age / self.ttl))


@dataclass
class PlumeCounters:
    """Counts for the cycle that just ran, for the 28b marker."""

    spawned: int = 0
    alive: int = 0
    expired: int = 0


def cluster_count_for_speed_abs(v_abs_kmh: float, wfh_mm: float) -> int:
    """Clusters spawned per cycle from the absolute (road) speed.

    ``mean = (0.2*wfh_mm + 0.1)*(v_abs_kmh - 50)``, then
    ``n = round(max(0, mean))``. Deterministic, no Poisson draw. ``wfh_mm`` is
    in millimetres; the 40 km/h activation threshold is separate from the
    50 km/h offset.
    """
    if v_abs_kmh <= ACTIVATION_SPEED_KMH or wfh_mm <= 0.0:
        return 0
    mean = (CLUSTER_COUNT_WFH_COEFF * wfh_mm + CLUSTER_COUNT_BASE) * (
        v_abs_kmh - VELOCITY_OFFSET_KMH
    )
    if mean <= 0.0:
        return 0
    return int(np.floor(mean + 0.5))


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
        config: PlumeStateConfig | None = None,
    ) -> list[SprayCluster]:
        """Spawn this cycle's clusters for one object.

        ``n`` and ``T`` use ``v_abs`` (``object_speed_mps``); the initial
        velocity uses ``v_rel = object_speed_mps - ego_speed_mps``. ``age``
        starts one cycle behind so the cluster is inactive on its birth frame.
        """
        cfg = config or self._config
        if config is not None:
            self._config = config

        if context.scene_token != self._scene_token:
            self._clusters.clear()
            self._scene_token = context.scene_token
            self._next_cluster_id = 0
            self._counters = PlumeCounters()

        v_abs_kmh = context.object_speed_mps * 3.6
        v_rel = context.object_speed_mps - context.ego_speed_mps
        count = cluster_count_for_speed_abs(v_abs_kmh, context.wfh_mm)
        mean_ttl = lifetime_mean_s(v_abs_kmh, context.wfh_mm)
        origin = np.asarray(context.sensor_origin, dtype=np.float64)

        bucket = self._clusters.setdefault(
            (context.scene_token, object_id), []
        )
        created: list[SprayCluster] = []
        for _ in range(count):
            radius = min(
                cfg.radius_max_m,
                float(np.exp(rng.normal(cfg.radius_mu, cfg.radius_sigma))),
            )
            ttl = max(
                0.0, float(rng.normal(mean_ttl, cfg.lifetime_sigma_s))
            )
            drag = float(rng.normal(cfg.drag_mean, cfg.drag_std))
            vz = float(rng.uniform(0.0, cfg.initial_vz_max_mps))
            pos = origin + rng.uniform(
                -_SPAWN_JITTER_HALF_M, _SPAWN_JITTER_HALF_M, size=3
            )
            cluster = SprayCluster(
                pos=pos,
                vel=np.array([v_rel, 0.0, vz], dtype=np.float64),
                radius=radius,
                age=-dt,
                ttl=ttl,
                drag=drag,
                object_id=object_id,
                cluster_id=self._next_cluster_id,
            )
            self._next_cluster_id += 1
            bucket.append(cluster)
            created.append(cluster)

        self._counters.spawned = len(created)
        self._counters.expired = 0
        self._counters.alive = self._total_alive()
        return created

    def advance(self, dt: float) -> None:
        """Advect every cluster with drag and wind, then age it by ``dt``."""
        wind = self.wind
        for clusters in self._clusters.values():
            for cluster in clusters:
                air = cluster.vel - wind
                air_speed = float(np.linalg.norm(air))
                if air_speed > 0.0:
                    cluster.vel = cluster.vel + (
                        cluster.drag
                        * (air / air_speed)
                        * (air_speed**2)
                        * dt
                    )
                cluster.pos = cluster.pos + cluster.vel * dt
                cluster.age += dt
        self._counters.alive = self._total_alive()

    def prune(self) -> int:
        """Remove clusters with ``age > max_age_factor * T``; return how many."""
        removed = 0
        for key, clusters in list(self._clusters.items()):
            kept = []
            for cluster in clusters:
                if cluster.age > self._config.max_age_factor * cluster.ttl:
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

    def _total_alive(self) -> int:
        return sum(len(clusters) for clusters in self._clusters.values())
