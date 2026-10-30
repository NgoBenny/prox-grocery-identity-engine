# Demo walkthrough (about 3 minutes)

Recording: _link to be added_

Record the terminal (and one browser tab for the API). Every number on screen comes from a live run; nothing is pre-recorded. Commands are from the repo root.

## 0:00–0:20 · Setup

```bash
uv sync --locked
```

Say: offline Python engine; synthetic data; no API keys, no LLM, no network. Show the repo tree: `src/`, `fixtures/`, `tests/`, `scripts/`.

## 0:20–1:15 · Core flow

```bash
uv run prox-match demo
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
uv run uvicorn prox_match.api:app --port 8000
```

Open `http://127.0.0.1:8000/search?q=chicken%20breast&retailer=FreshTown`. Show that only MEAT and FROZEN chicken come back, plain breast ranks first, and the `components` show why. Broth, dog food and the seasoning rub are absent. (Optional: `/docs`.)

## 2:15–2:50 · Real tests and evaluation

```bash
uv run pytest -q
uv run prox-match evaluate
```

Show the passing test count, then the confusion counts per split: dev 28/28 and held-out 10/10, with no false matches, plus the one category miss (T004, which correctly abstains but gets UNKNOWN instead of PANTRY). Say: the policy was committed before held-out was scored once, and 38 self-written labels can't support statistical claims.

## 2:50–3:15 · Performance and scale

```bash
uv run prox-match benchmark --searches 100
```

Read the measured p50/p95 from the screen. Close with SCALE_AND_COST.md: incremental matching by content hash, sharding by category, and the real bottleneck at 10M listings is the human review queue, not compute.
