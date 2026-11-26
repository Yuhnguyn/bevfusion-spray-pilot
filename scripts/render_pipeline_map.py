#!/usr/bin/env python3
"""Render the canonical Markdown pipeline map as a standalone HTML page."""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "pipeline-map.md"
OUTPUT = ROOT / "docs" / "pipeline-map.html"


def slug(text: str) -> str:
    return re.sub(r"[^\w-]+", "-", text.lower(), flags=re.UNICODE).strip("-")


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"\\\[(.+?)\\\]", r'<span class="formula">\1</span>', text)
    text = re.sub(r"\\\((.+?)\\\)", r'<span class="formula-inline">\1</span>', text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def render_markdown(source: str) -> str:
    """Render the small Markdown subset used by the maintained map."""
    lines = source.splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    list_open = False
    table_rows: list[list[str]] = []
    code_lines: list[str] | None = None

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph = []

    def close_list() -> None:
        nonlocal list_open
        if list_open:
            out.append("</ul>")
            list_open = False

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        out.append("<div class=\"table-wrap\"><table>")
        for index, row in enumerate(table_rows):
            if index == 1 and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in row):
                continue
            tag = "th" if index == 0 else "td"
            cells = "".join(f"<{tag}>{inline(cell.strip())}</{tag}>" for cell in row)
            out.append(f"<tr>{cells}</tr>")
        out.append("</table></div>")
        table_rows = []

    for line in lines:
        if code_lines is not None:
            if line.startswith("```"):
                out.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
                code_lines = None
            else:
                code_lines.append(line)
            continue
        if line.startswith("```"):
            flush_paragraph(); close_list(); flush_table()
            code_lines = []
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph(); close_list()
            table_rows.append([cell for cell in line.strip("|").split("|")])
            continue
        flush_table()
        if line.startswith("#"):
            flush_paragraph(); close_list()
            level = min(len(line) - len(line.lstrip("#")), 6)
            title = line[level:].strip()
            anchor = slug(title)
            out.append(f'<h{level} id="{anchor}">{inline(title)}</h{level}>')
        elif line.startswith("> "):
            flush_paragraph(); close_list()
            out.append(f"<blockquote>{inline(line[2:])}</blockquote>")
        elif line.startswith("- "):
            flush_paragraph()
            if not list_open:
                out.append("<ul>"); list_open = True
            out.append(f"<li>{inline(line[2:])}</li>")
        elif not line.strip():
            flush_paragraph(); close_list()
        else:
            close_list()
            paragraph.append(line.strip())
    flush_paragraph(); close_list(); flush_table()
    if code_lines is not None:
        out.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
    return "\n".join(out)


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8")
    body = render_markdown(markdown)
    sections = []
    for match in re.finditer(r"^## (.+)$", markdown, flags=re.MULTILINE):
        title = match.group(1).strip()
        if title != "Cập nhật bản đồ":
            sections.append(f'<a href="#{slug(title)}">{html.escape(title)}</a>')
    navigation = '<nav class="index" aria-label="Các phần">' + "".join(sections) + "</nav>"
    body = body.replace('<h2 id="luồng-tổng-quát">', navigation + '<h2 id="luồng-tổng-quát">', 1)
    page = f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bản đồ công thức pipeline spray</title>
<style>
:root{{color-scheme:light;--ink:#17232d;--muted:#526575;--line:#d7e0e7;--paper:#fff;--wash:#f2f6f8;--blue:#126782;--teal:#147d70;}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--wash);color:var(--ink);font:16px/1.65 system-ui,-apple-system,"Segoe UI",sans-serif}}
header{{background:#102b3a;color:#f5fbff;padding:2.5rem max(1.25rem,calc((100vw - 1080px)/2))}}header p{{color:#c5d9e3;max-width:70ch}}
main{{max-width:1080px;margin:1.5rem auto;padding:0 1rem 4rem}}h1,h2,h3{{line-height:1.25}}h1{{font-size:clamp(2rem,5vw,3rem);margin:0}}h2{{margin-top:2.6rem;padding-bottom:.45rem;border-bottom:1px solid var(--line)}}h3{{margin-top:1.8rem;color:var(--blue)}}
a{{color:var(--blue);text-decoration-thickness:1px;text-underline-offset:3px}}p,li{{max-width:85ch}}blockquote{{margin:1rem 0;padding:.8rem 1rem;border-left:4px solid #d38b28;background:#fff7e7;color:#563e1d}}
pre,code{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}}pre{{overflow:auto;padding:1rem;border-radius:10px;background:#102b3a;color:#e8f4fa;line-height:1.55}}:not(pre)>code{{background:#e6eef2;border-radius:4px;padding:.1rem .3rem}}
.table-wrap{{overflow:auto;margin:1rem 0 1.5rem}}table{{border-collapse:collapse;width:100%;background:var(--paper);font-size:.94rem}}th,td{{text-align:left;vertical-align:top;padding:.65rem .75rem;border:1px solid var(--line)}}th{{background:#e6eff3;color:#163e50}}
.formula{{display:block;overflow:auto;margin:.7rem 0;padding:.8rem 1rem;border-left:4px solid var(--teal);background:#e7f3f1;font:600 1.08rem/1.7 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:nowrap}}.formula-inline{{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;background:#e7f3f1;padding:.12rem .25rem;border-radius:4px}}
.index{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.7rem;margin:1rem 0}}.index a{{display:block;background:white;border:1px solid var(--line);border-radius:8px;padding:.75rem;text-decoration:none}}.index a:hover{{border-color:var(--teal);box-shadow:0 2px 10px #173b4a18}}
.top{{position:fixed;right:1rem;bottom:1rem;border-radius:99px;background:var(--teal);color:white;padding:.55rem .9rem;text-decoration:none;box-shadow:0 2px 8px #0002}}
@media(max-width:600px){{body{{font-size:15px}}header{{padding:1.6rem 1rem}}main{{padding:0 .75rem 3rem}}}}
</style></head><body><header><h1>Bản đồ công thức pipeline spray</h1><p>Trang được sinh từ <code>docs/pipeline-map.md</code>. Sửa Markdown rồi chạy <code>python scripts/render_pipeline_map.py</code>.</p></header><main>{body}</main><a class="top" href="#">Lên đầu</a></body></html>"""
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"Rendered {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
