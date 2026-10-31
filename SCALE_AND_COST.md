# Scale and cost: 10 million listings, weekly refresh

**Measured** numbers come from `prox-match benchmark` on a laptop (single process, 46 IDs, 100 listings). Everything else is an **assumption** and is labeled as one. No cloud rate below is a provider quote.

## Pipeline

```
weekly retailer feeds
  -> 1. ingest: immutable raw snapshot per retailer, schema validation, content hash per listing
  -> 2. diff: hash unchanged since last week? reuse last decision (canonical lookup reuse)
  -> 3. match changed/new listings only: normalize -> exact signature -> retrieve -> veto -> rerank
  -> 4. route: >= 0.90 and no flags -> auto-publish; flagged / ABSTAIN -> review queue
  -> 5. publish versioned decision table (listing_hash, policy_version, catalog_version) + search index
  -> 6. monitor, shadow-compare new policy, roll back by pointer
```

- **Incremental matching.** The decision key is `(listing content hash, catalog version, policy version)`. Assume 10–20% of listings change in a week, so 1–2M matches instead of 10M. A catalog or policy change re-matches only the affected types or categories.
- **Partitioning (proposed).** Shard the catalog postings by category, with per-retailer concurrency limits and queue backpressure. Matching currently retrieves across the whole catalog; its type/form/pet vetoes and search's category gate are not category-sharded retrieval. A future router must search every plausible shard when category is uncertain, rather than trusting a noisy retailer aisle. For example, chicken words can refer to MEAT, PANTRY, FROZEN or PET products.
- **Retrieval at scale.** The in-memory postings dict becomes a per-shard inverted index (a search engine or Postgres trigram/GIN). The current linear fuzzy vocabulary scan in `CatalogIndex.candidates` is the first thing to replace.

## Capacity arithmetic

| Quantity | Value | Basis |
|---|---|---|
| Match latency per listing | 0.31 ms p50 | **measured** (46-ID catalog) |
| Assumed latency at full catalog size (~100k IDs, indexed retrieval) | 3 ms | **assumption**: roughly 10× the small-corpus match latency; unvalidated |
| Full 10M re-match | 10M × 3 ms = 8.3 CPU-hours | arithmetic |
| Weekly incremental (2M changed) | 1.7 CPU-hours; ~6 min on 16 cores | arithmetic; ideal parallelism, requires multiple processes for this Python workload |
| Average ingest rate | 10M / 7 days ≈ 16.5 listings/s; plan for 10× peak on feed day | arithmetic |
| Raw snapshot | 10M × 0.5 KB ≈ 5 GB / week | **assumption**: 0.5 KB per listing |
| Search p50 / p95 | 0.27 / 0.52 ms | **measured**, 100 listings; not a 10M claim |

## Cost model

```
weekly cost = matched listings × CPU-s per listing × $ per CPU-s
            + stored GB × $ per GB-month / 4.3
            + review cases × $ per review case
            + LLM fallback calls × capped $ per call        (0 in this MVP)
```

With **assumed** rates of $0.04 per CPU-hour, $0.02 per GB-month, and $0.15 per review case (about 30 s of a $18/h reviewer): compute ≈ 1.7 h × $0.04 ≈ **$0.07**, storage (one year of 5 GB snapshots, 260 GB) ≈ **$1.20**, review at an assumed 3% of 2M changed listings = 60k cases ≈ **$9,000/week**.

These are variable-cost estimates, not a deployment bill: they exclude feed I/O, orchestration, search serving, index storage, minimum instance charges, replication and operational overhead. The 3 ms full-catalog latency and parallel speedup need a representative load test.

**Under these assumptions, human review dominates the modeled cost.** Every percentage point of changed listings sent to review costs about $3,000 a week. On our corpus, 3 of 62 clean listings abstain (all one catalog duplicate), 16 of 100 overall abstain, and 22 of 100 carry a review flag. The flagged count includes low-confidence matches as well as abstentions; deliberate traps make this corpus unsuitable for estimating a production queue rate.

## Review queue priority

Order cases by `listing traffic × price impact × risk`. Risk is highest for candidates that cross a category, then for duplicate clusters (one catalog merge clears every listing of that product), then for low-margin ties. Merging catalog duplicates and adding approved aliases from review outcomes removes whole classes of future cases.

## Error and cost budgets

- **Precision first.** Target ≥ 99.5% precision on auto-published matches, measured weekly on a random audit sample of 500 auto-approved decisions. If the audit fails, auto-publish pauses for the affected shard.
- **Review budget.** Cap the weekly queue at a dollar amount. Overflow stays unmatched (safe) rather than lowering the threshold.
- **LLM fallback (if ever added).** Only for ABSTAIN cases, behind the existing worker interface, with a per-item token cap, cached by listing hash, never allowed to override a veto, and **its self-reported confidence is never used as ground truth**.

## Drift monitoring, calibration and rollback

- **Per retailer and category, weekly:** abstention rate, review override rate, veto mix, unknown-brand rate and size-parse failures. A jump in `SIZE_UNPARSEABLE` or `BRAND_UNAPPROVED` for one retailer usually means its feed format changed.
- **Calibration.** `confidence` today is a ranking score. Fit an isotonic map from score to observed precision on an independently labeled, stratified set, refreshed from review outcomes. Thresholds then come from a target precision, not judgment.
- **Rollback.** Decisions are versioned by policy and catalog. A new policy runs in shadow on the same week's diff, and its disagreements with production are sampled for review before promotion. Rolling back moves the "current" pointer to the previous decision table, with no re-matching needed.
