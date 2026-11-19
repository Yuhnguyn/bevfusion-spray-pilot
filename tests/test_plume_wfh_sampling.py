"""Mức ẩm lấy mẫu theo scene (ADR-0006 §5.7 điều kiện 3; [PAPER] §V)."""

import inspect

from spray.plume_context import sample_wfh_mm


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
