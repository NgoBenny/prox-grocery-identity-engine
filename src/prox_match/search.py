"""Ranked listing search over the engine's precomputed match decisions.

1. Parse the query like a listing (same tokens, types, form and pet cues).
2. Intent = canonical products that fully cover the query words and agree on type/pet/form.
   No intent -> [] with reason "no_safe_match" (no filler results).
3. Candidate listings come from an inverted token index. A listing qualifies only if its
   category is one of the intent categories and its product type is one of the intent types,
   which is what keeps broth (PANTRY), dog food (PET) and seasoning (UNKNOWN) out of
   "chicken breast".
4. Tier 1: same product (matched to an intent canonical, or an abstained listing whose text
   covers the whole query). Tier 0 fallback (only when tier 1 is empty): same type and
   category, covering at least half the query words.
5. Rank by tier + 0.5 query_coverage + 0.3 listing_coverage (share of the product's identity
   words the query names) + 0.2 match_confidence; ties by listing_id. Deduplicate by (retailer, canonical_id); abstained listings are never merged.
"""

from collections import defaultdict

from .models import RetailerListing
from .normalize import CUE_FORMS, token_match

FALLBACK_MIN_COVERAGE = 0.5


def _coverage(of, by) -> float:
    """Share of `of` found in `by`; nothing to find (a brand-only query) counts as covered."""
    return sum(any(token_match(a, b) for b in by) for a in of) / len(of) if of else 1.0


class SearchIndex:
    def __init__(self, engine):
        self.engine = engine
        index = engine.index
        self.features = {lid: index.listing_features(row) for lid, row in engine.listings.items()}
        self.words: dict[str, set[str]] = {}
        self.types: dict[str, frozenset[str]] = {}
        self.postings: dict[str, set[str]] = defaultdict(set)
        for lid, f in self.features.items():
            cid = engine.decisions[lid]["canonical_id"]
            words = set(f.tokens) | (set(index.features[cid].tokens) if cid else set())
            self.words[lid] = words
            self.types[lid] = index.features[cid].types if cid else f.types
            for w in words | {w for ph in self.types[lid] for w in ph.split()}:
                self.postings[w].add(lid)
        self.retailers = {row.retailer.casefold(): row.retailer for row in engine.listings.values()}
        self.by_canonical: dict[str, set[str]] = defaultdict(set)
        for lid, d in engine.decisions.items():
            if d["canonical_id"]:
                self.by_canonical[d["canonical_id"]].add(lid)

    def _intent(self, qf) -> list[str]:
        index = self.engine.index
        hits = []
        for cid, cf in index.features.items():
            product = index.products[cid]
            words = set(cf.tokens) | {w for ph in cf.types for w in ph.split()}
            if _coverage(qf.tokens, words) < 1.0:
                continue
            if qf.brand_status == "approved" and cf.brand != qf.brand:
                continue
            if qf.types and not (cf.types & qf.types):
                continue
            if qf.pet != cf.pet:
                continue
            if qf.forms is not None and product.form in CUE_FORMS and product.form not in qf.forms:
                continue
            if qf.organic_explicit and qf.organic != cf.organic:
                continue
            hits.append(cid)
        return hits

    def search(self, q: str, retailer: str | None = None, limit: int = 10) -> dict:
        engine, index = self.engine, self.engine.index
        if retailer is not None and retailer.casefold() not in self.retailers:
            raise ValueError(f"unknown retailer {retailer!r}; known: {sorted(self.retailers.values())}")
        qf = index.listing_features(RetailerListing(listing_id="query", retailer="-", raw_name=q))
        if not qf.tokens and qf.brand_status != "approved":
            raise ValueError("query has no searchable words")
        intent = self._intent(qf)
        out = {"query": q, "retailer": retailer, "intent": {
            "canonical_ids": intent,
            "categories": sorted({index.products[c].category for c in intent}),
            "types": sorted({t for c in intent for t in index.features[c].types})},
            "fallback": False, "reason": None, "results": [], "deduplicated": []}
        if not intent:
            out["reason"] = "no_safe_match"
            return out

        categories = set(out["intent"]["categories"])
        types = set(out["intent"]["types"])
        candidates = set().union(*(self.by_canonical.get(cid, ()) for cid in intent))
        for qw in qf.tokens:
            for w, lids in self.postings.items():
                if token_match(qw, w):
                    candidates |= lids

        tiers: dict[int, list[dict]] = {0: [], 1: []}
        for lid in candidates:
            row, d, f = engine.listings[lid], engine.decisions[lid], self.features[lid]
            if retailer and row.retailer.casefold() != retailer.casefold():
                continue
            if d["assigned_category"] not in categories or not (self.types[lid] & types):
                continue
            if f.pet != qf.pet:
                continue
            brand = index.products[d["canonical_id"]].brand if d["canonical_id"] else f.brand
            if qf.brand_status == "approved" and brand != qf.brand:
                continue
            q_cov = _coverage(qf.tokens, self.words[lid])
            # how much of the product the query names: catalog words when matched, so
            # "chicken breast" ranks plain breast above breaded breast nuggets
            identity = index.features[d["canonical_id"]].tokens if d["canonical_id"] else f.tokens
            l_cov = _coverage(identity, qf.tokens)
            same_product = d["canonical_id"] in intent or (d["canonical_id"] is None and q_cov == 1)
            if not same_product and q_cov < FALLBACK_MIN_COVERAGE:
                continue
            tier = 1 if same_product else 0
            score = tier + 0.5 * q_cov + 0.3 * l_cov + 0.2 * d["confidence"]
            tiers[tier].append({
                "listing_id": lid, "retailer": row.retailer, "raw_name": row.raw_name,
                "canonical_id": d["canonical_id"], "canonical_name": d["canonical_name"],
                "assigned_category": d["assigned_category"], "match_stage": d["match_stage"],
                "price_cents": row.price_cents, "unit_price": d["unit_price"],
                "score": round(score, 4),
                "components": {"tier": tier, "query_coverage": round(q_cov, 4),
                               "listing_coverage": round(l_cov, 4),
                               "match_confidence": d["confidence"]},
                "collapsed_duplicates": [],
            })

        results = tiers[1] or tiers[0]
        out["fallback"] = not tiers[1] and bool(tiers[0])
        results.sort(key=lambda r: (-r["score"], r["listing_id"]))
        kept: dict[tuple, dict] = {}
        for r in results:
            key = (r["retailer"], r["canonical_id"] or r["listing_id"])
            if key in kept:
                kept[key]["collapsed_duplicates"].append(r["listing_id"])
                out["deduplicated"].append(r["listing_id"])
            else:
                kept[key] = r
        out["results"] = list(kept.values())[:limit]
        if not out["results"]:
            out["reason"] = "no_safe_match"
        return out
