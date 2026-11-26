#!/usr/bin/env python3
"""Build the interactive spray-pipeline graph from the Markdown map.

Reads ``docs/pipeline-map.md`` for the formulas and the maintained prose,
extracts the referenced functions verbatim with ``ast`` and writes:

- ``docs/pipeline-graph.json`` — nodes, edges, sources, formulas;
- ``docs/pipeline-graph.html`` — one self-contained page (no network).
"""

from __future__ import annotations

import ast
import html as html_module
import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MARKDOWN = ROOT / "docs" / "pipeline-map.md"
JSON_OUT = ROOT / "docs" / "pipeline-graph.json"
HTML_OUT = ROOT / "docs" / "pipeline-graph.html"

NODE_W = 196
NODE_H = 46
START_X = 30
STRIDE_X = 220
TOP = 74
ROW = 64
MAX_ROWS = 7

GROUPS = [
    {
        "id": "data",
        "title": "Dữ liệu vào",
        "color": "#4a7c94",
        "soft": "#eaf1f5",
        "note": "Gọi từ evaluator (sspp_infer.py / sspp_adapter.py). PlumeTransform KHÔNG tự đọc file; thiếu plume_context thì raise.",
    },
    {"id": "entry", "title": "Điểm vào", "color": "#126782", "soft": "#e3eef3", "note": ""},
    {
        "id": "cycle",
        "title": "Chu kỳ cụm",
        "color": "#147d70",
        "soft": "#e4f2ef",
        "note": "Δt = 0,1 s; cụm cũ trước, cụm mới sau.",
    },
    {"id": "drift", "title": "Trôi cụm", "color": "#a3752c", "soft": "#f6efe2", "note": ""},
    {"id": "raycast", "title": "Raycast", "color": "#6b5b95", "soft": "#efecf6", "note": ""},
    {"id": "output", "title": "Ghép ra", "color": "#b05c42", "soft": "#f8ece7", "note": ""},
]
GROUP_INDEX = {group["id"]: index for index, group in enumerate(GROUPS)}
GROUP_BY_ID = {group["id"]: group for group in GROUPS}

NODE_SPECS = [
    # a. Dữ liệu vào
    {
        "id": "clean_points",
        "group": "data",
        "file": "scripts/sspp_infer.py",
        "qualname": "clean_points",
        "description": "Ghép load_points + read_labels: trả (điểm thô, điểm sạch nhiễu, số điểm nhiễu). Gọi từ evaluator, không phải từ transform.",
        "patterns": [r"load_points", r"read_labels", r"NOISE_LABEL"],
    },
    {
        "id": "load_points",
        "group": "data",
        "file": "spray/sspp_adapter.py",
        "qualname": "load_points",
        "description": "Đọc velodyne .bin thành mảng (N,5) x,y,z,intensity,ring. Không lọc nhãn spray — transform không tự đọc file.",
        "patterns": [r"np\.fromfile", r"reshape"],
    },
    {
        "id": "read_labels",
        "group": "data",
        "file": "scripts/sspp_infer.py",
        "qualname": "read_labels",
        "description": "Đọc file .label int32 của một frame; clean_points dùng để bỏ điểm nhiễu.",
        "patterns": [r"np\.fromfile", r"label_path_for"],
    },
    {
        "id": "read_frame_boxes",
        "group": "data",
        "file": "spray/sspp_adapter.py",
        "qualname": "read_frame_boxes",
        "description": "Đọc box 3D Car/Van từ JSON nhãn của frame (bỏ Other Vehicle); đổi sang z_đáy + kích thước + yaw.",
        "patterns": [r"center3D", r"z_bottom", r"_BOX_TYPE"],
    },
    {
        "id": "build_context",
        "group": "data",
        "file": "scripts/sspp_infer.py",
        "qualname": "build_context",
        "description": "Dựng PlumeContext cho một frame (tốc độ ego/vật, wfh, road_z). Transform không tự đọc dataset; thiếu plume_context thì raise RuntimeError.",
        "patterns": [r"PlumeContext\(", r"ego_speed", r"object_speed_mps"],
    },
    {
        "id": "read_infos",
        "group": "data",
        "file": "scripts/sspp_infer.py",
        "qualname": "read_infos",
        "description": "Đọc pickle infos của split (danh sách frame). Gọi từ evaluator.",
        "patterns": [r"pickle\.load"],
    },
    {
        "id": "read_split",
        "group": "data",
        "file": "scripts/sspp_infer.py",
        "qualname": "read_split",
        "description": "Đọc danh sách scene của một split trong file split.json.",
        "patterns": [r"split", r"GATE_C_FAILED"],
    },
    # b. Điểm vào
    {
        "id": "PlumeTransform.__call__",
        "group": "entry",
        "file": "spray/plume_transform.py",
        "qualname": "PlumeTransform.__call__",
        "description": "Điểm vào: kiểm tra points/boxes/plume_context, chạy generator rồi raycast, ghép points_out.",
        "patterns": [r"raise RuntimeError", r"inject_plume_stateful\(", r"raycast_frame\(", r"np\.concatenate"],
    },
    # c. Chu kỳ cụm
    {
        "id": "inject_plume_stateful",
        "group": "cycle",
        "file": "spray/plume.py",
        "qualname": "inject_plume_stateful",
        "description": "Một chu kỳ: advance + prune cụm cũ, warm start khi sang scene, spawn cụm mới trong slab sau đuôi xe.",
        "patterns": [r"state\.advance", r"state\.prune", r"needs_warm_start", r"state\.warm_start", r"state\.spawn", r"select_alive", r"slab_length", r"SPAWN_BOX"],
    },
    {
        "id": "needs_warm_start",
        "group": "cycle",
        "file": "spray/plume_state.py",
        "qualname": "PlumeState.needs_warm_start",
        "description": "True khi state chưa từng chạy cho scene này (scene mới).",
        "patterns": [r"scene_token !="],
    },
    {
        "id": "warm_start",
        "group": "cycle",
        "file": "spray/plume_state.py",
        "qualname": "PlumeState.warm_start",
        "description": "Chạy các chu kỳ giả để scene bắt đầu với vệt bụi đã bão hoà thay vì state rỗng.",
        "patterns": [r"lifetime_mean_s", r"self\.advance", r"self\.prune", r"self\.spawn"],
    },
    {
        "id": "PlumeState.spawn",
        "group": "cycle",
        "file": "spray/plume_state.py",
        "qualname": "PlumeState.spawn",
        "description": "Sinh cụm mới: cộng dồn nhịp sinh, rải đều trong khối sau xe, bán kính log chuẩn, ttl = T.",
        "patterns": [r"radius_draw", r"lifetime_mean_s", r"rng\.uniform\(-1\.0", r"mean_ttl"],
    },
    {
        "id": "lifetime_mean_s",
        "group": "cycle",
        "file": "spray/plume_state.py",
        "qualname": "lifetime_mean_s",
        "description": "Tuổi thọ trung bình T từ tốc độ vật và màng nước wfh.",
        "patterns": [r"LIFETIME_WFH_COEFF", r"LIFETIME_BASE_S"],
    },
    {
        "id": "steady_state_factor",
        "group": "cycle",
        "file": "spray/plume.py",
        "qualname": "steady_state_factor",
        "description": "Hệ số tích luỹ K của cấp số nhân cụm tan theo xác suất exp(-Δt/T).",
        "patterns": [r"np\.exp\(-dt", r"1\.0 /"],
    },
    {
        "id": "cluster_rate_for_speed",
        "group": "cycle",
        "file": "spray/plume.py",
        "qualname": "cluster_rate_for_speed",
        "description": "Nhịp sinh cụm mỗi chu kỳ = số cụm nhìn thấy / K(T_ref); không chứa wfh.",
        "patterns": [r"visible_ref", r"k_ref"],
    },
    # d. Trôi cụm
    {
        "id": "PlumeState.advance",
        "group": "drift",
        "file": "spray/plume_state.py",
        "qualname": "PlumeState.advance",
        "description": "Trôi cụm bằng gió + lực cản; vị trí tích phân trong hệ ego; tăng tuổi thêm dt.",
        "patterns": [r"cluster\.vel - wind", r"speed_after", r"cluster\.pos =", r"cluster\.age \+="],
    },
    {
        "id": "PlumeState.prune",
        "group": "drift",
        "file": "spray/plume_state.py",
        "qualname": "PlumeState.prune",
        "description": "Loại cụm theo xác suất sống exp(-Δt/ttl) và trần tuổi 12×ttl.",
        "patterns": [r"cap_factor \* cluster\.ttl", r"survival =", r"random\.random"],
    },
    {
        "id": "wind_vector",
        "group": "drift",
        "file": "spray/plume_state.py",
        "qualname": "wind_vector",
        "description": "Vận tốc gió trong hệ ego từ hướng khí tượng “from” (208°).",
        "patterns": [r"heading_from", r"east =", r"north ="],
    },
    # e. Raycast
    {
        "id": "raycast_frame",
        "group": "raycast",
        "file": "spray/raycast.py",
        "qualname": "raycast_frame",
        "description": "Cast lưới tia qua cụm: xác suất phản hồi, suy hao điểm thật, giữ echo mạnh nhất.",
        "patterns": [r"build_beams\(", r"_collect_hits\(", r"np\.exp\(-2\.0", r"probability =", r"_keep_strongest_per_beam\("],
    },
    {
        "id": "build_beams",
        "group": "raycast",
        "file": "spray/beam_model.py",
        "qualname": "build_beams",
        "description": "Đổi lưới góc thành cặp mảng elevation/azimuth phẳng (azimuth-major).",
        "patterns": [r"meshgrid", r"n_azimuth"],
    },
    {
        "id": "RaycastConfig",
        "group": "raycast",
        "file": "spray/raycast.py",
        "qualname": "RaycastConfig",
        "description": "Tham số raycast: suy hao μ, lognormal P_det, hệ số cự ly b, ngưỡng cường độ.",
        "patterns": [r"mean_attenuation_per_m", r"p_det_mu", r"pdet_range_exponent"],
    },
    {
        "id": "_collect_hits",
        "group": "raycast",
        "file": "spray/raycast.py",
        "qualname": "_collect_hits",
        "description": "Tiền lọc tia trong vùng góc của từng cầu rồi mới giao, tránh thử cả 54 750 tia.",
        "patterns": [r"ray_sphere_intersect", r"half_angle"],
    },
    {
        "id": "ray_sphere_intersect",
        "group": "raycast",
        "file": "spray/beam_model.py",
        "qualname": "ray_sphere_intersect",
        "description": "Giải phương trình bậc hai tia–cầu, trả khoảng cách vào/ra; tia chỉ ra khỏi cầu thì bỏ.",
        "patterns": [r"discriminant", r"t0 = np\.where", r"t1 = np\.where"],
    },
    {
        "id": "_keep_strongest_per_beam",
        "group": "raycast",
        "file": "spray/raycast.py",
        "qualname": "_keep_strongest_per_beam",
        "description": "Mỗi tia chỉ giữ echo mạnh nhất giữa điểm thật và spray; điểm spray xuất ra cường độ 0.",
        "patterns": [r"group_max", r"real_max_by_hit"],
    },
    {
        "id": "load_beam_table",
        "group": "raycast",
        "file": "spray/beam_model.py",
        "qualname": "load_beam_table",
        "description": "Dựng lưới tia đều (30 ring) từ FOV đo được; không còn file YAML.",
        "patterns": [r"np\.arange", r"BeamTable\("],
    },
    # f. Ghép ra
    {
        "id": "PlumeState.select_alive",
        "group": "output",
        "file": "spray/plume_state.py",
        "qualname": "PlumeState.select_alive",
        "description": "Lọc cụm theo miền hợp lệ: mặt cầu ≥ min_range, tâm ≤ max_range.",
        "patterns": [r"distance - float", r"cfg\.max_range_m"],
    },
    {
        "id": "merge",
        "group": "output",
        "file": "spray/plume_transform.py",
        "qualname": None,
        "start_line": 129,
        "end_line": 141,
        "label": "points_out",
        "owner": "plume_transform",
        "description": "Ghép points_out = real_points + detections sau raycast.",
        "patterns": [],
        "highlight_all": True,
    },
]

FORMULA_TARGETS = [
    "lifetime_mean_s",
    "steady_state_factor",
    "steady_state_factor",
    "inject_plume_stateful",
    "PlumeState.spawn",
    "wind_vector",
    "PlumeState.advance",
    "PlumeState.advance",
    "PlumeState.prune",
    "ray_sphere_intersect",
    "raycast_frame",
    "raycast_frame",
    "merge",
]

UNICODE_SYMBOLS = {
    "Delta": "Δ",
    "mu": "μ",
    "theta": "θ",
    "sigma": "σ",
    "pi": "π",
    "sim": "∼",
    "cdots": "⋯",
    "ldots": "…",
    "sum": "∑",
    "times": "×",
    "approx": "≈",
    "le": "≤",
    "ge": "≥",
    "neq": "≠",
    "pm": "±",
    "cdot": "·",
    "infty": "∞",
}
FUNCTIONS = {"min", "max", "sin", "cos", "tan", "exp", "log", "ln", "arg"}


class MathRenderer:
    """Render the small LaTeX subset used by ``pipeline-map.md`` to HTML."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0

    def render(self) -> str:
        return self._sequence(False)

    def _peek(self) -> str:
        return self.source[self.pos] if self.pos < len(self.source) else ""

    def _sequence(self, inside_group: bool) -> str:
        out: list[str] = []
        while self.pos < len(self.source):
            char = self.source[self.pos]
            if char == "}":
                if inside_group:
                    self.pos += 1
                    break
                self.pos += 1
                continue
            if char == "{":
                out.append(self._group())
            elif char == "\\":
                out.append(self._command())
            elif char in "^_":
                self.pos += 1
                tag = "sup" if char == "^" else "sub"
                out.append(f"<{tag}>{self._atom()}</{tag}>")
            elif char.isalpha():
                start = self.pos
                while self.pos < len(self.source) and self.source[self.pos].isalpha():
                    self.pos += 1
                out.append(self._word(self.source[start:self.pos]))
            elif char.isdigit():
                self.pos += 1
                out.append(f'<span class="mn">{char}</span>')
            elif char in ".,":
                self.pos += 1
                out.append(f'<span class="punc">{char}</span>')
            elif char in "=+-<>":
                self.pos += 1
                symbol = "−" if char == "-" else ("∼" if char == "~" else char)
                out.append(f'<span class="op">{symbol}</span>')
            elif char in "()[]|/":
                self.pos += 1
                out.append(f'<span class="br">{html_module.escape(char)}</span>')
            elif char == "'":
                self.pos += 1
                out.append('<span class="prime">′</span>')
            else:
                if not char.isspace():
                    out.append(html_module.escape(char))
                self.pos += 1
        return "".join(out)

    def _group(self) -> str:
        self.pos += 1
        return self._sequence(True)

    def _atom(self) -> str:
        while self._peek().isspace():
            self.pos += 1
        char = self._peek()
        if not char:
            return ""
        if char == "{":
            return self._group()
        if char == "\\":
            return self._command()
        if char.isalpha():
            self.pos += 1
            return f"<i>{html_module.escape(char)}</i>"
        if char.isdigit():
            self.pos += 1
            return f'<span class="mn">{char}</span>'
        self.pos += 1
        return f'<span class="br">{html_module.escape(char)}</span>'

    @staticmethod
    def _word(run: str) -> str:
        if len(run) == 1:
            return f"<i>{html_module.escape(run)}</i>"
        return f'<span class="rm">{html_module.escape(run)}</span>'

    def _command(self) -> str:
        self.pos += 1
        start = self.pos
        while self.pos < len(self.source) and self.source[self.pos].isalpha():
            self.pos += 1
        name = self.source[start:self.pos]
        if not name:
            char = self._peek()
            self.pos += 1
            if char == ",":
                return '<span class="thin"></span>'
            if char in ";:":
                return '<span class="thin2"></span>'
            if char == " ":
                return '<span class="thin"></span>'
            if char == "|":
                return '<span class="op">‖</span>'
            if char in "{}":
                return html_module.escape(char)
            return html_module.escape(char)
        if name == "frac":
            numerator = self._atom()
            denominator = self._atom()
            return (
                '<span class="frac"><span class="num">'
                f"{numerator}</span><span class=\"den\">{denominator}</span></span>"
            )
        if name in {"mathbf", "boldsymbol"}:
            return f"<b>{self._atom()}</b>"
        if name == "mathcal":
            return f'<span class="cal">{self._atom()}</span>'
        if name in {"mathrm", "text", "operatorname"}:
            return f'<span class="rm">{self._atom()}</span>'
        if name in FUNCTIONS:
            return f'<span class="fn">{name}</span>'
        if name == "quad":
            return '<span class="quad"></span><wbr>'
        if name == "qquad":
            return '<span class="qquad"></span><wbr>'
        if name in UNICODE_SYMBOLS:
            return f'<span class="sym">{UNICODE_SYMBOLS[name]}</span>'
        return f'<span class="rm">{html_module.escape(name)}</span>'


def render_math(source: str) -> str:
    latex = source.strip()
    latex = re.sub(r"^\s*\\\[\s*", "", latex)
    latex = re.sub(r"\s*\\\]\s*$", "", latex)
    return MathRenderer(latex.strip()).render()


def read_formulas(markdown: str) -> list[dict]:
    blocks = re.findall(r"\\\[(.*?)\\\]", markdown, flags=re.DOTALL)
    if len(blocks) != len(FORMULA_TARGETS):
        raise SystemExit(
            "formula count changed in docs/pipeline-map.md: "
            f"{len(blocks)} blocks vs {len(FORMULA_TARGETS)} targets; "
            "update FORMULA_TARGETS in scripts/build_pipeline_graph.py"
        )
    formulas = []
    for index, (block, target) in enumerate(zip(blocks, FORMULA_TARGETS)):
        latex = " ".join(block.split())
        formulas.append(
            {
                "index": index,
                "node": target,
                "latex": latex,
                "html": render_math(block),
            }
        )
    return formulas


def parse_module(relative_path: str) -> tuple[str, ast.Module, list[str]]:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    return text, ast.parse(text), text.splitlines()


def find_definition(tree: ast.Module, qualname: str) -> ast.AST:
    body: list[ast.stmt] = tree.body
    node: ast.AST | None = None
    for part in qualname.split("."):
        node = None
        for candidate in body:
            if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if candidate.name == part:
                    node = candidate
                    break
        if node is None:
            raise SystemExit(f"definition not found: {qualname} ({part})")
        body = getattr(node, "body", [])
    assert node is not None
    return node


def source_span(node: ast.AST) -> tuple[int, int]:
    start = node.lineno
    for decorator in getattr(node, "decorator_list", []) or []:
        start = min(start, decorator.lineno)
    return start, node.end_lineno


def qualified_owner(qualname: str, relative_path: str) -> tuple[str, str]:
    parts = qualname.split(".")
    if len(parts) == 1:
        return parts[0], Path(relative_path).name
    return parts[-1], ".".join(parts[:-1])


def build_nodes() -> dict[str, dict]:
    parsed: dict[str, tuple[str, ast.Module, list[str]]] = {}
    nodes: dict[str, dict] = {}
    for spec in NODE_SPECS:
        relative_path = spec["file"]
        if relative_path not in parsed:
            parsed[relative_path] = parse_module(relative_path)
        text, tree, lines = parsed[relative_path]
        qualname = spec["qualname"]
        if qualname is not None:
            definition = find_definition(tree, qualname)
            start, end = source_span(definition)
            def_line = definition.lineno
            label, owner = qualified_owner(qualname, relative_path)
        else:
            start = int(spec["start_line"])
            end = int(spec["end_line"])
            def_line = start
            label = spec["label"]
            owner = spec["owner"]
        code = "\n".join(lines[start - 1:end])

        highlights = {def_line}
        if spec.get("highlight_all"):
            highlights.update(range(start, end + 1))
        else:
            for pattern in spec.get("patterns", []):
                regex = re.compile(pattern)
                for offset, line in enumerate(lines[start - 1:end]):
                    if regex.search(line):
                        highlights.add(start + offset)

        group = GROUP_BY_ID[spec["group"]]
        nodes[spec["id"]] = {
            "id": spec["id"],
            "label": label,
            "owner": owner,
            "group": spec["group"],
            "description": spec["description"],
            "file": relative_path,
            "start_line": start,
            "end_line": end,
            "editor_link": f"../{relative_path}#L{start}",
            "highlight_lines": sorted(highlights),
            "formulas": [],
        }
        nodes[spec["id"]]["_code"] = code
        nodes[spec["id"]]["_text"] = text
        nodes[spec["id"]]["_lines"] = lines
        nodes[spec["id"]]["color"] = group["color"]
        nodes[spec["id"]]["soft"] = group["soft"]
    return nodes


def build_edges(nodes: dict[str, dict]) -> list[dict]:
    known_ids = set(nodes)
    short_index: dict[str, list[str]] = {}
    for node_id in known_ids:
        short_index.setdefault(node_id.split(".")[-1], []).append(node_id)

    edges: set[tuple[str, str, str]] = set()
    parsed: dict[str, ast.Module] = {}
    for node_id, node in nodes.items():
        spec = next((item for item in NODE_SPECS if item["id"] == node_id), None)
        if spec is None or spec.get("qualname") is None:
            continue
        relative_path = spec["file"]
        if relative_path not in parsed:
            parsed[relative_path] = parse_module(relative_path)[1]
        tree = parsed[relative_path]
        definition = find_definition(tree, spec["qualname"])
        parts = spec["qualname"].split(".")
        enclosing_class = parts[0] if len(parts) > 1 else None

        candidates: set[str] = set()
        for sub in ast.walk(definition):
            if isinstance(sub, ast.Attribute) and sub.attr == "wind":
                if isinstance(sub.value, ast.Name) and sub.value.id == "self":
                    candidates.add("wind_vector")
            if not isinstance(sub, ast.Call):
                continue
            func = sub.func
            name = None
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name is None:
                continue
            if enclosing_class and f"{enclosing_class}.{name}" in known_ids:
                candidates.add(f"{enclosing_class}.{name}")
            elif name in known_ids:
                candidates.add(name)
            elif name in short_index:
                options = short_index[name]
                if len(options) == 1:
                    candidates.add(options[0])
        for target in candidates:
            if target != node_id:
                edges.add((node_id, target, "call"))

    edges.add(("raycast_frame", "merge", "flow"))
    edges.add(("PlumeState.select_alive", "merge", "flow"))

    ordered = sorted(
        edges,
        key=lambda item: (
            GROUP_INDEX[nodes[item[0]]["group"]],
            GROUP_INDEX[nodes[item[1]]["group"]],
            item[0],
            item[1],
        ),
    )
    return [{"source": source, "target": target, "kind": kind} for source, target, kind in ordered]


def layout(nodes: dict[str, dict]) -> tuple[int, int, dict[str, dict]]:
    by_group: dict[str, list[str]] = {group["id"]: [] for group in GROUPS}
    for spec in NODE_SPECS:
        by_group[spec["group"]].append(spec["id"])

    headers = []
    width = 0
    for column, group in enumerate(GROUPS):
        x = START_X + column * STRIDE_X
        width = max(width, x + NODE_W + START_X)
        entries = by_group[group["id"]]
        total = len(entries) * ROW - (ROW - NODE_H)
        start_y = TOP + (MAX_ROWS * ROW - (ROW - NODE_H) - total) / 2
        for row, node_id in enumerate(entries):
            nodes[node_id]["x"] = x
            nodes[node_id]["y"] = start_y + row * ROW
        headers.append(
            {
                "x": x,
                "y": 24,
                "title": group["title"],
                "color": group["color"],
                "count": len(entries),
            }
        )
    height = int(TOP + MAX_ROWS * ROW + 120)
    return width, height, {"headers": headers}


def rounded_path(points: list[tuple[float, float]], radius: float = 12) -> str:
    def fmt(value: float) -> str:
        return f"{value:.1f}".rstrip("0").rstrip(".")

    if len(points) < 2:
        return ""
    commands = [f"M {fmt(points[0][0])} {fmt(points[0][1])}"]
    for index in range(1, len(points)):
        x0, y0 = points[index - 1]
        x1, y1 = points[index]
        if index == len(points) - 1:
            commands.append(f"L {fmt(x1)} {fmt(y1)}")
            break
        x2, y2 = points[index + 1]
        length_in = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        length_out = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        r = min(radius, length_in / 2, length_out / 2)
        if length_in == 0 or length_out == 0:
            commands.append(f"L {fmt(x1)} {fmt(y1)}")
            continue
        before = (x1 - (x1 - x0) / length_in * r, y1 - (y1 - y0) / length_in * r)
        after = (x1 + (x2 - x1) / length_out * r, y1 + (y2 - y1) / length_out * r)
        commands.append(f"L {fmt(before[0])} {fmt(before[1])}")
        commands.append(f"Q {fmt(x1)} {fmt(y1)} {fmt(after[0])} {fmt(after[1])}")
    return " ".join(commands)


def route_edges(nodes: dict[str, dict], edges: list[dict]) -> list[dict]:
    fan_counter: dict[str, int] = {}
    long_lane = 0
    routed = []
    for edge in edges:
        source = nodes[edge["source"]]
        target = nodes[edge["target"]]
        source_column = GROUP_INDEX[source["group"]]
        target_column = GROUP_INDEX[target["group"]]
        source_x = source["x"] + NODE_W
        source_y = source["y"] + NODE_H / 2
        target_x = target["x"] + NODE_W
        target_y = target["y"] + NODE_H / 2
        entry_x = target["x"] + 4

        if source_column == target_column:
            fan = fan_counter.get(edge["source"], 0)
            fan_counter[edge["source"]] = fan + 1
            offset = 7 + fan * 5
            right = source["x"] + NODE_W - 2
            path = (
                f"M {right:.1f} {source_y:.1f} "
                f"C {right + offset:.1f} {source_y:.1f}, "
                f"{right + offset:.1f} {target_y:.1f}, {right:.1f} {target_y:.1f}"
            )
        elif target_column - source_column >= 3:
            lane_y = 548 + long_lane * 14
            long_lane += 1
            gutter_out = source["x"] + NODE_W + 16
            gutter_in = target["x"] - 12
            path = rounded_path(
                [
                    (source["x"] + NODE_W, source_y),
                    (gutter_out, source_y),
                    (gutter_out, lane_y),
                    (gutter_in, lane_y),
                    (gutter_in, target_y),
                    (entry_x, target_y),
                ]
            )
        else:
            path = (
                f"M {source_x:.1f} {source_y:.1f} "
                f"C {source_x + 18:.1f} {source_y:.1f}, "
                f"{entry_x - 18:.1f} {target_y:.1f}, {entry_x:.1f} {target_y:.1f}"
            )
        routed.append({**edge, "path": path, "source_group": source["group"]})
    return routed


def attach_formulas(nodes: dict[str, dict], formulas: list[dict]) -> None:
    for formula in formulas:
        nodes[formula["node"]]["formulas"].append(
            {"latex": formula["latex"], "html": formula["html"]}
        )


def build_payload() -> dict:
    markdown = MARKDOWN.read_text(encoding="utf-8")
    formulas = read_formulas(markdown)
    nodes = build_nodes()
    attach_formulas(nodes, formulas)
    edges = build_edges(nodes)
    width, height, meta = layout(nodes)

    sources = {}
    public_nodes = []
    for node_id, node in nodes.items():
        sources[node_id] = {
            "file": node["file"],
            "start_line": node["start_line"],
            "end_line": node["end_line"],
            "code": node["_code"],
        }
        public_nodes.append(
            {
                key: value
                for key, value in node.items()
                if not key.startswith("_")
            }
        )

    routed = route_edges(nodes, edges)
    return {
        "title": "Pipeline spray — graph tương tác",
        "generated_from": "docs/pipeline-map.md",
        "width": width,
        "height": height,
        "groups": GROUPS,
        "headers": meta["headers"],
        "nodes": public_nodes,
        "edges": routed,
        "sources": sources,
        "formulas": formulas,
        "node_size": {"width": NODE_W, "height": NODE_H},
    }


def verify_sources(payload: dict) -> None:
    failures = []
    for node_id, source in payload["sources"].items():
        text = (ROOT / source["file"]).read_text(encoding="utf-8")
        if source["code"] not in text:
            failures.append(node_id)
    if failures:
        raise SystemExit(f"source extraction mismatch: {failures}")
    sample = random.sample(list(payload["sources"]), 3)
    for node_id in sample:
        source = payload["sources"][node_id]
        text = (ROOT / source["file"]).read_text(encoding="utf-8")
        assert source["code"] in text, node_id
    print(f"EXTRACT_OK {len(sample)}/{len(sample)} random samples verbatim")


PAGE = r"""<!doctype html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{
  color-scheme:light;
  --ink:#17232d;--muted:#5b6b76;--paper:#fbfaf7;--panel:#fff;--line:#e3e9ec;
  --edge:#b9c8d1;--wash:#f4f7f8;--accent:#126782;
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:14px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;-webkit-font-smoothing:antialiased}
header{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding:13px 22px;border-bottom:1px solid var(--line);background:rgba(255,255,255,.92);backdrop-filter:blur(6px);position:sticky;top:0;z-index:10}
.brand{font-weight:600;font-size:14.5px;letter-spacing:.01em}
.brand small{display:block;font-weight:400;color:var(--muted);font-size:11px;letter-spacing:.02em}
.search{position:relative}
.search input{width:min(330px,42vw);padding:8px 34px 8px 12px;border:1px solid var(--line);border-radius:9px;background:var(--wash);font:inherit;font-size:13px;color:inherit}
.search input:focus{outline:none;border-color:var(--accent);background:#fff;box-shadow:0 0 0 3px #1267821a}
.search kbd{position:absolute;right:9px;top:8px;font:10px/1.6 ui-monospace,monospace;color:var(--muted);border:1px solid var(--line);border-radius:4px;padding:0 4px;background:#fff}
.legend{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:#fff;color:var(--muted);border-radius:999px;padding:4px 10px;font-size:11.5px;cursor:pointer;transition:background .15s,color .15s,border-color .15s}
.chip .dot{width:7px;height:7px;border-radius:50%;background:var(--c)}
.chip:hover{color:var(--ink)}
.chip.on{color:var(--ink);border-color:var(--c);background:var(--soft)}
.graph-wrap{padding:4px 10px 0}
svg{width:100%;height:auto;display:block;min-height:300px}
.group-head text{font-size:11.5px;font-weight:600;letter-spacing:.03em}
.group-head .count{font-weight:400;fill:#93a3ad}
.node{cursor:pointer;transition:opacity .16s}
.node .body{stroke-width:1.2;transition:stroke-width .16s,filter .16s}
.node .label{font-size:12.5px;font-weight:600;fill:var(--ink)}
.node .owner{font-size:10px;fill:var(--muted);letter-spacing:.01em}
.node text{pointer-events:none;user-select:none}
.node:hover .body{stroke-width:2}
.node.hit .body{stroke-width:2.6}
.node.hl .body{stroke-width:1.9}
.node.selected .body{stroke-width:2.6;filter:drop-shadow(0 2px 8px #17232d22)}
.edge .line{fill:none;stroke:var(--edge);stroke-width:1.5;transition:stroke .16s,stroke-width .16s}
.edge .hit{fill:none;stroke:transparent;stroke-width:15;cursor:pointer}
.edge.hl .line{stroke-width:2.4}
.edge[data-kind="flow"] .line{stroke-dasharray:5 4}
.dim{opacity:.13}
.footer{display:flex;gap:18px;flex-wrap:wrap;padding:0 24px 26px;color:var(--muted);font-size:11.5px}
.footer span{max-width:80ch}
#panel{position:fixed;top:0;right:0;height:100%;width:min(480px,94vw);background:var(--panel);border-left:1px solid var(--line);box-shadow:-16px 0 44px #17232d12;transform:translateX(104%);transition:transform .22s ease;z-index:30;display:flex;flex-direction:column}
#panel.open{transform:none}
.p-head{padding:18px 20px 14px;border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:flex-start}
.p-head h2{margin:4px 0 0;font-size:19px;line-height:1.2;letter-spacing:-.01em}
.p-group{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--c);font-weight:600}
.p-group .dot{width:7px;height:7px;border-radius:50%;background:var(--c)}
.p-meta{margin-top:6px;font:11.5px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--muted)}
.p-meta a{color:var(--accent);text-decoration:none;border-bottom:1px dotted #12678266;white-space:nowrap}
.p-meta a:hover{border-bottom-style:solid}
.p-close{margin-left:auto;border:1px solid var(--line);background:#fff;border-radius:8px;width:30px;height:30px;font-size:17px;line-height:1;color:var(--muted);cursor:pointer;flex:none}
.p-close:hover{color:var(--ink);border-color:#c8d4da}
.p-body{padding:16px 20px 40px;overflow:auto;flex:1}
.p-body p{margin:0 0 14px;color:#2b3b46}
.formula{overflow-x:auto;margin:0 0 12px;padding:12px 14px;border-radius:10px;border:1px solid #dcebe7;background:#f2faf7;color:#123c37;font-family:"STIX Two Math","Latin Modern Math","Cambria Math",Georgia,serif;font-size:1.16rem;line-height:2;white-space:normal}
.formula .frac{display:inline-flex;flex-direction:column;vertical-align:-.48em;text-align:center;font-size:.92em;margin:0 .13em}
.formula .frac .num{padding:0 .2em;border-bottom:1.2px solid currentColor;line-height:1.12}
.formula .frac .den{padding:0 .2em;line-height:1.12}
.formula sup,.formula sub{font-size:.68em;line-height:0}
.formula i{font-style:italic}
.formula .rm{font-style:normal}
.formula .fn{font-style:normal;padding-right:.12em}
.formula .op{margin:0 .17em}
.formula .sym{margin-right:.05em}
.formula .punc{margin-right:.1em}
.formula .br{margin:0 .015em}
.formula .thin{display:inline-block;width:.18em}
.formula .thin2{display:inline-block;width:.32em}
.formula .quad{display:inline-block;width:1em}
.formula .qquad{display:inline-block;width:1.8em}
.formula .cal{font-style:italic;font-family:"STIX Two Math",Georgia,serif}
.formula .prime{font-style:normal}
.links{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 16px}
.links .lbl{width:100%;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-top:6px}
.links button{border:1px solid var(--line);background:#fff;border-radius:7px;padding:3px 8px;font:11.5px ui-monospace,monospace;color:#2b3b46;cursor:pointer}
.links button:hover{border-color:var(--accent);color:var(--accent)}
.code{margin:0;background:#f7f9fa;border:1px solid var(--line);border-radius:10px;padding:10px 0;overflow:auto;max-height:52vh;font:11.5px/1.65 ui-monospace,SFMono-Regular,Consolas,monospace;color:#26343d}
.cl{display:block;white-space:pre;padding:0 12px}
.cl.hl{background:#e7f3f1;box-shadow:inset 2px 0 0 #147d70}
.cl .n{display:inline-block;width:3.1em;padding-right:.9em;text-align:right;color:#9aabb4;user-select:none}
.cl.hl .n{color:#147d70}
@media (max-width:860px){
  header{padding:11px 14px;gap:10px}
  .search{flex:1 1 100%;order:3}
  .search input{width:100%}
  .legend{order:2;margin-left:0}
  .graph-wrap{padding:0 2px;overflow-x:auto;-webkit-overflow-scrolling:touch}
  .graph-wrap svg{min-width:1080px}
  .footer{padding:0 14px 120px}
  #panel{width:100%;height:78%;top:auto;bottom:0;border-left:0;border-top:1px solid var(--line);border-radius:16px 16px 0 0;transform:translateY(104%)}
  #panel.open{transform:none}
}
</style>
</head>
<body>
<header>
  <div class="brand">Pipeline spray · graph<small>__SUBTITLE__</small></div>
  <div class="search">
    <input id="search" type="search" placeholder="Tìm hàm, công thức, từ khoá…" autocomplete="off" aria-label="Tìm node">
    <kbd>Enter</kbd>
  </div>
  <div class="legend" id="legend"></div>
</header>
<main>
  <div class="graph-wrap"><svg id="graph" role="img" aria-label="Bản đồ pipeline spray"></svg></div>
  <div class="footer">
    <span>Bấm node để xem mô tả, công thức và source. Hover để soi đường đi. <b>Esc</b> đóng panel. Nét đứt = luồng dữ liệu, không phải call-site.</span>
    <span>Nhóm dữ liệu gọi từ evaluator; <code>PlumeTransform</code> không tự đọc file — thiếu <code>plume_context</code> thì raise.</span>
  </div>
</main>
<aside id="panel" aria-hidden="true"></aside>
<script>
const DATA = __DATA_JSON__;
const SVGNS = "http://www.w3.org/2000/svg";
const nodesById = new Map(DATA.nodes.map(n => [n.id, n]));
const groupsById = new Map(DATA.groups.map(g => [g.id, g]));
const outgoing = new Map();
const incoming = new Map();
const neighbors = new Map(DATA.nodes.map(n => [n.id, new Set()]));
for (const edge of DATA.edges) {
  if (!outgoing.has(edge.source)) outgoing.set(edge.source, []);
  if (!incoming.has(edge.target)) incoming.set(edge.target, []);
  outgoing.get(edge.source).push(edge);
  incoming.get(edge.target).push(edge);
  neighbors.get(edge.source).add(edge.target);
  neighbors.get(edge.target).add(edge.source);
}
const nodeEls = new Map();
const edgeEls = [];
const svg = document.getElementById("graph");
const panel = document.getElementById("panel");
const search = document.getElementById("search");
let selected = null;
let activeGroups = new Set();
const haystack = new Map(DATA.nodes.map(n => {
  const text = [n.id, n.label, n.owner, n.description, groupsById.get(n.group).title, n.file, formulaText(n)].join(" ");
  return [n.id, normalize(text)];
}));

function formulaText(node) {
  return node.formulas.map(item => item.html.replace(/<[^>]+>/g, " ")).join(" ");
}
function normalize(value) {
  return (value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/[_.,;:(){}\[\]\\\/]/g, " ").replace(/\s+/g, " ").trim();
}
function esc(value) {
  return String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
}
function markerId(group) { return "arrow-" + group; }

function renderLegend() {
  const legend = document.getElementById("legend");
  legend.innerHTML = DATA.groups.map(group =>
    `<button class="chip" data-group="${group.id}" style="--c:${group.color};--soft:${group.soft}" title="${esc(group.note || group.title)}"><span class="dot"></span>${esc(group.title)}</button>`
  ).join("");
  legend.querySelectorAll(".chip").forEach(chip => {
    chip.addEventListener("click", () => {
      const id = chip.dataset.group;
      if (activeGroups.has(id)) activeGroups.delete(id); else activeGroups.add(id);
      chip.classList.toggle("on", activeGroups.has(id));
      applyFilters();
    });
  });
}

function renderGraph() {
  const parts = [];
  const markers = ['<marker id="arrow-neutral" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#b9c8d1"/></marker>'];
  for (const group of DATA.groups) {
    markers.push(`<marker id="${markerId(group.id)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${group.color}"/></marker>`);
  }
  parts.push(`<defs>${markers.join("")}</defs>`);

  for (const header of DATA.headers) {
    parts.push(`<g class="group-head"><text x="${header.x}" y="${header.y}" fill="${header.color}">${esc(header.title)} <tspan class="count">${header.count}</tspan></text></g>`);
  }

  for (const edge of DATA.edges) {
    parts.push(`<g class="edge" data-s="${esc(edge.source)}" data-t="${esc(edge.target)}" data-group="${edge.source_group}" data-kind="${edge.kind}"><path class="hit" d="${edge.path}"/><path class="line" d="${edge.path}" marker-end="url(#arrow-neutral)"/></g>`);
  }

  for (const node of DATA.nodes) {
    parts.push(`<g class="node" data-id="${esc(node.id)}" transform="translate(${node.x},${node.y})"><rect class="body" width="${DATA.node_size.width}" height="${DATA.node_size.height}" rx="11" fill="${node.soft}" stroke="${node.color}" stroke-opacity=".38"/><rect x="0" y="9" width="4" height="${DATA.node_size.height - 18}" rx="2" fill="${node.color}"/><text class="label" x="14" y="20">${esc(node.label)}</text><text class="owner" x="14" y="34">${esc(node.owner)}</text></g>`);
  }

  svg.setAttribute("viewBox", `0 0 ${DATA.width} ${DATA.height}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMin meet");
  svg.innerHTML = parts.join("");
  for (const el of svg.querySelectorAll(".node")) nodeEls.set(el.dataset.id, el);
  edgeEls.push(...svg.querySelectorAll(".edge"));
}

function clearHighlight() {
  svg.querySelectorAll(".dim, .hl").forEach(el => el.classList.remove("dim", "hl"));
  edgeEls.forEach(edge => edge.querySelector(".line").setAttribute("stroke", ""));
}

function applyFilters() {
  const query = normalize(search.value.trim());
  const filtering = query.length > 0 || activeGroups.size > 0;
  svg.querySelectorAll(".node").forEach(el => {
    const node = nodesById.get(el.dataset.id);
    const groupOk = activeGroups.size === 0 || activeGroups.has(node.group);
    const textOk = !query || haystack.get(node.id).includes(query);
    const visible = groupOk && textOk;
    el.classList.toggle("dim", !visible);
    el.classList.toggle("hit", filtering && visible);
  });
  for (const edge of edgeEls) {
    const source = nodesById.get(edge.dataset.s);
    const target = nodesById.get(edge.dataset.t);
    const sourceOk = activeGroups.size === 0 || activeGroups.has(source.group);
    const targetOk = activeGroups.size === 0 || activeGroups.has(target.group);
    const textOk = !query || haystack.get(source.id).includes(query) || haystack.get(target.id).includes(query);
    edge.classList.toggle("dim", !(sourceOk && targetOk && textOk));
  }
  return filtering;
}

function highlightNode(id) {
  if (applyFilters()) return;
  const connected = new Set([id, ...neighbors.get(id)]);
  svg.querySelectorAll(".node").forEach(el => {
    if (!connected.has(el.dataset.id)) el.classList.add("dim");
    else el.classList.add("hl");
  });
  for (const edge of edgeEls) {
    if (edge.dataset.s === id || edge.dataset.t === id) {
      edge.classList.add("hl");
      edge.querySelector(".line").setAttribute("stroke", groupsById.get(nodesById.get(edge.dataset.s).group).color);
    } else {
      edge.classList.add("dim");
    }
  }
}

function highlightEdge(edge) {
  if (applyFilters()) return;
  for (const el of edgeEls) {
    if (el === edge) {
      el.classList.add("hl");
      el.querySelector(".line").setAttribute("stroke", groupsById.get(nodesById.get(el.dataset.s).group).color);
    } else {
      el.classList.add("dim");
    }
  }
  svg.querySelectorAll(".node").forEach(el => {
    if (el.dataset.id === edge.dataset.s || el.dataset.id === edge.dataset.t) el.classList.add("hl");
    else el.classList.add("dim");
  });
}

function formatFormula(item) {
  return `<div class="formula">${item.html}</div>`;
}

function linkButtons(edges, key) {
  if (!edges.length) return "";
  return edges.map(edge => {
    const id = key === "in" ? edge.source : edge.target;
    return `<button data-target="${esc(id)}">${esc(nodesById.get(id).label)}</button>`;
  }).join("");
}

function openPanel(id) {
  const node = nodesById.get(id);
  if (!node) return;
  if (selected) nodeEls.get(selected)?.classList.remove("selected");
  selected = id;
  nodeEls.get(id)?.classList.add("selected");
  const group = groupsById.get(node.group);
  const source = DATA.sources[id];
  const lines = source.code.split("\n");
  const highlight = new Set(node.highlight_lines);
  const code = lines.map((line, index) => {
    const number = source.start_line + index;
    const cls = highlight.has(number) ? "cl hl" : "cl";
    return `<span class="${cls}"><span class="n">${number}</span>${esc(line)}</span>`;
  }).join("");
  const formulas = node.formulas.map(formatFormula).join("");
  const out = outgoing.get(id) || [];
  const inc = incoming.get(id) || [];
  const links = [
    out.length ? `<div class="lbl">Gọi tới</div>${linkButtons(out, "out")}` : "",
    inc.length ? `<div class="lbl">Được gọi từ</div>${linkButtons(inc, "in")}` : "",
  ].join("");
  panel.innerHTML = `
    <div class="p-head">
      <div>
        <div class="p-group" style="--c:${group.color}"><span class="dot"></span>${esc(group.title)}</div>
        <h2>${esc(node.label)}</h2>
        <div class="p-meta">${esc(node.owner)} · ${esc(node.file)}:${node.start_line}–${node.end_line} · <a href="${esc(node.editor_link)}">mở trong editor ↗</a></div>
      </div>
      <button class="p-close" aria-label="Đóng panel">×</button>
    </div>
    <div class="p-body">
      <p>${esc(node.description)}</p>
      ${formulas}
      ${links ? `<div class="links">${links}</div>` : ""}
      <pre class="code">${code}</pre>
    </div>`;
  panel.classList.add("open");
  panel.setAttribute("aria-hidden", "false");
  panel.querySelector(".p-close").addEventListener("click", closePanel);
  panel.querySelectorAll(".links button").forEach(button => {
    button.addEventListener("click", () => openPanel(button.dataset.target));
  });
}

function closePanel() {
  panel.classList.remove("open");
  panel.setAttribute("aria-hidden", "true");
  if (selected) nodeEls.get(selected)?.classList.remove("selected");
  selected = null;
}

svg.addEventListener("pointerover", event => {
  const node = event.target.closest(".node");
  if (node) { highlightNode(node.dataset.id); return; }
  const edge = event.target.closest(".edge");
  if (edge) highlightEdge(edge);
});
svg.addEventListener("pointerout", event => {
  const related = event.relatedTarget;
  if (related && svg.contains(related) && (related.closest(".node") || related.closest(".edge"))) return;
  clearHighlight();
  activeEdge = null;
});
svg.addEventListener("click", event => {
  const node = event.target.closest(".node");
  if (node) { openPanel(node.dataset.id); return; }
  const edge = event.target.closest(".edge");
  if (edge) openPanel(edge.dataset.t);
});
search.addEventListener("input", () => { applyFilters(); });
search.addEventListener("keydown", event => {
  if (event.key === "Enter") {
    const hit = [...svg.querySelectorAll(".node.hit")][0];
    if (hit) {
      hit.scrollIntoView({block: "nearest", inline: "center", behavior: "smooth"});
      openPanel(hit.dataset.id);
      hit.classList.remove("hit");
    }
  } else if (event.key === "Escape") {
    search.value = "";
    search.blur();
    applyFilters();
  }
});
document.addEventListener("keydown", event => {
  if (event.key === "Escape") closePanel();
  if (event.key === "/" && document.activeElement !== search) {
    event.preventDefault();
    search.focus();
    search.select();
  }
});
renderLegend();
renderGraph();
applyFilters();
</script>
</body>
</html>
"""


def build_html(payload: dict) -> str:
    page_payload = json.loads(json.dumps(payload, ensure_ascii=False))
    for formula in page_payload["formulas"]:
        formula.pop("latex", None)
    for node in page_payload["nodes"]:
        for formula in node["formulas"]:
            formula.pop("latex", None)
    data = json.dumps(page_payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")
    subtitle = f"Sinh từ {payload['generated_from']} · {len(payload['nodes'])} node · {len(payload['edges'])} edge"
    page = PAGE.replace("__DATA_JSON__", data)
    page = page.replace("__TITLE__", html_module.escape(payload["title"]))
    page = page.replace("__SUBTITLE__", html_module.escape(subtitle))
    return page


def main() -> None:
    payload = build_payload()
    verify_sources(payload)
    JSON_OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    HTML_OUT.write_text(build_html(payload), encoding="utf-8")

    verify_payload = json.loads(JSON_OUT.read_text(encoding="utf-8"))
    assert verify_payload["sources"], "JSON missing sources"
    page = HTML_OUT.read_text(encoding="utf-8")
    offline = page.replace("http://www.w3.org/2000/svg", "")
    if "http://" in offline or "https://" in offline:
        raise SystemExit("HTML must not reference the network")
    if re.search(r"<(?:script|link|img)[^>]+(?:src|href)=", page):
        raise SystemExit("HTML must not load external assets")
    print(f"Wrote {JSON_OUT.relative_to(ROOT)} ({JSON_OUT.stat().st_size} bytes)")
    print(f"Wrote {HTML_OUT.relative_to(ROOT)} ({HTML_OUT.stat().st_size} bytes)")
    print(f"nodes={len(payload['nodes'])} edges={len(payload['edges'])}")
    counts = {}
    for node in payload["nodes"]:
        counts[node["group"]] = counts.get(node["group"], 0) + 1
    print("groups: " + ", ".join(f"{group['id']}={counts.get(group['id'], 0)}" for group in GROUPS))


if __name__ == "__main__":
    main()
