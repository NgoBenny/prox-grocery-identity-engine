import pytest

from prox_match.normalize import (
    BrandBook,
    clean_text,
    parse_organic,
    parse_size,
    token_match,
    tokens,
    unit_price,
)


@pytest.mark.parametrize("raw,total,unit,dimension,pack", [
    ("1 gal", 128, "fl oz", "volume", 1),
    ("128 fl oz", 128, "fl oz", "volume", 1),
    ("32 fl. oz.", 32, "fl oz", "volume", 1),
    ("1 lb", 16, "oz", "mass", 1),
    ("1 LB", 16, "oz", "mass", 1),
    ("16 oz", 16, "oz", "mass", 1),
    ("5oz", 5, "oz", "mass", 1),
    ("14.75 oz", 14.75, "oz", "mass", 1),
    ("1 kg", 35.274, "oz", "mass", 1),
    ("2 x 8 oz", 16, "oz", "mass", 2),
    ("1 dozen", 12, "ct", "count", 1),
    ("18-count", 18, "ct", "count", 1),
    ("1/2 gal", 64, "fl oz", "volume", 1),
])
def test_parse_size(raw, total, unit, dimension, pack):
    size, problem = parse_size(raw)
    assert problem is None
    assert (size.total_value, size.unit, size.dimension, size.pack_count) == (
        total, unit, dimension, pack)


def test_multipack_keeps_unit_value():
    size, _ = parse_size("2 x 8 oz")
    assert size.unit_value == 8 and size.total_value == 16


def test_equivalent_sizes_compare_equal():
    assert parse_size("1 gal")[0].equals(parse_size("128 fl oz")[0])
    assert parse_size("1 lb")[0].equals(parse_size("16 oz")[0])
    assert parse_size("1 kg")[0].equals(parse_size("35.274 oz")[0])
    assert parse_size("454 g")[0].equals(parse_size("16 oz")[0])


def test_weight_never_equals_volume():
    assert not parse_size("16 oz")[0].equals(parse_size("16 fl oz")[0])


def test_close_but_different_sizes_are_not_equal():
    assert not parse_size("14.5 oz")[0].equals(parse_size("14.75 oz")[0])


@pytest.mark.parametrize("raw,problem", [
    ("", "SIZE_UNKNOWN"), ("0 oz", "SIZE_ZERO_INVALID"), ("0 x 8 oz", "SIZE_ZERO_INVALID"),
    ("family size", "SIZE_UNPARSEABLE"), ("12 parsecs", "SIZE_UNPARSEABLE"),
    ("-16 oz", "SIZE_UNPARSEABLE"), ("-1 lb", "SIZE_UNPARSEABLE"),
    ("2 x -8 oz", "SIZE_UNPARSEABLE"),
])
def test_bad_sizes_return_a_reason(raw, problem):
    assert parse_size(raw) == (None, problem)


def test_unit_price_needs_valid_size_and_price():
    size, _ = parse_size("1 lb")
    assert unit_price(800, size) == {"cents_per_unit": 50.0, "unit": "oz"}
    assert unit_price(None, size) is None
    assert unit_price(800, None) is None


def test_clean_text_unicode_and_punctuation():
    assert clean_text("Salmon Pâté – OCEAN-CATCH (Canned)") == \
        "salmon pate ocean catch canned"
    assert clean_text("2% Milk, 80/20 Beef, 14.75 oz.") == "2% milk 80/20 beef 14.75 oz"


def test_tokens_singularize_consistently():
    assert tokens("Bananas Eggs Tomatoes Thighs") == ["banana", "egg", "tomato", "thigh"]
    assert tokens("Boneless Swiss") == ["boneless", "swiss"]


def test_token_match_rules():
    assert token_match("flavor", "flavored")
    assert token_match("chiken", "chicken")
    assert not token_match("salted", "unsalted")
    assert not token_match("smooth", "crunchy")


@pytest.mark.parametrize("text,expected", [
    ("Organic Baby Spinach", (True, True)),
    ("Baby Spinach", (False, False)),
    ("Non-Organic Spinach", (False, True)),
])
def test_parse_organic(text, expected):
    assert parse_organic(tokens(text)) == expected


def test_brand_book_allowlist():
    book = BrandBook({"Ocean Catch": ["ocean-catch"], "Farmhouse": ["farm house"]})
    assert book.resolve("Ocean-Catch", [])[:2] == ("Ocean Catch", "approved")
    assert book.resolve("Farm House", [])[:2] == ("Farmhouse", "approved")
    assert book.resolve("Ocean Cache", [])[:2] == (None, "unknown")
    assert book.resolve("", tokens("Farm House Chicken Breast"))[:2] == ("Farmhouse", "approved")
    assert book.resolve("", tokens("Baby Spinach"))[:2] == (None, "missing")
