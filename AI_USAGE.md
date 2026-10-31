# AI usage

AI tools wrote most of the code, fixtures and docs in this repo. I directed the work, made the product decisions, reviewed the hand labels, approved the matching policy at checkpoints, and ran an independent second review with a different tool. This file records which tool did what, the prompts that shaped the work, the mistakes the tools made and how they were caught, and the calls I made myself.

## Tools and how they were used

| Tool | Model | Used for |
|---|---|---|
| ChatGPT (web) | Not recorded | First implementation plan (`PROX_TRACK_C_IMPLEMENTATION_PLAN.md`, kept outside the repo) |
| Claude Code, desktop app | Claude Opus 5.5 | Plan revision, all scaffolding, fixtures, truth-label drafts, engine code, tests, docs; ran the review skills after implementation Steps 1–3 |
| Codex (desktop) | Not recorded | Independent review of Steps 1–4 with its own review skills; code fixes in Steps 2–3 and documentation corrections in Step 4 |

Review skills used: `/code-review` and `ponytail:ponytail-review` (Claude Code, implementation Steps 1–3); `agent-skills:code-review-and-quality` and `ponytail:ponytail-review` (Codex, including the Step 4 documentation review).

**Generated components:** every file in `src/`, `tests/`, `scripts/`, the fixtures and the docs was drafted by Claude Code, except the Codex fixes listed below. I reviewed the 38 truth labels and the matching policy before they were used, and edited the time log.

## Three prompts that shaped the work

1. **Planning brief** (to Claude Code, with the assessment PDF, the ChatGPT plan and a revised plan attached):
   > /plan given all these resources about the prox take-home assessment, help come up with a plan that can implement the given track

2. **Requirements check against the source** (to Claude Code, which led to the coverage table in the plan, the `scripts/` directory, and explicit failure handling):
   > does this satisfy these instructions?: [the assessment Google Doc] you can check on the google doc using your browser skill

3. **Review-gate rule** (to Claude Code; now in `AGENTS.md` and `CLAUDE.md`):
   > every time you push a big feature to the repo, use the review skills i have installed in claude to review the code to make sure there's no REALISTIC edge case/bugs errors. add to AGENTS.md: rate each bug from 1 to 10 on how often it would happen and how bad it would be. If the two scores multiplied are below 5, just file it as an issue and leave the code alone. for CLAUDE.md: "Do not design for rare or future cases nobody asked about"

## Two errors the AI made, and how they were corrected

**1. ChatGPT's plan quietly changed Prox's prescribed data.** Its example catalog gave C103 `type: "chicken breast"`, but the assessment table gives `type: chicken` for both C103 (breast) and C104 (broth), and `tuna` for both C101 and C102. Building on that plan would have made the "broth vs breast" trap trivially easy by rewriting the fixture.
*Caught by:* Claude Code comparing the plan against the PDF while revising it.
*Fix:* C101–C112 are copied verbatim, and `tests/test_fixtures.py::test_prescribed_starters_are_verbatim` pins them. Breast vs broth is told apart by form, category and name words, as the real data requires.

**2. Claude Code's own bug fix introduced a worse bug.** In the Step 2 review gate, Claude fixed sizes like `18-count` by turning *every* hyphen into a space. That made `-16 oz` parse as a valid 16 oz, so a negative, corrupt size could match the 16 oz cheddar.
*Caught by:* the independent Codex review, which scored it 2 × 5 = 10 and reproduced it with a failing regression test.
*Fix (`015bc04`):* only a hyphen between a number and a unit becomes a space, and `tests/test_normalize.py` now rejects `-16 oz`, `-1 lb` and `2 x -8 oz`.
*Lesson:* a second reviewer using a different tool caught a regression that the tool that wrote the fix missed.

### Other corrections found by tests and reviews

- **"family size" treated as identity.** "Honey Nut Oat Cereal, 18.8 oz" abstained because C112's name says "family size" (score 0.71). Found by a regression test written separately from the truth file. Size words became stopwords, since size is compared numerically.
- **Accept threshold too strict.** The provisional 0.75 rejected "Farmhouse Chicken Breast, 1 lb" (0.7125) just for not saying "boneless". Lowered to 0.70 on dev cases only. The vetoes, the 0.08 margin and the 0.90 review flag still guard precision.
- **Search ranked breaded nuggets above plain chicken breast**, because listing coverage measured retailer marketing words. It now measures the catalog product's own words.
- **Evaluation could overwrite its own truth file** when `--output` pointed at `--truth` (Codex, Step 3, 2 × 8). It's now rejected, with a regression test.
- **Two of Claude's own new tests asserted the wrong thing** in Step 2 (they treated a correct veto and a safe abstain as failures). They were rewritten to test the actual property.

## Debugging notes

- On Windows the console printed the en dash in "Tuna Steak – Sushi Grade" as `�`. The CLI now reconfigures stdout to UTF-8, guarded for streams that can't be reconfigured (a review finding).
- Codex's sandbox hung creating a Windows loopback socket pair during the FastAPI TestClient tests. They passed when run outside the sandbox. This is an environment issue, not a code issue.
- A clean clone from GitHub, a locked install, a non-editable `pip install .` and a real uvicorn server were all checked in Step 3.

## Decisions I made myself

- **Track C**, and the stack: offline rules plus lexical retrieval, no LLM, no database.
- **Organic policy:** a listing that doesn't say organic is treated as non-organic, with lower confidence, rather than abstaining on most produce.
- **C107/C108:** approved always abstaining on the duplicate pair, with a catalog merge as the real fix.
- **Truth integrity:** labels committed before any matcher code; I reviewed and approved all 38 before the engine existed; a dev/held-out split, with the first held-out evaluation after the policy was frozen (`899700d`). Later reproducibility checks did not drive policy tuning.
- **Review discipline:** the frequency × severity rule for every review finding, branch + PR per step, regular merge commits so the history stays auditable, and a second reviewer from a different tool.
- **Matching policy:** approved the 0.70 accept / 0.08 margin / 0.90 auto-approve thresholds and the veto list at the Step 2 checkpoint.
- **Time accounting:** set planning time to 0.45 h; `TIME_LOG.md` records the remaining estimates as pending candidate confirmation, with Step 4 hours still to add.

No private conversations or personal data are included; the prompts above are quoted from my own messages.

## Review gate log

| Push | Skills run | Findings (freq × severity) | Action |
|---|---|---|---|
| Step 1 (fixtures + loader) | `/code-review`, `ponytail:ponytail-review` | null optional listing fields rejected (4x6); extra keys rejected (3x6); minimal truth file rejected (3x6); fixtures path breaks in non-editable install (2x6); generator KeyError on unknown category (2x4); UTF-8 BOM breaks both readers (2x4); bool/str price coerced (1x4) | First six fixed, with tests in `tests/test_fixtures.py`; last one filed as issue #1 |
| Step 2 (matcher, category, search, API, CLI) | `/code-review`, `ponytail:ponytail-review` | brand-only query 400s (3x4); `18-count` / `1/2 gal` unparseable (3x4); branded query returns other brands (3x3); "hot dog" read as pet (3x3); aisle substring "Veggies"->DAIRY (3x2); demo KeyError on custom listings (2x3); pet aisle ignored (2x3); stdout.reconfigure crash (1x5); search scans all decisions (10x1); long unit names counted as identity (3x2); upstream pool backlog (1x3); intent scans whole catalog (1x2) | Ten fixed, with tests; last two filed as issues #2 and #3 |
| Step 2 independent Codex review | `agent-skills:code-review-and-quality`, `ponytail:ponytail-review` | organic search falls back to conventional spinach at ValueMart (4x5); negative sizes become positive (`-16 oz` matches 16 oz cheddar) (2x5) | Both fixed in shared code (`015bc04`); four regression cases failed before the fixes; 133 tests passed afterward |
| Step 3 (evaluate, benchmark) | `/code-review`, `ponytail:ponytail-review` | benchmark crashes on a corpus without our retailer names (2x3); duplicate truth rows double-counted (1x3); report `command` uses `sys.argv` (2x1); negative `--warmup` (1x2) | First fixed with a test; other three filed as issue #5. Ponytail review: no findings |
| Low-score issues follow-up | candidate's request (overrides the AGENTS.md "file and leave" rule) | #1 bool/string price coerced; #2 timed-out upstream calls back up a shared pool; #3 search intent scans whole catalog; #5 duplicate truth rows, argv in report, negative warmup | Initial regression run: 7 of 9 new cases failed on old code; two were existing behavior/safety checks. Initial search benchmark p50 0.26 ms. Independent review below completed the brand-only index and bounded the worker threads. |
| Step 3 independent Codex review | `agent-skills:code-review-and-quality`, `ponytail:ponytail-review` | evaluation output can overwrite its truth input (2x8) | Fixed (`80aedb5`) with a regression test; 142 tests pass; held-out not rerun |
| Step 4 independent Codex review | `agent-skills:code-review-and-quality`, `ponytail:ponytail-review` | sample JSON drops a real type veto (10x3); architecture, category behavior and CLI claims differ from implementation (10x3); scale proposal described as current behavior and costs overclaimed (10x3); recording reruns held-out and overwrites committed reports (4x3); authorship and evaluation-history wording overstates the record (10x2) | Documentation corrected. All three JSON excerpts checked against live decisions/search; local links, CLI flags, corpus counts, saved truth hash and cost arithmetic verified with assertions. No application code, truth labels or saved reports changed; held-out not rescored. |
| PR #8 independent Codex review | `agent-skills:code-review-and-quality`, `ponytail:ponytail-review` | brand-only intent still scans catalog (10x1); unbounded abandoned worker threads and uncaught thread-start failure (2x5) | Added a prebuilt brand lookup, bounded active workers to 16 with immediate uncertainty at capacity, and caught thread-start failure. All three new tests failed before the fixes; 154 tests pass afterward, lint clean. Search results matched the original full scan for 488 query/retailer combinations. Saved a real post-review benchmark (search p50 0.2675 / p95 0.5185 ms); truth, policy and saved evaluation unchanged, held-out not rescored. |
