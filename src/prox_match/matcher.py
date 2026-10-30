"""Two-stage matching: exact signature, then retrieval + rerank behind hard vetoes.

Policy (provisional, set before looking at evaluation numbers):
  - accept only if the best non-vetoed candidate scores >= ACCEPT_THRESHOLD and beats the
    runner-up by >= MIN_MARGIN; otherwise ABSTAIN with the top 3 candidates and reasons.
  - no valid listing size -> ABSTAIN (size is part of identity).
  - ties never get broken by ID; candidate ordering by ID is for display only.
"""

from dataclasses import dataclass, field

from .index import CatalogIndex, Features
from .models import RetailerListing
from .normalize import CUE_FORMS, clean_text, token_match, unit_price

ACCEPT_THRESHOLD = 0.70  # was 0.75: rejected "Farmhouse Chicken Breast 1 lb" for lacking "boneless"
MIN_MARGIN = 0.08
HIGH_CONFIDENCE = 0.90  # auto-approve without review only at or above this
INFERRED_ORGANIC_FACTOR = 0.95  # listing silent on organic: trust a bit less
MISSING_BRAND_FACTOR = 0.85  # listing has no brand, canonical is branded
UNRECOGNIZED_BRAND_FACTOR = 0.90  # unknown brand vs an unbranded canonical


@dataclass
class Candidate:
    canonical_id: str
    name: str
    score: float
    components: dict
    vetoes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"canonical_id": self.canonical_id, "canonical_name": self.name,
                "score": round(self.score, 4), "components": self.components,
                "vetoes": self.vetoes, "notes": self.notes}


def _coverage(of: tuple[str, ...], by: tuple[str, ...]) -> float:
    if not of:
        return 0.0
    return sum(any(token_match(a, b) for b in by) for a in of) / len(of)


def score_candidate(index: CatalogIndex, lf: Features, cid: str) -> Candidate:
    product, cf = index.products[cid], index.features[cid]
    vetoes, notes = [], []

    if lf.brand_status == "approved" and lf.brand != cf.brand:
        vetoes.append("BRAND_MISMATCH")
    elif lf.brand_status == "unknown" and cf.brand:
        vetoes.append("BRAND_UNAPPROVED")
    canonical_type = next(iter(cf.types))
    if lf.types and canonical_type not in lf.types:
        vetoes.append("TYPE_MISMATCH")
    if lf.pet != cf.pet:
        vetoes.append("PET_HUMAN_CONFLICT")
    if lf.forms is not None and product.form in CUE_FORMS and product.form not in lf.forms:
        vetoes.append("FORM_MISMATCH")
    if lf.organic != cf.organic:
        vetoes.append("ORGANIC_CONFLICT")
    if lf.size is not None:
        if lf.size.dimension != cf.size.dimension:
            dims = {lf.size.dimension, cf.size.dimension}
            vetoes.append("MASS_VOLUME_CONFLICT" if dims == {"mass", "volume"} else "SIZE_MISMATCH")
        elif lf.size.pack_count != cf.size.pack_count:
            vetoes.append("PACKAGING_DIFFERENCE")
        elif not lf.size.equals(cf.size):
            vetoes.append("SIZE_MISMATCH")

    brand_factor = 1.0
    if lf.brand_status == "missing" and cf.brand:
        brand_factor = MISSING_BRAND_FACTOR
        notes.append("BRAND_MISSING")
    elif lf.brand_status == "unknown" and not cf.brand:
        brand_factor = UNRECOGNIZED_BRAND_FACTOR
        notes.append("BRAND_UNRECOGNIZED")
    organic_factor = 1.0 if lf.organic_explicit else INFERRED_ORGANIC_FACTOR

    canonical_cov = _coverage(cf.tokens, lf.tokens)  # catalog words the listing has
    listing_cov = _coverage(lf.tokens, cf.tokens)  # listing words the catalog explains
    lexical = 0.75 * canonical_cov + 0.25 * listing_cov
    score = lexical * brand_factor * organic_factor
    components = {"canonical_coverage": round(canonical_cov, 4),
                  "listing_coverage": round(listing_cov, 4), "lexical": round(lexical, 4),
                  "brand_factor": brand_factor, "organic_factor": organic_factor}
    return Candidate(cid, product.name, score, components, vetoes, notes)


def match_listing(index: CatalogIndex, listing: RetailerListing) -> dict:
    """Identity decision for one listing. Category is assigned afterwards by category.py."""
    lf = index.listing_features(listing)
    ids = index.candidates(lf) | set(index.lookup_signature(lf))
    scored = sorted((score_candidate(index, lf, cid) for cid in ids),
                    key=lambda c: (bool(c.vetoes), -c.score, c.canonical_id))
    passing = [c for c in scored if not c.vetoes]
    reasons: list[str] = []
    winner, stage = None, "abstain"

    passing_ids = {c.canonical_id for c in passing}
    exact = [cid for cid in index.lookup_signature(lf) if cid in passing_ids]
    top = passing[0] if passing else None
    runner = passing[1] if len(passing) > 1 else None
    if lf.size_problem:
        reasons.append(lf.size_problem)
    elif len(exact) > 1 or (top and runner and top.score - runner.score < MIN_MARGIN
                            and runner.canonical_id in index.cluster_of.get(top.canonical_id, ())):
        reasons.append("CATALOG_DUPLICATE")
    elif len(exact) == 1:
        winner, stage = next(c for c in passing if c.canonical_id == exact[0]), "exact_signature"
        reasons.append("EXACT_SIGNATURE")
    elif top is None:
        reasons.append("NO_SAFE_CANDIDATE")
    elif top.score < ACCEPT_THRESHOLD:
        reasons.append("LOW_CONFIDENCE")
    elif runner and top.score - runner.score < MIN_MARGIN:
        reasons.append("SMALL_SCORE_MARGIN")
    else:
        winner, stage = top, "rerank"

    if winner:
        reasons += winner.notes
        if lf.brand_status == "approved" and clean_text(listing.brand_raw) not in (
                "", clean_text(lf.brand or "")):
            reasons.append("BRAND_ALIAS")
    if not lf.organic_explicit:
        reasons.append("ORGANIC_INFERRED")

    product = index.products[winner.canonical_id] if winner else None
    return {
        "listing_id": listing.listing_id,
        "canonical_id": product.canonical_id if product else None,
        "canonical_name": product.name if product else None,
        "assigned_category": None,  # filled by category.assign_category
        "normalized_size": lf.size.as_dict() if lf.size else None,
        "match_stage": stage,
        "confidence": round(winner.score, 4) if winner else 0.0,
        "reason_codes": reasons,
        "reviewer_flag": winner is None or winner.score < HIGH_CONFIDENCE,
        "top_candidates": [c.as_dict() for c in scored[:3]],
        "unit_price": unit_price(listing.price_cents, lf.size),
    }
