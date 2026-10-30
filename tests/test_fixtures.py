"""Fixture integrity: counts, the PDF's prescribed starters, truth references and determinism."""

import pytest

from prox_match.fixtures import FIXTURES_DIR, RETAILERS, render_listings
from prox_match.models import (
    CanonicalProduct,
    FixtureError,
    RetailerListing,
    TruthLabel,
    load_jsonl,
)

CATALOG = load_jsonl(FIXTURES_DIR / "canonical_catalog.jsonl", CanonicalProduct)
LISTINGS = load_jsonl(FIXTURES_DIR / "retailer_listings.jsonl", RetailerListing)
TRUTH = load_jsonl(FIXTURES_DIR / "ground_truth.jsonl", TruthLabel)
BY_ID = {c.canonical_id: c for c in CATALOG}

# Copied by hand from the assessment's "Required starter examples" table.
# (id, name, category, type, form, size_value, size_unit)
PRESCRIBED = [
    ("C101", "Ocean Catch Solid White Tuna, canned 5 oz", "PANTRY", "tuna", "canned", 5, "oz"),
    ("C102", "Atlantic Fresh Tuna Steak, raw 1 lb", "SEAFOOD", "tuna", "fresh", 16, "oz"),
    ("C103", "Farmhouse Chicken Breast, boneless 1 lb", "MEAT", "chicken", "fresh", 16, "oz"),
    ("C104", "Heritage Chicken Broth, 32 fl oz", "PANTRY", "chicken", "shelf-stable broth", 32,
     "fl oz"),
    ("C105", "Fresh Salmon Fillet, 1 lb", "SEAFOOD", "salmon", "fresh", 16, "oz"),
    ("C106", "Tinned Pink Salmon, 14.75 oz", "PANTRY", "salmon", "canned", 14.75, "oz"),
    ("C107", "Whole Milk, 1 gal", "DAIRY", "milk", "liquid", 128, "fl oz"),
    ("C108", "Whole Milk, 128 fl oz", "DAIRY", "milk", "liquid", 128, "fl oz"),
    ("C109", "Organic Baby Spinach, 5 oz", "PRODUCE", "spinach", "fresh", 5, "oz"),
    ("C110", "Baby Spinach, 5 oz", "PRODUCE", "spinach", "fresh", 5, "oz"),
    ("C111", "Chicken Flavored Dog Food, 12 lb", "PET", "dog food", "dry", 192, "oz"),
    ("C112", "Honey Nut Oat Cereal, family size 18.8 oz", "BREAKFAST", "cereal", "dry", 18.8,
     "oz"),
]


def test_minimum_counts():
    assert len(BY_ID) == len(CATALOG) >= 40
    assert len({row.listing_id for row in LISTINGS}) == len(LISTINGS) >= 80
    assert {row.retailer for row in LISTINGS} == set(RETAILERS)
    assert len(TRUTH) >= 25


@pytest.mark.parametrize("cid,name,category,type_,form,size_value,size_unit", PRESCRIBED)
def test_prescribed_starters_are_verbatim(cid, name, category, type_, form, size_value, size_unit):
    c = BY_ID[cid]
    assert (c.name, c.category, c.type, c.form, c.size_value, c.size_unit) == (
        name, category, type_, form, size_value, size_unit)


def test_organic_flags_on_prescribed_spinach():
    assert BY_ID["C109"].organic and not BY_ID["C110"].organic


def test_truth_references_exist_and_agree_with_catalog():
    listing_ids = {row.listing_id for row in LISTINGS}
    assert len({t.listing_id for t in TRUTH}) == len(TRUTH)
    for t in TRUTH:
        assert t.listing_id in listing_ids, t.listing_id
        if t.expected_canonical_id is not None:
            assert t.expected_canonical_id in BY_ID, t.listing_id
            assert t.expected_category == BY_ID[t.expected_canonical_id].category, t.listing_id


def test_truth_has_abstains_and_heldout_split():
    assert sum(t.expected_canonical_id is None for t in TRUTH) >= 5
    assert sum(t.split == "heldout" for t in TRUTH) >= 10


def test_committed_listings_match_generator():
    committed = (FIXTURES_DIR / "retailer_listings.jsonl").read_text(encoding="utf-8")
    assert render_listings() == committed
    assert render_listings() == render_listings()  # deterministic


def test_loader_reports_line_number_on_bad_record(tmp_path):
    bad = tmp_path / "listings.jsonl"
    bad.write_text(
        '{"listing_id": "X1", "retailer": "R", "raw_name": "Milk", "price_cents": 100}\n'
        '{"listing_id": "X2", "retailer": "R", "raw_name": "Milk", "price_cents": "abc"}\n',
        encoding="utf-8",
    )
    with pytest.raises(FixtureError, match=r"listings\.jsonl:2"):
        load_jsonl(bad, RetailerListing)


def test_negative_price_rejected():
    with pytest.raises(ValueError):
        RetailerListing(listing_id="X", retailer="R", raw_name="Milk", price_cents=-1)
