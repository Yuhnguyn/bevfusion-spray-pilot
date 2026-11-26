## Agent skills

### Issue tracker

Issues and specs live as markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Five default roles: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.

### Generator pipeline map

When changing the standard spray simulation path or one of its formulas, read and update `docs/pipeline-map.md`, then regenerate `docs/pipeline-map.html` with `python scripts/render_pipeline_map.py`.

Rebuild the interactive graph and the article together with `python scripts/build_pipeline_graph.py && python scripts/render_pipeline_map.py`.
