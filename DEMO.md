# Demo walkthrough (about 3 minutes)

Recording: _link to be added_

Record the terminal (and one browser tab for the API). Run the commands live; show the held-out numbers from the committed evaluation report and identify them as saved results. Commands are from the repo root.

## 0:00–0:20 · Setup

```bash
uv sync --locked
```

Say: offline Python engine; synthetic data; no API keys or LLM; no external network calls during matching. Dependency installation may need network access. Show the repo tree: `src/`, `fixtures/`, `tests/`, `scripts/`.

## 0:20–1:15 · Core flow

```bash
uv run prox-match demo --output outputs/recording_demo.json
```

Point at four sections of the output:

- **Positive match (T007):** `Farm House` is an approved alias of Farmhouse, `1 LB` = 16 oz, and it hits the exact signature for C103.
- **Corrected category (T008):** the retailer filed chicken broth under "Meat & Poultry". The catalog says PANTRY, and the reason code `RETAILER_CATEGORY_OVERRIDDEN` shows it.
- **Veto (T003):** raw tuna steak vs canned tuna C101 shows `FORM_MISMATCH`, so a high name score can't override it.
- **Upstream AI (T006):** uncertain, timeout and confident conflict. MEAT is kept every time, and the conflict sets `reviewer_flag`.

## 1:15–1:50 · One difficult edge case: ABSTAIN on duplicate IDs

```bash
uv run prox-match match --listing-id T014
```

Say: C107 "Whole Milk, 1 gal" and C108 "Whole Milk, 128 fl oz" are the same product under two IDs, since 1 gal = 128 fl oz. The engine returns `canonical_id: null`, `CATALOG_DUPLICATE`, both IDs as tied top candidates, category DAIRY, and `reviewer_flag: true`. It never picks one by ID order. The real fix is a catalog merge in review.

## 1:50–2:15 · Search over HTTP

```bash
uv run uvicorn prox_match.api:app --port 8001
```

Keep the server running in a second terminal so the recording terminal is free for later commands.

Open `http://127.0.0.1:8001/search?q=chicken%20breast&retailer=FreshTown`. Show that only MEAT and FROZEN chicken come back, plain breast ranks first, and the `components` show why. Broth, dog food and the seasoning rub are absent. (Optional: `/docs`.)

## 2:15–2:50 · Real tests and evaluation

```bash
uv run pytest -q
uv run prox-match evaluate --split dev --output outputs/recording_dev_evaluation.json
```

Show the passing test count and live dev counts: 28/28, with no false matches and one category miss (T004, which correctly abstains but gets UNKNOWN instead of PANTRY). Open the committed `outputs/evaluation_report.json` to show the saved held-out result: 10/10, including six correct abstentions. Say: the policy was committed before the first held-out evaluation and was not tuned on that result. The same AI-assisted workflow produced these 38 labels and the rules, so this is a consistency check, not evidence of general accuracy. The recording does not rescore held-out labels or overwrite the committed reports.

## 2:50–3:15 · Performance and scale

```bash
uv run prox-match benchmark --searches 100 --output outputs/recording_benchmark.json
```

Read the measured p50/p95 from the screen. Close with SCALE_AND_COST.md: proposed incremental matching by content hash and category shards. Under the document's assumptions, human review dominates the modeled cost; full-scale throughput has not been measured.
