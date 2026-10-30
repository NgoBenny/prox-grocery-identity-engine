# Fixtures

All data is synthetic. Retailer names, brands and prices are made up.

| File | Written by | Contents |
|---|---|---|
| `canonical_catalog.jsonl` | hand | 46 canonical products. C101–C112 are copied verbatim from the assessment; C113–C146 are confusable siblings (oat/almond/2% milk, organic vs regular bananas, 12 vs 18 eggs, 8 vs 16 oz cheddar, smooth vs crunchy peanut butter, ...). |
| `brand_aliases.json` | hand | Approved brand allowlist: canonical brand -> normalized aliases. Anything not listed (e.g. `Ocean Cache`) is not an alias. |
| `tricky_listings.jsonl` | hand | 38 deliberately adversarial listings (`T001`–`T038`). |
| `retailer_listings.jsonl` | `scripts/generate_fixtures.py` | The 38 tricky listings followed by 62 generated clean listings (`G001`–`G062`). 100 total across FreshTown, ValueMart, MarketSquare. |
| `ground_truth.jsonl` | hand | Expected `canonical_id` or `null` (= ABSTAIN) for every tricky listing. 28 `dev`, 10 `heldout`. |

## Record formats

- Catalog: `{canonical_id, name, brand|null, category, type, form, organic, size_value, size_unit}`; `size_unit` is `oz` (weight), `fl oz` (volume) or `ct` (count).
- Listing: `{listing_id, retailer, raw_name, brand_raw, size_raw, retailer_category, price_cents}`; `price_cents` is a non-negative integer or absent.
- Truth: `{listing_id, expected_canonical_id|null, expected_category|null, split, case, note, reviewed_by_candidate}`.

## Generation rules (clean listings)

`random.Random(42)`; for catalog product *i*:

1. Stocked at retailer `i % 3`; every third product (`i % 3 == 0`) is also stocked at retailer `(i + 1) % 3`.
2. `raw_name`: the catalog name with its trailing size removed, then one of: as-is, UPPERCASE, commas removed.
3. `size_raw`: one equivalent spelling of the catalog size: `N oz`, `N/16 lb` (weights divisible by 8 oz), `1 gal` (128 fl oz), `1 dozen` (12 ct).
4. `retailer_category`: that retailer's aisle label for the catalog category.
5. `price_cents`: uniform 99–2499.

Regenerate with `uv run python scripts/generate_fixtures.py`; verify with `--check` (also a pytest test). The generator never reads or writes `ground_truth.jsonl` and never calls the matcher.

## Ground-truth policy

- Labels were written before any matching code existed (see git history) and are never edited to make a metric pass.
- No organic claim in the listing = non-organic.
- C107 and C108 are the same product (whole milk, 128 fl oz) under two IDs, so whole-milk gallon listings are labeled ABSTAIN.
- Multipacks (`2 x 8 oz`) are not the same item as a single package of the same total size.
