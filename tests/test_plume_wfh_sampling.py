"""Mức ẩm lấy mẫu theo scene (ADR-0006 §5.7 điều kiện 3; [PAPER] §V)."""

import inspect

import numpy as np

from spray.plume import inject_plume_stateful
from spray.plume_context import PlumeContext, sample_wfh_mm
from spray.plume_state import PlumeState


def test_sample_wfh_in_paper_range():
    """1000 lần với token khác nhau: mọi giá trị trong [0.1, 1.2]."""
    for index in range(1000):
        value = sample_wfh_mm(f"scene_{index}")

        assert 0.1 <= value <= 1.2


def test_sample_wfh_is_deterministic_per_scene():
    """Cùng (token, epoch, seed) => cùng giá trị; khác epoch => khác giá trị
    (ít nhất một trong 20 cặp khác)."""
    first = sample_wfh_mm("Crafter_dynamic/0060", 0, 0)
    second = sample_wfh_mm("Crafter_dynamic/0060", 0, 0)

    assert first == second

    differences = sum(
        sample_wfh_mm("Crafter_dynamic/0060", epoch, 0)
        != sample_wfh_mm("Crafter_dynamic/0060", 0, 0)
        for epoch in range(1, 21)
    )

    assert differences >= 1


def test_sample_wfh_does_not_depend_on_frame_index():
    """Chữ ký hàm không có frame_index; hai lần gọi liền nhau cùng token => bằng nhau."""
    assert "frame_index" not in inspect.signature(sample_wfh_mm).parameters

    assert sample_wfh_mm("Golf_dynamic/0006") == sample_wfh_mm("Golf_dynamic/0006")


def test_sample_wfh_mean_near_0766():
    """1000 mẫu: mean trong [0.70, 0.85] — chốt đặc tính phân bố, không phải giá trị tuyệt đối."""
    values = [sample_wfh_mm(f"mean_{index}") for index in range(1000)]

    mean = sum(values) / len(values)

    assert 0.70 <= mean <= 0.85


def _context() -> PlumeContext:
    return PlumeContext(
        scene_token="Crafter_dynamic/0060",
        frame_index=0,
        epoch=0,
        sensor_origin=np.zeros(3, dtype=np.float64),
        ego_speed_mps=0.0,
        object_speed_mps=30.0,
        wfh_mm=0.5,
        road_z_m=-0.411,
    )


def test_fixed_water_film_is_not_sampled(monkeypatch, capsys):
    """``water_film_mm`` khác None => dùng số đó, KHÔNG gọi ``sample_wfh_mm``."""

    def _boom(*args, **kwargs):
        raise AssertionError("sample_wfh_mm must not be called when fixed")

    monkeypatch.setattr("spray.plume.sample_wfh_mm", _boom)

    inject_plume_stateful(
        np.zeros((100, 5), dtype=np.float32),
        np.empty((0, 9), dtype=np.float32),
        _context(),
        PlumeState(),
        seed=0,
        token="Crafter_dynamic/0060",
        water_film_mm=1.0,
    )

    output = capsys.readouterr().out

    assert "PLUME_WFH fixed=1" in output
