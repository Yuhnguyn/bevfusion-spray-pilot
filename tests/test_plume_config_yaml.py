"""``spray/config/plume_default.yaml`` must be a faithful copy of PlumeConfig."""

import dataclasses

import pytest
import yaml

from spray.ab_config import SPRAY_CONFIG
from spray.plume import PlumeConfig


@pytest.fixture(scope="module")
def params():
    with open(SPRAY_CONFIG, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _same(loaded, default):
    if isinstance(default, tuple):
        return tuple(loaded) == default
    return loaded == default


def test_every_yaml_key_is_a_plume_config_field(params):
    fields = {field.name for field in dataclasses.fields(PlumeConfig)}
    assert set(params) <= fields
    assert set(params) == fields, "plume_default.yaml is not a full copy"


def test_yaml_values_are_the_current_defaults(params):
    defaults = PlumeConfig()
    for key, value in params.items():
        assert _same(value, getattr(defaults, key)), key


def test_yaml_reconstructs_the_plume_config(params):
    built = PlumeConfig(**params)
    defaults = PlumeConfig()
    for field in dataclasses.fields(PlumeConfig):
        assert _same(getattr(built, field.name), getattr(defaults, field.name)), (
            field.name
        )
