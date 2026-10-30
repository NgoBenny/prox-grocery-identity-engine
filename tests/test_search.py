import pytest


def _ids(result):
    return [r["canonical_id"] for r in result["results"]]


def test_chicken_breast_excludes_broth_pet_food_and_seasoning(engine):
    result = engine.search("chicken breast")
    categories = {r["assigned_category"] for r in result["results"]}
    assert result["results"] and categories <= {"MEAT", "FROZEN"}
    assert not {"C104", "C126", "C111", "C143"} & set(_ids(result))
    assert all("seasoning" not in r["raw_name"].lower() for r in result["results"])


def test_plain_breast_ranks_above_breaded_nuggets(engine):
    assert _ids(engine.search("chicken breast", "FreshTown"))[0] == "C103"


def test_retailer_filter(engine):
    result = engine.search("chicken breast", "freshtown")
    assert {r["retailer"] for r in result["results"]} == {"FreshTown"}


def test_dedup_by_retailer_and_canonical(engine):
    result = engine.search("chicken breast")
    keys = [(r["retailer"], r["canonical_id"]) for r in result["results"]]
    assert len(keys) == len(set(keys))
    assert result["deduplicated"]  # MarketSquare stocks C103 twice (T007, G004)


def test_abstained_listings_are_not_merged(engine):
    result = engine.search("whole milk", "FreshTown")
    abstained = [r for r in result["results"] if r["canonical_id"] is None]
    assert len(abstained) >= 2


def test_milk_query_excludes_oat_milk_and_yogurt(engine):
    assert not {"C113", "C114", "C129", "C130"} & set(_ids(engine.search("milk")))


def test_typo_fallback(engine):
    assert "C103" in _ids(engine.search("chiken brest"))


def test_related_fallback_when_no_exact_hit(engine):
    result = engine.search("chicken thighs", "FreshTown")
    assert result["fallback"] is True
    assert all(r["components"]["tier"] == 0 and r["assigned_category"] == "MEAT"
               for r in result["results"])


def test_no_safe_match_returns_empty(engine):
    result = engine.search("pretzels")
    assert result["results"] == [] and result["reason"] == "no_safe_match"


def test_scoring_components_exposed_and_sorted(engine):
    results = engine.search("chicken breast")["results"]
    assert {"tier", "query_coverage", "listing_coverage", "match_confidence"} <= \
        results[0]["components"].keys()
    assert [r["score"] for r in results] == sorted((r["score"] for r in results), reverse=True)


def test_intent_prefilter_matches_full_catalog_scan(engine):  # issue #3
    from prox_match.models import RetailerListing
    from prox_match.normalize import token_match

    index = engine.index
    for q in ["chicken breast", "chiken brest", "milk", "organic baby spinach", "dog food",
              "sharp cheddar", "pretzels"]:
        qf = index.listing_features(RetailerListing(listing_id="q", retailer="-", raw_name=q))
        # every product that covers all query words must be in the indexed pool
        covering = {cid for cid, cf in index.features.items()
                    if all(any(token_match(w, t) for t in
                               set(cf.tokens) | {x for ph in cf.types for x in ph.split()})
                           for w in qf.tokens)}
        assert covering <= index.candidates(qf), q


def test_brand_only_query(engine):
    result = engine.search("Heritage")
    assert result["results"] and all(
        r["canonical_id"] in {"C104", "C125", "C126"} for r in result["results"])


def test_organic_query_never_falls_back_to_conventional_spinach(engine):
    result = engine.search("organic baby spinach", "ValueMart")
    assert result["results"] == [] and result["reason"] == "no_safe_match"
    assert "C109" in _ids(engine.search("organic baby spinach", "FreshTown"))


def test_branded_query_excludes_other_brands(engine):
    ids = set(_ids(engine.search("Farmhouse chicken breast")))
    assert "C103" in ids and "C122" not in ids


@pytest.mark.parametrize("q,retailer", [("   ", None), ("chicken", "NoSuchMart")])
def test_bad_queries_raise_value_error(engine, q, retailer):
    with pytest.raises(ValueError):
        engine.search(q, retailer)
