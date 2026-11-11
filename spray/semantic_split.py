"""Frozen ``cal`` / ``held-out`` split for the SemanticSpray dataset (ticket 29d).

The split rule is frozen (``[CHỌN 2026-11-11]``):

* a cell is ``(group, object_velocity_kmh, distance_to_object_m)``;
* inside a cell the scenes are sorted by ``(itr_after_water, rel_path)`` and
  assigned alternately, with the starting role flipped for every other cell
  (even cell index starts at ``cal``, odd cell index starts at ``held-out``);
* an odd cell keeps its extra scene in ``cal`` and is flagged ``unpaired``;
* no RNG, so the same input always gives the same output.

Rule v1 sorted only by relative path and always started at ``cal``.  The
measurement runs inside a cell are ordered by ``itr_after_water`` (1..6) and
the water tank gets emptier after every run, so v1 systematically put
``cal`` into iterations 1, 3, 5 (fresh water, larger plume) and ``held-out``
into 2, 4, 6 (depleted water).  That produced a 44.6 % noise/frame gap and
failed G1/G6/G7 even though the two roles covered exactly the same cells.

Rule v2 sorts by ``itr_after_water`` and flips the parity per cell, so every
role receives the same number of scenes at every ``w_itr`` level.  Consequence:
comparing the two roles *inside a single cell* is no longer meaningful (their
iterations differ by construction); only role-level aggregates may be used.

It exists so generator parameters are never selected and validated on the same
scenes: ``cal`` may select parameters, ``held-out`` may only be used to check
them.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import yaml

ROLE_CAL = "cal"
ROLE_HELD_OUT = "held-out"
RULE_VERSION = "v2-parity-flip-by-cell"
SPLIT_VERSION = "semantic-spray-split-v2"
GROUPS = ("Crafter_dynamic", "Golf_dynamic")

SPLIT_RULE = (
    "1:1 trong từng ô (group, object_velocity, distance_to_object); "
    "sắp theo (itr_after_water, tên); parity đảo theo ô (ô chẵn bắt đầu cal, "
    "ô lẻ bắt đầu held-out); scene dư về cal"
)

_REQUIRED_COLUMNS = (
    "object_velocity",
    "distance_to_object",
    "itr_after_water",
    "amb_tmp",
)


@dataclass(frozen=True)
class SceneMeta:
    """One dataset scene and the metadata columns that define its cell."""

    group: str
    scene: str
    object_velocity_kmh: float
    distance_to_object_m: float
    itr_after_water: int
    amb_tmp_c: float | None

    @property
    def rel_path(self) -> str:
        return f"{self.group}/{self.scene}"


@dataclass(frozen=True)
class CriterionSpec:
    """One frozen acceptance criterion of the cal/held-out gate."""

    id: str
    quantity: str
    estimator: str
    keys: tuple[str, ...]
    floor_rel: float
    floor_abs: float


# Frozen thresholds from .scratch/spray-augmentation/issues/29d-semantic-split-gate.md
# (G1..G7, "7 tiêu chí đóng băng"). Never edit after seeing numbers.
CRITERIA_SPECS = (
    CriterionSpec(
        "G1", "noise_points_per_frame", "median", ("G1",), 0.15, 0.0
    ),
    CriterionSpec(
        "G2", "clusters_per_frame", "mean", ("G2",), 0.20, 0.0
    ),
    CriterionSpec(
        "G3", "points_per_cluster", "median", ("G3",), 0.20, 0.0
    ),
    CriterionSpec(
        "G4", "range_over_extent", "median", ("G4",), 0.0, 0.10
    ),
    CriterionSpec(
        "G5", "abs_y_p95_m", "p95", ("G5",), 0.15, 0.0
    ),
    CriterionSpec(
        "G6",
        "height_above_road_m",
        "p5, p50, p95",
        ("G6_p5", "G6_med", "G6_p95"),
        0.0,
        0.20,
    ),
    CriterionSpec(
        "G7", "elevation_deg", "median", ("G7",), 0.0, 0.5
    ),
)

SPEC_BY_ID = {spec.id: spec for spec in CRITERIA_SPECS}


@dataclass(frozen=True)
class CriterionResult:
    id: str
    quantity: str
    estimator: str
    cal: float
    held_out: float
    delta: float
    half_split_delta: float
    threshold: float
    relative: bool
    passed: bool
    note: str


def _parse_metadata(meta_path: Path, group: str, scene: str) -> SceneMeta:
    rel_path = f"{group}/{scene}"
    with meta_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(
            f"scene {rel_path}: metadata.txt must contain exactly 1 data row, "
            f"got {len(rows)}"
        )

    row = rows[0]
    missing = [
        column
        for column in _REQUIRED_COLUMNS
        if row.get(column) is None or row[column].strip() == ""
    ]
    if missing:
        raise ValueError(
            f"scene {rel_path}: metadata.txt missing column(s): "
            f"{', '.join(missing)}"
        )

    try:
        velocity = float(row["object_velocity"])
        distance = float(row["distance_to_object"])
        itr_after_water = int(row["itr_after_water"])
        amb_text = row["amb_tmp"].strip().lower()
        amb_tmp = None if amb_text in {"", "nan", "none"} else float(amb_text)
    except ValueError as exc:
        raise ValueError(
            f"scene {rel_path}: cannot parse metadata: {exc}"
        ) from exc

    return SceneMeta(
        group=group,
        scene=scene,
        object_velocity_kmh=velocity,
        distance_to_object_m=distance,
        itr_after_water=itr_after_water,
        amb_tmp_c=amb_tmp,
    )


def read_dataset(root: str | Path) -> list[SceneMeta]:
    """Read ``<group>/<scene>/metadata.txt`` for both SemanticSpray groups."""

    root = Path(root)
    metas: list[SceneMeta] = []
    for group in GROUPS:
        group_dir = root / group
        if not group_dir.is_dir():
            raise FileNotFoundError(f"missing dataset group: {group_dir}")
        scene_dirs = sorted(
            (path for path in group_dir.iterdir() if path.is_dir()),
            key=lambda path: path.name,
        )
        for scene_dir in scene_dirs:
            meta_path = scene_dir / "metadata.txt"
            if not meta_path.is_file():
                raise FileNotFoundError(f"missing metadata.txt: {meta_path}")
            metas.append(_parse_metadata(meta_path, group, scene_dir.name))

    metas.sort(key=lambda meta: meta.rel_path)
    return metas


def cell_key(meta: SceneMeta) -> tuple[str, float, float]:
    return (meta.group, meta.object_velocity_kmh, meta.distance_to_object_m)


def assign_roles(metas: list[SceneMeta]) -> dict[str, str]:
    """Assign ``cal``/``held-out`` by alternating inside each sorted cell.

    Members are ordered by ``(itr_after_water, rel_path)`` and the starting
    role flips with the cell index, so both roles get the same number of
    scenes at every ``w_itr`` level.  In an odd cell the extra scene always
    goes to ``cal``.
    """

    cells: dict[tuple[str, float, float], list[SceneMeta]] = {}
    for meta in metas:
        cells.setdefault(cell_key(meta), []).append(meta)

    roles: dict[str, str] = {}
    for cell_index, key in enumerate(sorted(cells)):
        members = sorted(
            cells[key],
            key=lambda meta: (meta.itr_after_water, meta.rel_path),
        )
        offset = cell_index % 2
        odd = bool(len(members) % 2)
        for index, meta in enumerate(members):
            if odd and index == len(members) - 1:
                roles[meta.rel_path] = ROLE_CAL
                continue
            roles[meta.rel_path] = (
                ROLE_CAL if (index + offset) % 2 == 0 else ROLE_HELD_OUT
            )
    return roles


def itr_balance(
    metas: list[SceneMeta], split: dict
) -> dict[str, dict[str, dict[int, int]]]:
    """Count scenes per ``group``, ``role`` and ``itr_after_water`` level.

    Returns ``{group: {role: {itr: count}}}``.  Only levels that actually
    occur are present; missing levels are absent rather than zero.
    """

    roles = _role_map(split)
    table: dict[str, dict[str, dict[int, int]]] = {}
    for meta in sorted(metas, key=lambda meta: meta.rel_path):
        role = roles.get(meta.rel_path)
        if role is None:
            raise ValueError(f"scene not in split: {meta.rel_path}")
        per_group = table.setdefault(
            meta.group, {ROLE_CAL: {}, ROLE_HELD_OUT: {}}
        )
        per_role = per_group[role]
        per_role[meta.itr_after_water] = (
            per_role.get(meta.itr_after_water, 0) + 1
        )
    return table


def _criteria_table() -> list[dict]:
    return [
        {
            "id": spec.id,
            "quantity": spec.quantity,
            "estimator": spec.estimator,
            "floor_rel": spec.floor_rel,
            "floor_abs": spec.floor_abs,
        }
        for spec in CRITERIA_SPECS
    ]


def build_split(metas: list[SceneMeta]) -> dict:
    """Build the complete split document (roles, counts, cells, criteria)."""

    roles = assign_roles(metas)
    cells: dict[tuple[str, float, float], dict[str, list[str]]] = {}
    for meta in sorted(metas, key=lambda meta: meta.rel_path):
        cell = cells.setdefault(
            cell_key(meta), {ROLE_CAL: [], ROLE_HELD_OUT: []}
        )
        cell[roles[meta.rel_path]].append(meta.rel_path)

    rows = []
    counts = {ROLE_CAL: 0, ROLE_HELD_OUT: 0}
    for key in sorted(cells):
        scenes = cells[key]
        total = len(scenes[ROLE_CAL]) + len(scenes[ROLE_HELD_OUT])
        counts[ROLE_CAL] += len(scenes[ROLE_CAL])
        counts[ROLE_HELD_OUT] += len(scenes[ROLE_HELD_OUT])
        rows.append(
            {
                "key": {
                    "group": key[0],
                    "velocity_kmh": key[1],
                    "distance_m": key[2],
                },
                "scenes": {
                    ROLE_CAL: scenes[ROLE_CAL],
                    ROLE_HELD_OUT: scenes[ROLE_HELD_OUT],
                },
                "unpaired": bool(total % 2),
            }
        )

    return {
        "version": SPLIT_VERSION,
        "rule_version": RULE_VERSION,
        "rule": SPLIT_RULE,
        "counts": counts,
        "cells": rows,
        "criteria": _criteria_table(),
    }


def dump_split(split: dict, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(
            split, handle, sort_keys=False, allow_unicode=True
        )


def load_split(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict):
        raise ValueError(f"split file is not a mapping: {path}")
    return document


def _role_map(split: dict) -> dict[str, str]:
    roles: dict[str, str] = {}
    for cell in split.get("cells") or []:
        scenes = cell.get("scenes") or {}
        for role in (ROLE_CAL, ROLE_HELD_OUT):
            for rel_path in scenes.get(role) or []:
                roles[str(rel_path)] = role
    return roles


def _cell_key_from_row(cell: dict) -> tuple[str, float, float]:
    key = cell.get("key") or {}
    return (
        str(key.get("group")),
        float(key.get("velocity_kmh")),
        float(key.get("distance_m")),
    )


def _cell_table(split: dict) -> dict[tuple[str, float, float], bool]:
    table: dict[tuple[str, float, float], bool] = {}
    for cell in split.get("cells") or []:
        table[_cell_key_from_row(cell)] = bool(cell.get("unpaired", False))
    return table


def verify_split(split: dict, path: str | Path) -> list[str]:
    """Compare ``split`` with the YAML on disk; [] means they agree.

    Only semantic content is compared (version, counts, per-scene roles, cell
    keys and ``unpaired`` flags), never the byte layout of the file.
    """

    on_disk = load_split(path)
    problems: list[str] = []

    if split.get("version") != on_disk.get("version"):
        problems.append(
            f"version: expected {split.get('version')!r}, "
            f"got {on_disk.get('version')!r}"
        )

    if split.get("rule_version") != on_disk.get("rule_version"):
        problems.append(
            f"rule_version: expected {split.get('rule_version')!r}, "
            f"got {on_disk.get('rule_version')!r}"
        )

    if split.get("counts") != on_disk.get("counts"):
        problems.append(
            f"counts: expected {split.get('counts')!r}, "
            f"got {on_disk.get('counts')!r}"
        )

    expected_roles = _role_map(split)
    actual_roles = _role_map(on_disk)
    for rel_path in sorted(set(expected_roles) | set(actual_roles)):
        expected = expected_roles.get(rel_path)
        actual = actual_roles.get(rel_path)
        if expected != actual:
            problems.append(
                f"scene {rel_path}: expected role {expected!r}, "
                f"got {actual!r}"
            )

    expected_cells = _cell_table(split)
    actual_cells = _cell_table(on_disk)
    for key in sorted(set(expected_cells) | set(actual_cells)):
        if key not in actual_cells:
            problems.append(f"cell {key}: missing from file")
        elif key not in expected_cells:
            problems.append(f"cell {key}: unexpected in file")
        elif expected_cells[key] != actual_cells[key]:
            problems.append(
                f"cell {key}: expected unpaired {expected_cells[key]}, "
                f"got {actual_cells[key]}"
            )

    return problems


def role_scenes(split: dict, role: str, root: str | Path) -> list[Path]:
    if role not in (ROLE_CAL, ROLE_HELD_OUT):
        raise ValueError(f"unknown role: {role!r}")
    rel_paths = sorted(
        rel_path
        for cell in split.get("cells") or []
        for rel_path in (cell.get("scenes") or {}).get(role) or []
    )
    base = Path(root)
    return [base / rel_path for rel_path in rel_paths]


def halves(rel_paths: list[str]) -> tuple[list[str], list[str]]:
    """Split an already sorted list into alternating halves (even, odd)."""

    ordered = list(rel_paths)
    return ordered[::2], ordered[1::2]


def _finite(value) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _relative_gap(gap: float, base: float) -> float:
    if base == 0.0:
        return 0.0 if gap == 0.0 else math.inf
    return abs(gap) / abs(base)


def _rollup(values: list[float]) -> float:
    if any(not math.isfinite(value) for value in values):
        return math.nan
    return max(abs(value) for value in values)


def _gate_notes(
    metrics_by_role: dict[str, dict[str, float]],
    min_frames: int,
    min_clusters: int,
) -> list[str]:
    notes: list[str] = []
    for role in (ROLE_CAL, ROLE_HELD_OUT):
        data = metrics_by_role.get(role) or {}
        frames = _finite(data.get("frames"))
        clusters = _finite(data.get("n_clusters"))
        if frames is None:
            notes.append(f"{role}: thiếu frames")
        elif frames < min_frames:
            notes.append(f"{role}: {int(frames)} frame < {min_frames}")
        if clusters is None:
            notes.append(f"{role}: thiếu n_clusters")
        elif clusters < min_clusters:
            notes.append(f"{role}: {int(clusters)} cụm < {min_clusters}")
    return notes


def evaluate_criteria(
    metrics_by_role: dict[str, dict[str, float]],
    *,
    min_frames: int = 300,
    min_clusters: int = 100,
) -> list[CriterionResult]:
    """Evaluate the frozen G1..G7 gate on ``cal`` vs ``held-out``.

    ``threshold = max(floor, 2 * Δ_halfsplit)`` where ``Δ_halfsplit`` is the
    gap between the two alternating halves of ``cal``; for G6 it is the largest
    gap over p5/p50/p95. Relative criteria compare ``|Δ|/cal``; absolute ones
    compare metres, ratio or degrees directly. Any criterion whose roles lack
    ``min_frames`` frames or ``min_clusters`` clusters fails with a
    ``quá ít dữ liệu`` note; thresholds are never widened.
    """

    cal_metrics = metrics_by_role.get(ROLE_CAL) or {}
    held_metrics = metrics_by_role.get(ROLE_HELD_OUT) or {}
    half_a = metrics_by_role.get("cal_a") or {}
    half_b = metrics_by_role.get("cal_b") or {}
    gate = _gate_notes(metrics_by_role, min_frames, min_clusters)

    results: list[CriterionResult] = []
    for spec in CRITERIA_SPECS:
        relative = spec.floor_rel > 0.0
        cal_values = [_finite(cal_metrics.get(key)) for key in spec.keys]
        held_values = [_finite(held_metrics.get(key)) for key in spec.keys]
        a_values = [_finite(half_a.get(key)) for key in spec.keys]
        b_values = [_finite(half_b.get(key)) for key in spec.keys]

        missing = [
            key
            for key, cal_value, held_value in zip(
                spec.keys, cal_values, held_values
            )
            if cal_value is None or held_value is None
        ]

        cal_head = cal_values[0] if cal_values[0] is not None else math.nan
        held_head = (
            held_values[0] if held_values[0] is not None else math.nan
        )

        if missing:
            note_parts = list(gate)
            note_parts.extend(f"thiếu {key}" for key in missing)
            results.append(
                CriterionResult(
                    id=spec.id,
                    quantity=spec.quantity,
                    estimator=spec.estimator,
                    cal=cal_head,
                    held_out=held_head,
                    delta=math.nan,
                    half_split_delta=math.nan,
                    threshold=(
                        spec.floor_rel if relative else spec.floor_abs
                    ),
                    relative=relative,
                    passed=False,
                    note="quá ít dữ liệu: " + "; ".join(note_parts),
                )
            )
            continue

        deltas = [
            held_value - cal_value
            for cal_value, held_value in zip(cal_values, held_values)
        ]

        half_values = [
            abs(a_value - b_value)
            for a_value, b_value in zip(a_values, b_values)
            if a_value is not None and b_value is not None
        ]
        if len(half_values) == len(spec.keys):
            half_gap = _rollup(half_values)
        else:
            half_gap = None

        if relative:
            base = cal_values[0]
            observed = _relative_gap(deltas[0], base)
            if half_gap is None:
                half_delta = math.nan
                threshold = spec.floor_rel
            else:
                half_delta = _relative_gap(half_gap, base)
                threshold = max(spec.floor_rel, 2.0 * half_delta)
            passed = observed <= threshold
            note = ""
        elif len(spec.keys) == 1:
            observed = abs(deltas[0])
            half_delta = half_gap if half_gap is not None else math.nan
            threshold = (
                max(spec.floor_abs, 2.0 * half_gap)
                if half_gap is not None
                else spec.floor_abs
            )
            passed = observed <= threshold
            note = ""
        else:
            worst = max(
                range(len(deltas)), key=lambda index: abs(deltas[index])
            )
            observed = abs(deltas[worst])
            half_delta = half_gap if half_gap is not None else math.nan
            threshold = (
                max(spec.floor_abs, 2.0 * half_gap)
                if half_gap is not None
                else spec.floor_abs
            )
            passed = all(abs(delta) <= threshold for delta in deltas)
            note = "; ".join(
                f"{key}: Δ={delta:+.3f}"
                for key, delta in zip(spec.keys, deltas)
            )
            if not passed:
                note += " — có phân vị vượt ngưỡng"

        if half_gap is None:
            passed = False
            note = "quá ít dữ liệu: thiếu half-split của cal"
        if gate:
            passed = False
            note = "quá ít dữ liệu: " + "; ".join(gate)

        if len(spec.keys) == 1:
            delta_value = deltas[0]
            cal_value = cal_values[0]
            held_value = held_values[0]
        else:
            worst = max(
                range(len(deltas)), key=lambda index: abs(deltas[index])
            )
            delta_value = deltas[worst]
            cal_value = cal_values[worst]
            held_value = held_values[worst]

        results.append(
            CriterionResult(
                id=spec.id,
                quantity=spec.quantity,
                estimator=spec.estimator,
                cal=float(cal_value),
                held_out=float(held_value),
                delta=float(delta_value),
                half_split_delta=float(half_delta),
                threshold=float(threshold),
                relative=relative,
                passed=bool(passed),
                note=note,
            )
        )

    return results
