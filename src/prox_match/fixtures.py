"""Deterministic fixture generation.

retailer_listings.jsonl = the hand-written tricky listings (fixtures/tricky_listings.jsonl)
followed by "clean" listings generated from the canonical catalog with a fixed seed.
The generator never touches ground_truth.jsonl and never calls the matcher.
"""

import hashlib
import json
import random
import re
from pathlib import Path

from .models import CanonicalProduct, load_jsonl

# Repo checkout (editable install) first; a non-editable install falls back to ./fixtures.
_REPO_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
FIXTURES_DIR = _REPO_FIXTURES if _REPO_FIXTURES.is_dir() else Path.cwd() / "fixtures"
RETAILERS = ("FreshTown", "ValueMart", "MarketSquare")
DEFAULT_SEED = 42

# Each retailer labels aisles its own way: category -> (FreshTown, ValueMart, MarketSquare).
AISLE_LABELS = {
    "PANTRY": ("Pantry", "Grocery", "Pantry Staples"),
    "SEAFOOD": ("Seafood", "Fish & Seafood", "Seafood Counter"),
    "MEAT": ("Fresh Meat", "Meat", "Meat & Poultry"),
    "DAIRY": ("Dairy", "Dairy & Eggs", "Dairy"),
    "PRODUCE": ("Produce", "Fruits & Vegetables", "Fresh Produce"),
    "PET": ("Pet", "Pet Supplies", "Pet Care"),
    "BREAKFAST": ("Breakfast", "Cereal", "Breakfast & Cereal"),
    "FROZEN": ("Frozen", "Frozen Foods", "Freezer"),
    "BEVERAGES": ("Beverages", "Drinks", "Juice & Drinks"),
}

_TRAILING_SIZE = re.compile(r",?\s*\d+(?:\.\d+)?\s*(?:fl oz|oz|lb|gal|ct)\b.*$", re.IGNORECASE)


def _size_variants(value: float, unit: str) -> list[str]:
    """Equivalent ways a retailer might print the catalog size."""
    variants = [f"{value:g} {unit}"]
    if unit == "oz" and value % 8 == 0:
        variants.append(f"{value / 16:g} lb")
    if unit == "fl oz" and value == 128:
        variants.append("1 gal")
    if unit == "ct" and value == 12:
        variants.append("1 dozen")
    return variants


def _name_variants(name: str) -> list[str]:
    base = _TRAILING_SIZE.sub("", name).strip(" ,")
    return [base, base.upper(), base.replace(",", "")]


def generate_clean_listings(catalog: list[CanonicalProduct], seed: int = DEFAULT_SEED) -> list[dict]:
    rng = random.Random(seed)
    listings = []
    for i, product in enumerate(catalog):
        retailer_slots = [i % 3]
        if i % 3 == 0:  # every third product is also stocked by a second retailer
            retailer_slots.append((i + 1) % 3)
        for slot in retailer_slots:
            listings.append({
                "listing_id": f"G{len(listings) + 1:03d}",
                "retailer": RETAILERS[slot],
                "raw_name": rng.choice(_name_variants(product.name)),
                "brand_raw": product.brand or "",
                "size_raw": rng.choice(_size_variants(product.size_value, product.size_unit)),
                "retailer_category": AISLE_LABELS.get(
                    product.category, (product.category.title(),) * 3)[slot],
                "price_cents": rng.randint(99, 2499),
            })
    return listings


def render_listings(fixtures_dir: Path = FIXTURES_DIR, seed: int = DEFAULT_SEED) -> str:
    catalog = load_jsonl(fixtures_dir / "canonical_catalog.jsonl", CanonicalProduct)
    tricky = (fixtures_dir / "tricky_listings.jsonl").read_text(encoding="utf-8-sig").splitlines()
    tricky = [json.dumps(json.loads(line)) for line in tricky if line.strip()]
    clean = [json.dumps(row) for row in generate_clean_listings(catalog, seed)]
    return "\n".join(tricky + clean) + "\n"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_or_check(check: bool, seed: int = DEFAULT_SEED) -> tuple[bool, str]:
    """-> (ok, message). Writes retailer_listings.jsonl unless check=True."""
    target = FIXTURES_DIR / "retailer_listings.jsonl"
    expected = render_listings(seed=seed)
    if check:
        actual = target.read_text(encoding="utf-8") if target.is_file() else ""
        if actual != expected:
            return False, f"MISMATCH: {target} differs from generator output (seed {seed})"
        return True, f"OK {target.name} sha256={sha256(actual)}"
    target.write_text(expected, encoding="utf-8", newline="\n")
    return True, f"wrote {target.name} ({expected.count(chr(10))} listings) sha256={sha256(expected)}"
