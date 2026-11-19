#!/usr/bin/env python3
"""Compress a Kaggle kernel log into a one-screen failure card.

Usage: kernel_card.py <logfile> [outfile]

Kaggle ``kernels logs`` emits JSON lines like
``,{"stream_name":"stdout","time":540.7,"data":"OPS_OK\\n"}``; this script
decodes them back into plain text first (falling back to the raw line when a
line is not JSON), then prints:

  1. status line if present,
  2. every marker line (SMOKE_*, OPS_OK, ...) with line numbers,
  3. the last traceback block (up to 45 lines),
  4. the last 12 non-empty lines.

One read of the card is enough to write the next task brief.
"""
import json
import re
import sys

MARK = re.compile(
    r"(SMOKE_[A-Z_]+|MINI_SPLIT_[A-Z_]+|OPS_OK|STACK_OK|MIT_PIN_OK|"
    r"CLONE_OK|ENV_OK|GPU_OK|BUILD_OK)"
)


def decode(raw_lines):
    """Turn Kaggle's JSON-per-line log into plain text lines."""
    text = []
    for line in raw_lines:
        stripped = line.lstrip(",").strip()
        if stripped.startswith("{"):
            try:
                obj = json.loads(stripped)
            except ValueError:
                text.append(line)
                continue
            data = obj.get("data")
            if isinstance(data, str):
                text.extend(data.splitlines())
            continue
        text.append(line)
    return text


def main():
    src = sys.argv[1]
    raw = open(src, encoding="utf-8", errors="replace").read().splitlines()
    lines = [l.rstrip() for l in decode(raw)]
    lines = [l for l in lines if l.strip()]

    out = ["# kernel failure card: %s" % src, "raw_lines=%d text_lines=%d" % (len(raw), len(lines))]

    status = [l for l in lines if "KernelWorkerStatus" in l]
    if status:
        out.append("status: %s" % status[-1].strip())

    out.append("\n## markers")
    hits = [(i, l) for i, l in enumerate(lines, 1) if MARK.search(l)]
    for i, line in hits:
        out.append("%5d | %s" % (i, line.strip()[:220]))
    if not hits:
        out.append("(none)")

    starts = [i for i, l in enumerate(lines) if l.startswith("Traceback (most recent call last)")]
    out.append("\n## last traceback (block %d of %d)" % (len(starts), len(starts)))
    if starts:
        tail = [l for l in lines[starts[-1]:] if l.strip() or True][:45]
        out.extend(tail)
    else:
        out.append("(none)")

    out.append("\n## tail")
    out.extend(lines[-12:])

    text = "\n".join(out)
    print(text)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w", encoding="utf-8").write(text + "\n")


if __name__ == "__main__":
    main()