# CLAUDE.md

Do not design for rare or future cases nobody asked about

Read `AGENTS.md` for the bug-triage and integrity rules; they apply to every change.

## Commands

```bash
uv sync
uv run pytest -q
uv run python scripts/generate_fixtures.py --check
uv run prox-match demo
```
