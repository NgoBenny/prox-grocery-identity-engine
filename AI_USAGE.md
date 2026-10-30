# AI usage

Working log, cleaned up into the final write-up in the docs step.

## Tools

- ChatGPT: first implementation plan.
- Claude Code (Claude Opus 5.5, desktop app): plan revision, scaffolding, fixtures, code, reviews.

## Corrections log (candidates for the "2 corrections")

1. **Prescribed `type` values were rewritten.** The ChatGPT plan's example catalog used `type: "chicken breast"` for C103, but the assessment table gives `type: chicken` for both C103 (breast) and C104 (broth), and `tuna` for both C101 and C102. Kept Prox's values verbatim (`tests/test_fixtures.py::test_prescribed_starters_are_verbatim`) and moved the distinction to form, category and name modifiers.

2. **"family size" treated as product identity.** The first matcher kept every non-size word in the catalog name. `tests/test_matcher.py::test_adversarial[identical title, 18.8 oz]` failed: "Honey Nut Oat Cereal, 18.8 oz" abstained because C112's name also says "family size", so the listing covered only 4/6 of its words (score 0.71). Fix: size descriptors (`family`, `size`, `value`, `jumbo`, `bag`) are stopwords, because size is compared numerically.
3. **Accept threshold too strict.** The provisional 0.75 rejected "Farmhouse Chicken Breast, 1 lb" (score 0.7125) just for not saying "boneless", and failed 5 category tests. Lowered it to 0.70. Safety comes from the hard vetoes and the 0.08 margin rule, and anything under 0.90 still sets `reviewer_flag`. The dev set stayed 28/28; the held-out set has not been run.

## Review gate log

| Push | Skills run | Findings (freq x severity) | Action |
|---|---|---|---|
| Step 1 (fixtures + loader) | `/code-review`, `ponytail:ponytail-review` | null optional listing fields rejected (4x6); extra keys rejected (3x6); minimal truth file rejected (3x6); fixtures path breaks in non-editable install (2x6); generator KeyError on unknown category (2x4); UTF-8 BOM breaks both readers (2x4); bool/str price coerced (1x4) | First six fixed, with tests in `tests/test_fixtures.py`; last one filed as issue #1 |
| Step 2 (matcher, category, search, API, CLI) | `/code-review`, `ponytail:ponytail-review` | brand-only query 400s (3x4); `18-count` / `1/2 gal` unparseable (3x4); branded query returns other brands (3x3); "hot dog" read as pet (3x3); aisle substring "Veggies"->DAIRY (3x2); demo KeyError on custom listings (2x3); pet aisle ignored (2x3); stdout.reconfigure crash (1x5); search scans all decisions (10x1); long unit names counted as identity (3x2); upstream pool backlog (1x3); intent scans whole catalog (1x2) | Ten fixed, with tests; last two filed as issues #2 and #3. My first versions of two new tests asserted the wrong thing (a correct veto, a safe abstain) and were rewritten. |
| Step 3 (evaluate, benchmark) | `/code-review`, `ponytail:ponytail-review` | benchmark crashes on a corpus without our retailer names (2x3); duplicate truth rows double-counted (1x3); report `command` uses `sys.argv` (2x1); negative `--warmup` (1x2) | First fixed with a test; other three filed as issue #5. Ponytail review: no findings. |
| Step 2 independent Codex review | `agent-skills:code-review-and-quality`, `ponytail:ponytail-review` | organic search falls back to conventional spinach at ValueMart (4x5); negative sizes become positive (`-16 oz` matches 16 oz cheddar) (2x5) | Both fixed in shared search/normalization code. Four regression cases failed before the fixes; 133 tests pass afterward, lint clean. API tests required execution outside the sandbox because Windows' internal socket-pair creation hung. Held-out labels were not scored; thresholds and truth files unchanged. |
