"""Regression assertions for every required adversarial case.

Inputs are written here by hand (new phrasings, not the truth-file rows), so these tests pin
behavior independently of the evaluation set.
"""

import pytest

# (case, raw_name, size_raw, brand_raw, expected canonical_id or None, reason or veto expected)
CASES = [
    ("canned tuna is not tuna steak", "Ocean Catch Solid White Tuna in Water, Canned", "5 oz",
     "Ocean Catch", "C101", None),
    ("tuna steak is not canned tuna", "Atlantic Fresh Raw Tuna Steak", "16 oz", "Atlantic Fresh",
     "C102", None),
    ("tinned salmon is not a fresh fillet", "Pink Salmon, Tinned", "14.75 oz", "", "C106", None),
    ("fresh fillet is not tinned salmon", "Salmon Fillet Fresh", "1 lb", "", "C105", None),
    ("broth is not chicken meat", "Heritage Chicken Broth Carton", "32 fl oz", "Heritage", "C104",
     None),
    ("dog food is not human chicken", "Dry Dog Food Chicken Flavored", "12 lb", "", "C111", None),
    ("multipack is not the single 16 oz block", "Valley Creamery Sharp Cheddar 2pk", "2 x 8 oz",
     "Valley Creamery", None, "PACKAGING_DIFFERENCE"),
    ("1 gal of 2% milk = 128 fl oz", "2% Reduced Fat Milk", "128 fl oz", "", "C115", None),
    ("gal vs 128 fl oz duplicate IDs abstain", "Whole Milk Gallon", "1 gal", "", None,
     "CATALOG_DUPLICATE"),
    ("organic listing never gets the non-organic ID", "Organic Baby Spinach Clamshell", "5 oz", "",
     "C109", None),
    ("silent organic reads as non-organic", "Baby Spinach Clamshell", "5 oz", "", "C110",
     "ORGANIC_INFERRED"),
    ("explicit non-organic", "Non-Organic Baby Spinach", "5 oz", "", "C110", None),
    ("milk is not oat milk", "Oat Milk Original", "64 fl oz", "", "C113", None),
    ("oat milk never matches dairy milk", "Oat Milk", "1 gal", "", None, "NO_SAFE_CANDIDATE"),
    ("approved alias", "Farm House Boneless Chicken Breast", "1 lb", "Farm House", "C103",
     "BRAND_ALIAS"),
    ("false brand alias", "Farmstead Boneless Chicken Breast", "1 lb", "Farmstead", None,
     "BRAND_UNAPPROVED"),
    ("identical title, 12 oz", "Honey Nut Oat Cereal", "12 oz", "", "C142", None),
    ("identical title, 18.8 oz", "Honey Nut Oat Cereal", "18.8 oz", "", "C112", None),
    ("missing size abstains", "Sunvine Diced Tomatoes", "", "Sunvine", None, "SIZE_UNKNOWN"),
    ("zero size abstains", "Sunvine Diced Tomatoes", "0 oz", "Sunvine", None,
     "SIZE_ZERO_INVALID"),
    ("weight vs fluid ounces", "Nutty Acres Crunchy Peanut Butter", "16 fl oz", "Nutty Acres",
     None, "MASS_VOLUME_CONFLICT"),
    ("tied candidates abstain", "Valley Creamery Butter", "16 oz", "Valley Creamery", None, None),
    ("token overlap: yogurt is not milk", "Meadowlark Whole Milk Plain Yogurt", "32 oz",
     "Meadowlark", "C130", None),
    ("token overlap: unrelated product", "Chicken Breast Shaped Dog Chew Toy", "1 ct", "", None,
     None),
    ("metric units", "Farmhouse Ground Beef 80/20", "0.4536 kg", "Farmhouse", "C119", None),
    ("typo tolerance", "Farmhouse Chiken Brest Boneless", "1 lb", "Farmhouse", "C103", None),
    ("unicode", "Salmon PÂTÉ Cat Food", "3 oz", "", "C144", None),
    ("low sodium modifier", "Heritage Chicken Broth, Low Sodium", "32 fl oz", "Heritage", "C126",
     None),
]


@pytest.mark.parametrize("case,raw_name,size_raw,brand_raw,expected,reason", CASES,
                         ids=[c[0] for c in CASES])
def test_adversarial(engine, listing, case, raw_name, size_raw, brand_raw, expected, reason):
    d = engine.match(listing(raw_name, size_raw, brand_raw))
    assert d["canonical_id"] == expected, d["top_candidates"]
    if reason:
        vetoes = {v for c in d["top_candidates"] for v in c["vetoes"]}
        assert reason in set(d["reason_codes"]) | vetoes


def test_abstain_shape(engine, listing):
    d = engine.match(listing("Whole Milk", "1 gal"))
    assert d["canonical_id"] is None and d["canonical_name"] is None
    assert d["match_stage"] == "abstain" and d["reviewer_flag"] is True
    assert {c["canonical_id"] for c in d["top_candidates"][:2]} == {"C107", "C108"}
    assert len(d["top_candidates"]) <= 3


def test_duplicate_cluster_detected_at_load(engine):
    assert ["C107", "C108"] in engine.index.duplicate_clusters


def test_tie_is_never_broken_by_id(engine, listing):
    d = engine.match(listing("Nutty Acres Peanut Butter", "16 oz", "Nutty Acres"))
    assert d["canonical_id"] is None
    top = d["top_candidates"]
    assert top[0]["score"] == top[1]["score"]


def test_output_has_required_fields(engine, listing):
    d = engine.match(listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse", price_cents=800))
    required = {"listing_id", "canonical_id", "canonical_name", "assigned_category",
                "normalized_size", "match_stage", "confidence", "reason_codes", "reviewer_flag"}
    assert required <= d.keys()
    assert d["normalized_size"]["dimension"] == "mass"
    assert d["unit_price"] == {"cents_per_unit": 50.0, "unit": "oz"}
    assert 0.0 <= d["confidence"] <= 1.0


def test_matching_is_deterministic(engine, listing):
    row = listing("Valley Creamery Butter", "16 oz", "Valley Creamery")
    assert engine.match(row) == engine.match(row)
