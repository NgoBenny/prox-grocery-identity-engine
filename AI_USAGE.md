# AI usage

Working log, cleaned up into the final write-up in the docs step.

## Tools

- ChatGPT: first implementation plan.
- Claude Code (Claude Opus 5.5, desktop app): plan revision, scaffolding, fixtures, code, reviews.

## Corrections log (candidates for the "2 corrections")

1. **Prescribed `type` values were rewritten.** The ChatGPT plan's example catalog used `type: "chicken breast"` for C103, but the assessment table gives `type: chicken` for both C103 (breast) and C104 (broth), and `tuna` for both C101 and C102. Kept Prox's values verbatim (`tests/test_fixtures.py::test_prescribed_starters_are_verbatim`) and moved the distinction to form, category and name modifiers.

## Review gate log

| Push | Skills run | Findings (freq x severity) | Action |
|---|---|---|---|
| Step 1 (fixtures + loader) | `/code-review`, `ponytail:ponytail-review` | null optional listing fields rejected (4x6); extra keys rejected (3x6); minimal truth file rejected (3x6); fixtures path breaks in non-editable install (2x6); generator KeyError on unknown category (2x4); UTF-8 BOM breaks both readers (2x4); bool/str price coerced (1x4) | First six fixed, with tests in `tests/test_fixtures.py`; last one filed as issue #1 |
