"""Ticket 29e-d: per-class radius and P_det measured on `cal`.

The paper numbers (r_cl lognormal -1.2/0.8, P_det lognormal -2.3/1.09) were
measured on a VW Crafter with a VLP-32C. Ticket 29e-d replaces them with the
fits measured on our own ``cal`` split, one set per vehicle class.
"""

import numpy as np
import pytest

from spray.plume_context import PlumeContext
from spray.plume_state import (
    RADIUS_MU_BY_CLASS,
    RADIUS_SIGMA_BY_CLASS,
    PlumeState,
    PlumeStateConfig,
)
from spray.raycast import (
    P_DET_MU_BY_CLASS,
    P_DET_SIGMA_BY_CLASS,
    p_det_params_for_class,
)


def _context():
    return PlumeContext(
        scene_token="scene-0001",
        frame_index=0,
        epoch=0,
        sensor_origin=np.array([0.0, 0.0, 1.8], dtype=np.float64),
        ego_speed_mps=130.0 / 3.6,
        object_speed_mps=130.0 / 3.6,
        wfh_mm=1.0,
        road_z_m=-0.411,
    )


def _radii(vehicle_class, *, frames=4000, seed=0):
    state = PlumeState()
    rng = np.random.default_rng(seed)
    context = _context()
    values = []
    for _ in range(frames):
        values.extend(
            cluster.radius
            for cluster in state.spawn(
                context, object_id=0, rng=rng, vehicle_class=vehicle_class
            )
        )
    return np.asarray(values)


def test_radius_fit_is_the_measured_lognormal_per_class():
    config = PlumeStateConfig()

    assert config.radius_mu["crafter"] == pytest.approx(-0.928)
    assert config.radius_sigma["crafter"] == pytest.approx(1.686)
    assert config.radius_mu["golf"] == pytest.approx(-0.850)
    assert config.radius_sigma["golf"] == pytest.approx(1.811)


def test_spawn_samples_the_class_specific_radius_median():
    crafter = _radii("crafter")
    golf = _radii("golf")

    assert crafter.size > 3000 and golf.size > 3000
    assert np.median(crafter) == pytest.approx(
        np.exp(RADIUS_MU_BY_CLASS["crafter"]), rel=0.05
    )
    assert np.median(golf) == pytest.approx(
        np.exp(RADIUS_MU_BY_CLASS["golf"]), rel=0.05
    )
    # Golf's measured fit has the larger median, so the class must matter.
    assert np.median(golf) > np.median(crafter)


def test_p_det_fit_is_the_measured_lognormal_per_class():
    assert p_det_params_for_class("crafter") == pytest.approx((-4.064, 2.597))
    assert p_det_params_for_class("golf") == pytest.approx((-4.415, 2.727))
    assert p_det_params_for_class("Crafter") == pytest.approx(
        p_det_params_for_class("crafter")
    )
    # Unknown classes keep the published profile.
    assert p_det_params_for_class("unknown") == pytest.approx((-2.3, 1.1))


def test_measured_p_det_tables_are_class_keyed():
    assert set(P_DET_MU_BY_CLASS) == {"crafter", "golf"}
    assert set(P_DET_SIGMA_BY_CLASS) == {"crafter", "golf"}
