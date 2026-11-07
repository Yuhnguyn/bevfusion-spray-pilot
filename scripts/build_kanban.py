#!/usr/bin/env python3
"""Build docs/kanban.html from the issue tracker.

Run from the repo root:  python3 scripts/build_kanban.py

Sources of truth (nothing about a ticket's state is written in this file):
  * .scratch/spray-augmentation/STATUS.md — "## Bảng ticket" table (#, Việc,
    Trạng thái, Bằng chứng / next) and the "Việc tiếp theo" line.
  * .scratch/spray-augmentation/issues/NN-*.md — title, checkbox criteria,
    "Blocked by", and repo paths worth showing.

The HTML is self-contained (no CDN, no storage) so it can be published as an
artifact. Re-run after any ticket/spec change and publish again.
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / ".scratch" / "spray-augmentation"
ISSUES = SCRATCH / "issues"
STATUS = SCRATCH / "STATUS.md"
SPEC = SCRATCH / "spec.md"
OUT = ROOT / "docs" / "kanban.html"
TEMPLATE = Path(__file__).parent / "kanban_template.html"

# Phase grouping only — progress and every ticket field come from the sources
# above. Keep the existing P0..P6 cards; do not invent new phases.
PHASES = [
    {
        "id": "P0",
        "name": "Nền móng & kiểm chứng",
        "desc": "Chốt version, môi trường, checkpoint, dataset, evaluator, velocity.",
        "tickets": ["01", "02", "02b", "03", "04", "05", "19", "24"],
    },
    {
        "id": "P1",
        "name": "Pipeline chèn plume",
        "desc": "Transform, clean points, routing hai nhánh, test end-to-end.",
        "tickets": ["07", "08", "09", "15", "21", "22", "23"],
    },
    {
        "id": "P2",
        "name": "Đo lường & đối chứng",
        "desc": "Adapter evaluator, config A/B, arm lọc spray B0, eligibility.",
        "tickets": ["06", "10", "14", "18"],
    },
    {
        "id": "P3",
        "name": "Mini A/B",
        "desc": "Train 2 arm trên tập nhỏ, eval trên spray held-out.",
        "tickets": ["11"],
    },
    {
        "id": "P4",
        "name": "Quyết định",
        "desc": "Mở rộng hay dừng, dựa trên tiêu chí đã đăng ký trước.",
        "tickets": ["13"],
    },
    {
        "id": "P5",
        "name": "Tham chiếu",
        "desc": "Thống kê spray thật để kiểm tra simulator (không dùng để train/eval).",
        "tickets": ["12"],
    },
    {
        "id": "P6",
        "name": "Hình học plume",
        "desc": "Đo dạng cụm thật, đổi cách rải điểm, và nhìn lại bằng ảnh/clip.",
        "tickets": ["16", "17", "20"],
    },
]

# Top-level roots that make a backticked token look like a repo path.
PATH_ROOTS = {
    "docs", "spray", "tests", "scripts", "proxy_eval", "kaggle", "mit",
    "configs", "data", "results", ".scratch", "interactive", "kernel",
    "notebook-kernel", "archive", "third_party",
}

GLOSSARY = [
    ("Checkpoint", "File chứa trọng số đã train. Nạp vào model để model có 'kiến thức'."),
    ("Forward", "Chạy model một lần từ input đến output dự đoán."),
    ("Tensor / shape", "Mảng số nhiều chiều. Shape là kích thước từng chiều, ví dụ [6,1,256,704]."),
    ("Plume", "Cụm điểm nước bắn phía sau xe đang chạy trên đường ướt."),
    ("infos.pkl", "File danh mục frame: đường dẫn ảnh/LiDAR, calibration, GT. Pipeline đọc file này."),
    ("Proxy mAP", "Thước đo phát hiện tự viết, đơn giản hơn NDS của nuScenes, dùng để so A/B."),
    ("Paired A/B", "So sánh hai phiên bản trên cùng một frame; chỉ khác đúng một biến."),
    ("Held-out spray", "Bộ tham số spray không dùng khi train, chỉ dùng khi eval."),
    ("Precondition", "Điều kiện phải xong trước khi được làm tiếp."),
    ("Blocked by", "Ticket này phải chờ ticket khác xong mới bắt đầu."),
    ("Checkbox", "Tiêu chí nghiệm thu. Chỉ tick khi có bằng chứng thật."),
]


def warn(message):
    print(f"warning: {message}", file=sys.stderr)


def git(*args):
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        warn(f"git {' '.join(args)} failed: {exc}")
        return ""


def sort_key(tid):
    match = re.match(r"(\d+)([a-z]?)", tid)
    return (int(match.group(1)), match.group(2)) if match else (10**9, tid)


def strip_markdown(text):
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip()


def status_kind(raw):
    low = raw.lower()
    if "done" in low:
        return "done"
    if "blocked" in low:
        return "blocked"
    if "ready" in low:
        return "ready"
    if "progress" in low or "doing" in low or "đang" in low:
        return "progress"
    return "triage"


def status_sha(raw):
    return "+".join(re.findall(r"`([0-9a-f]{7,40})`", raw))


def parse_status_table(text):
    """Parse the '## Bảng ticket' markdown table into ordered rows."""
    section = re.search(r"^##\s+Bảng ticket\s*$(.*?)(?=^##\s)", text, re.M | re.S)
    if not section:
        raise SystemExit(f"error: no '## Bảng ticket' table in {STATUS}")
    rows = []
    for line in section.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or set(cells[0]) <= {"-", ":", " "}:
            continue
        tid = cells[0]
        if not re.fullmatch(r"\d+[a-z]?", tid):
            continue
        rows.append({
            "id": tid,
            "job": strip_markdown(cells[1]),
            "status_raw": cells[2],
            "evidence": strip_markdown(cells[3]),
        })
    if not rows:
        raise SystemExit(f"error: empty ticket table in {STATUS}")
    return rows


def parse_next_line(text):
    match = re.search(r"\*\*Việc tiếp theo:\*\*\s*(.+)$", text, re.M)
    if not match:
        return {"headline": "", "detail": "", "ticket": None}
    raw = strip_markdown(match.group(1))
    ids = re.findall(r"`(\d+[a-z]?)`", match.group(1))
    headline = re.split(r"(?<=[a-z0-9)])\s*\.\s+", raw)[0].rstrip(".")
    return {"headline": headline, "detail": raw, "ticket": ids[0] if ids else None}


def parse_checkboxes(text):
    """Count acceptance checkboxes only.

    Criterion prose is deliberately not rendered: it quotes commands and paths
    (e.g. the `git rm`-ed ticket 17 path) that would leak dead references into
    the published artifact.
    """
    return [mark.lower() == "x" for mark in re.findall(r"^\s*-\s*\[([ xX])\]", text, re.M)]


def checkbox_heading(text):
    """The acceptance section whose checklist was counted, if it has one."""
    current = ""
    for line in text.splitlines():
        heading = re.match(r"^##+\s+(.+)$", line)
        if heading:
            current = strip_markdown(heading.group(1))
        elif re.match(r"^\s*-\s*\[[ xX]\]", line):
            if re.match(r"(?i)xong khi|nghiệm thu|done when|acceptance", current):
                return current
            return ""
    return ""


def parse_field(text, label):
    match = re.search(rf"^\*\*(?:{label}):\*\*\s*(.+)$", text, re.M)
    return match.group(1).strip() if match else ""


def parse_blockers(text):
    raw = parse_field(text, "Blocked by|Phụ thuộc")
    if not raw:
        return []
    return [tid for tid in re.findall(r"\b\d+[a-z]?\b", raw) if tid]


def first_paragraph(text):
    lines = text.splitlines()
    i = 1 if lines and lines[0].startswith("# ") else 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith(("#", "|", "```", ">", "- ", "* ", "1.")):
            i += 1
            continue
        if re.match(r"^\*\*(Type|Status|Trạng thái|Blocked by|Phụ thuộc|Chủ|Loại):\*\*", line):
            i += 1
            continue
        line = re.sub(r"^\*\*[^*]+:\*\*\s*", "", line)
        return strip_markdown(line)
    return ""


def section_paragraph(text, heading_pattern):
    match = re.search(
        rf"^##+\s+(?:{heading_pattern})\s*$(.*?)(?=^##+\s|\Z)",
        text,
        re.M | re.S,
    )
    if not match:
        return ""
    return first_paragraph(match.group(1))


def extract_files(text, issue_rel):
    """Repo paths quoted in the ticket; missing ones warn and are dropped."""
    candidates = [issue_rel]
    for token in re.findall(r"`([^`\n]+)`", text):
        token = token.strip()
        if not token or " " in token:
            continue
        token = re.split(r"::", token)[0]
        token = re.sub(r":\d+(?:-\d+)?$", "", token).rstrip(".,;:)")
        if any(ch in token for ch in "*<>{}=") or "..." in token:
            continue
        if token.startswith(("/", "~", "http", "git@")):
            continue
        root = token.lstrip("./").split("/")[0]
        if root not in PATH_ROOTS:
            continue
        candidates.append(token)

    files, seen, warned = [], set(), set()
    for candidate in candidates:
        rel = candidate.rstrip("/") or candidate
        if rel in seen:
            continue
        if (ROOT / rel).exists():
            seen.add(rel)
            files.append(rel)
        elif rel not in warned:
            warned.add(rel)
            warn(f"missing path in {issue_rel}: {rel} (not rendered)")
    return files[:8]


def issue_path(tid):
    matches = sorted(ISSUES.glob(f"{tid}-*.md"))
    return matches[0] if matches else None


def build_ticket(row):
    tid = row["id"]
    path = issue_path(tid)
    text = path.read_text() if path else ""
    issue_rel = str(path.relative_to(ROOT)) if path else ""

    if path is None:
        warn(f"no issue file for ticket {tid}")

    title = ""
    heading = re.search(r"^#\s+(.+)$", text, re.M)
    if heading:
        title = re.sub(r"^\d+[a-z]?:\s*", "", heading.group(1).strip())
    if not title:
        title = row["job"]

    checkboxes = parse_checkboxes(text)
    blockers = parse_blockers(text) if text else []
    kind = status_kind(row["status_raw"])
    if kind == "triage":
        warn(f"ticket {tid}: unrecognized status {row['status_raw']!r} in STATUS.md")

    return {
        "id": tid,
        "title": title,
        "short": first_paragraph(text) if text else "",
        "why": section_paragraph(text, "Vì sao|Bối cảnh|Mục đích|Vấn đề") if text else "",
        "raw_status": row["status_raw"],
        "kind": kind,
        "sha": status_sha(row["status_raw"]) if kind == "done" else "",
        "evidence": row["evidence"],
        "done": sum(1 for done in checkboxes if done),
        "total": len(checkboxes),
        "checks_heading": checkbox_heading(text) if text else "",
        "blockers": [b for b in blockers if b != tid],
        "blocked_labels": [],
        "files": extract_files(text, issue_rel) if text else [],
    }


def parse_spec():
    if not SPEC.exists():
        warn(f"{SPEC.relative_to(ROOT)} not found")
        return {"version": "—", "status": "—"}
    text = SPEC.read_text()
    version = re.search(r"^Version:\s*(\S+)", text, re.M)
    status = re.search(r"^Status:\s*([^—\n]+)", text, re.M)
    return {
        "version": version.group(1) if version else "—",
        "status": strip_markdown(status.group(1)) if status else "—",
    }


def git_timeline(count=12):
    raw = git("log", f"-n{count}", "--pretty=format:%h%x1f%ad%x1f%s", "--date=short")
    entries = []
    for line in raw.splitlines():
        parts = line.split("\x1f")
        if len(parts) != 3:
            continue
        sha, date, subject = parts
        tone = "good" if subject.startswith(("feat", "pm(")) else "warn" if subject.startswith("fix") else ""
        entries.append({
            "when": date,
            "tone": tone,
            "title": subject,
            "body": f"commit {sha}",
        })
    return entries


def main():
    status_text = STATUS.read_text()
    rows = parse_status_table(status_text)
    spec = parse_spec()
    status_updated = re.search(r"\*\*Cập nhật:\*\*\s*([^·\n]+)", status_text)
    commit = git("rev-parse", "--short", "HEAD") or "unknown"

    by_id = {}
    for row in rows:
        by_id[row["id"]] = build_ticket(row)

    phase_of = {}
    for phase in PHASES:
        for tid in phase["tickets"]:
            if tid in by_id:
                phase_of[tid] = phase["id"]
    for tid in by_id:
        if tid not in phase_of:
            warn(f"ticket {tid} is not assigned to a phase; showing '—'")
    for phase in PHASES:
        for tid in phase["tickets"]:
            if tid not in by_id:
                warn(f"phase {phase['id']} lists ticket {tid} missing from STATUS.md")

    for tid in sorted(ISSUES.glob("*.md"), key=lambda p: p.name):
        name = re.match(r"(\d+[a-z]?)", tid.name)
        if name and name.group(1) not in by_id:
            warn(f"issue file {tid.name} has no row in STATUS.md; not rendered")

    tickets = sorted(by_id.values(), key=lambda t: sort_key(t["id"]))
    for ticket in tickets:
        ticket["phase"] = phase_of.get(ticket["id"], "—")
        ticket["blocked_labels"] = [
            b for b in ticket["blockers"] if b in by_id and by_id[b]["kind"] != "done"
        ]

    counts = {kind: sum(1 for t in tickets if t["kind"] == kind)
              for kind in ("done", "progress", "ready", "blocked", "triage")}
    boxes_done = sum(t["done"] for t in tickets)
    boxes_total = sum(t["total"] for t in tickets)

    for phase in PHASES:
        members = [by_id[t] for t in phase["tickets"] if t in by_id]
        phase["done"] = sum(1 for t in members if t["kind"] == "done")
        phase["total"] = len(members)
        phase["percent"] = round(100 * phase["done"] / phase["total"]) if members else 0

    dep_rows = [
        {"id": t["id"], "blockers": [b for b in t["blockers"] if b in by_id]}
        for t in tickets
        if any(b in by_id for b in t["blockers"])
    ]

    data = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": {
            "file": "STATUS.md",
            "commit": commit,
            "updated": strip_markdown(status_updated.group(1)) if status_updated else "—",
        },
        "spec": spec,
        "focus": parse_next_line(status_text),
        "overall": {
            "tickets": len(tickets),
            "done_tickets": counts["done"],
            "percent": round(100 * counts["done"] / len(tickets)) if tickets else 0,
            "boxes_done": boxes_done,
            "boxes_total": boxes_total,
            "counts": counts,
        },
        "phases": PHASES,
        "tickets": tickets,
        "timeline": git_timeline(),
        "glossary": [{"term": term, "def": definition} for term, definition in GLOSSARY],
        "dep_rows": dep_rows,
    }

    template = TEMPLATE.read_text()
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(template.replace("__DATA__", payload))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes): {len(tickets)} tickets, "
          f"{counts['done']} done, source STATUS.md @ {commit}")


if __name__ == "__main__":
    main()
