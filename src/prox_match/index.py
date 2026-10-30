"""Identity features, exact signatures and the inverted token index over the canonical catalog."""

from collections import defaultdict
from dataclasses import dataclass

from .models import CanonicalProduct, RetailerListing
from .normalize import (
    FORM_CUES,
    FORM_ONLY_WORDS,
    STOPWORDS,
    BrandBook,
    Size,
    aisle_category,
    contains_phrase,
    mentions_pet,
    parse_organic,
    parse_size,
    strip_trailing_size,
    token_match,
    tokens,
)


@dataclass(frozen=True)
class Features:
    """Identity evidence extracted from a canonical record or a retailer listing."""

    brand: str | None
    brand_status: str  # approved | unknown | missing
    tokens: tuple[str, ...]  # identity words (brand, size, organic and pure form words removed)
    types: frozenset[str]  # catalog type phrases named in the text
    forms: frozenset[str] | None  # forms the text allows; None = text says nothing about form
    pet: bool
    organic: bool
    organic_explicit: bool
    size: Size | None
    size_problem: str | None

    @property
    def signature(self) -> tuple | None:
        if self.size is None:
            return None
        return (self.brand, self.organic, self.size.dimension, round(self.size.total_value, 2),
                self.size.pack_count, frozenset(self.tokens))


def _drop_phrase(toks: list[str], phrase: list[str]) -> list[str]:
    i = contains_phrase(toks, phrase) if phrase else -1
    return toks if i < 0 else toks[:i] + toks[i + len(phrase):]


def _identity_tokens(toks: list[str]) -> tuple[str, ...]:
    keep = []
    for t in toks:
        if t in STOPWORDS or t in FORM_ONLY_WORDS or t in {"organic", "non", "not"}:
            continue
        if len(t) < 2 or (t[0].isdigit() and "%" not in t and "/" not in t):
            continue  # sizes and stray numbers; keeps "2%" and "80/20"
        keep.append(t)
    return tuple(dict.fromkeys(keep))


def _allowed_forms(toks: list[str]) -> frozenset[str] | None:
    sets = [FORM_CUES[t] for t in toks if t in FORM_CUES]
    if not sets:
        return None
    allowed = frozenset.intersection(*map(frozenset, sets))
    return allowed or None  # contradictory cues ("fresh frozen") constrain nothing


class CatalogIndex:
    def __init__(self, catalog: list[CanonicalProduct], brands: BrandBook):
        self.brands = brands
        self.products = {p.canonical_id: p for p in catalog}
        if len(self.products) != len(catalog):
            raise ValueError("duplicate canonical_id in catalog")
        self.type_phrases = sorted({tuple(tokens(p.type)) for p in catalog}, key=len, reverse=True)
        self.features = {p.canonical_id: self._canonical_features(p) for p in catalog}

        self.signatures: dict[tuple, list[str]] = defaultdict(list)
        self.postings: dict[str, set[str]] = defaultdict(set)
        for cid, f in self.features.items():
            self.signatures[f.signature].append(cid)
            for t in f.tokens + tuple(w for ph in f.types for w in ph.split()):
                self.postings[t].add(cid)
        # Distinct IDs with identical identity evidence (C107/C108): can never be told apart.
        self.duplicate_clusters = [sorted(ids) for ids in self.signatures.values() if len(ids) > 1]
        self.cluster_of = {cid: frozenset(ids) for ids in self.duplicate_clusters for cid in ids}

    def detect_types(self, toks: list[str]) -> frozenset[str]:
        """Catalog type phrases present in the text, dropping ones inside a longer match
        ("oat milk" hides "milk", "peanut butter" hides "butter")."""
        found = [ph for ph in self.type_phrases if contains_phrase(toks, list(ph)) >= 0]
        kept = [ph for ph in found
                if not any(o != ph and contains_phrase(list(o), list(ph)) >= 0 for o in found)]
        return frozenset(" ".join(ph) for ph in kept)

    def _canonical_features(self, p: CanonicalProduct) -> Features:
        toks = _drop_phrase(tokens(strip_trailing_size(p.name)), tokens(p.brand or ""))
        size, problem = parse_size(f"{p.size_value:g} {p.size_unit}")
        if problem:
            raise ValueError(f"{p.canonical_id}: unusable catalog size ({problem})")
        return Features(
            brand=p.brand, brand_status="approved" if p.brand else "missing",
            tokens=_identity_tokens(toks),
            types=frozenset({" ".join(tokens(p.type))}), forms=frozenset({p.form}),
            pet=p.category.upper() == "PET", organic=p.organic, organic_explicit=True,
            size=size, size_problem=None,
        )

    def listing_features(self, listing: RetailerListing) -> Features:
        name_toks = tokens(listing.raw_name)
        brand, status, brand_toks = self.brands.resolve(listing.brand_raw, name_toks)
        toks = _drop_phrase(name_toks, brand_toks)  # "Atlantic Fresh" must not read as "fresh"
        organic, explicit = parse_organic(toks)
        size, problem = parse_size(listing.size_raw)
        return Features(
            brand=brand, brand_status=status, tokens=_identity_tokens(toks),
            types=self.detect_types(toks), forms=_allowed_forms(toks),
            # the pet aisle counts as pet evidence: a mis-shelved human item only abstains
            pet=mentions_pet(toks) or aisle_category(listing.retailer_category) == "PET",
            organic=organic, organic_explicit=explicit,
            size=size, size_problem=problem,
        )

    def candidates(self, f: Features) -> set[str]:
        """Union of postings for each listing word, expanded to fuzzy vocabulary matches.
        shortcut: linear scan of the vocabulary, fine for thousands of words; a trigram or
        RapidFuzz process.extract index is the upgrade for millions."""
        found: set[str] = set()
        words = set(f.tokens) | {w for ph in f.types for w in ph.split()}
        for word in words:
            for vocab_word, ids in self.postings.items():
                if token_match(word, vocab_word):
                    found |= ids
        return found

    def lookup_signature(self, f: Features) -> list[str]:
        return list(self.signatures.get(f.signature, [])) if f.signature else []
