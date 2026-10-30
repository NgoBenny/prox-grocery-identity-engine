"""Text, brand, size and organic normalization. Pure functions; no catalog knowledge."""

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from rapidfuzz import fuzz

# Words that never carry product identity. Domain words (whole, oat, organic, canned...) are
# deliberately NOT here; organic and form words are pulled out separately, not discarded.
STOPWORDS = {
    "a", "an", "and", "the", "of", "in", "with", "on", "for", "&",
    "oz", "fl", "lb", "lbs", "g", "kg", "ml", "l", "gal", "ct", "count", "pack", "pk",
    "dozen", "x", "ea", "each", "brand",
    # size descriptors: the numeric size is compared separately, so these are not identity
    "family", "size", "value", "jumbo", "bag",
}

# Listing words that pin down product form -> the catalog forms they allow.
FORM_CUES = {
    "canned": {"canned"}, "can": {"canned"}, "tinned": {"canned"}, "tin": {"canned"},
    "fresh": {"fresh"}, "raw": {"fresh"},
    "frozen": {"frozen"},
    "broth": {"shelf-stable broth"}, "stock": {"shelf-stable broth"},
    "steak": {"fresh", "frozen"}, "fillet": {"fresh", "frozen"},
}
CUE_FORMS = set().union(*FORM_CUES.values())  # catalog forms the cues can rule in or out
FORM_ONLY_WORDS = {"canned", "can", "tinned", "tin", "fresh", "raw", "frozen"}  # not identity
PET_WORDS = {"dog", "cat", "pet", "puppy", "kitten"}
HUMAN_DOG_FOODS = {"hot", "corn"}  # "hot dog", "corn dog" are human food

# Retailer aisle words -> catalog category, matched on whole words. Order matters:
# "Canned Fish" is PANTRY.
AISLE_WORDS = [
    ("pet", "PET"), ("frozen", "FROZEN"), ("freezer", "FROZEN"), ("canned", "PANTRY"),
    ("pantry", "PANTRY"), ("grocery", "PANTRY"), ("soup", "PANTRY"), ("broth", "PANTRY"),
    ("spice", "PANTRY"), ("cereal", "BREAKFAST"), ("breakfast", "BREAKFAST"),
    ("meat", "MEAT"), ("poultry", "MEAT"), ("seafood", "SEAFOOD"), ("fish", "SEAFOOD"),
    ("dairy", "DAIRY"), ("egg", "DAIRY"), ("cheese", "DAIRY"), ("produce", "PRODUCE"),
    ("fruit", "PRODUCE"), ("vegetable", "PRODUCE"), ("juice", "BEVERAGES"),
    ("drink", "BEVERAGES"), ("beverage", "BEVERAGES"),
]

# unit -> (dimension, factor to the dimension's base unit: oz, fl oz or ct)
UNITS = {
    "oz": ("mass", 1.0), "ounce": ("mass", 1.0), "ounces": ("mass", 1.0),
    "lb": ("mass", 16.0), "lbs": ("mass", 16.0), "pound": ("mass", 16.0),
    "pounds": ("mass", 16.0),
    "g": ("mass", 1 / 28.349523125), "gram": ("mass", 1 / 28.349523125),
    "grams": ("mass", 1 / 28.349523125),
    "kg": ("mass", 35.274), "kilogram": ("mass", 35.274),  # assessment: 1 kg ~= 35.274 oz
    "floz": ("volume", 1.0), "fluidounce": ("volume", 1.0), "fluidounces": ("volume", 1.0),
    "gal": ("volume", 128.0), "gallon": ("volume", 128.0), "gallons": ("volume", 128.0),
    "l": ("volume", 33.814), "liter": ("volume", 33.814), "litre": ("volume", 33.814),
    "ml": ("volume", 0.033814),
    "ct": ("count", 1.0), "count": ("count", 1.0), "each": ("count", 1.0), "ea": ("count", 1.0),
    "dozen": ("count", 12.0),
}
STOPWORDS |= set(UNITS)  # "gallon", "ounce" in a title are size, not identity
BASE_UNIT = {"mass": "oz", "volume": "fl oz", "count": "ct"}
SIZE_TOLERANCE = 0.01  # 1%: covers 454 g vs 16 oz and 1 kg vs 35.274 oz, not 14.5 vs 14.75 oz

_SIZE_RE = re.compile(r"^(?:(\d+)\s*[x×*]\s*)?(\d*\.?\d+)\s*([a-z ]+)$")
_TRAILING_SIZE = re.compile(r",?\s*\d+(?:\.\d+)?\s*(?:fl oz|oz|lb|gal|ct)\b.*$", re.IGNORECASE)


def clean_text(text: str) -> str:
    """NFKD, strip accents, casefold, punctuation -> space. Keeps '2%' and '80/20'."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    text = re.sub(r"(?<=\d)/(?=\d)", "\x00", text)  # protect ratios like 80/20
    text = re.sub(r"[^a-z0-9%\x00.]+", " ", text)
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", text)  # periods only survive inside numbers
    return re.sub(r"\s+", " ", text.replace("\x00", "/")).strip()


def singular(token: str) -> str:
    if len(token) > 3 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("oes"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokens(text: str) -> list[str]:
    return [singular(t) for t in clean_text(text).split()]


def strip_trailing_size(name: str) -> str:
    return _TRAILING_SIZE.sub("", name).strip(" ,")


def token_match(a: str, b: str) -> bool:
    """Equal, a shared prefix of 5+ chars (flavor/flavored), or a one-letter typo (RapidFuzz).
    The same-first-letter rule keeps salted/unsalted apart."""
    if a == b:
        return True
    short, long_ = sorted((a, b), key=len)
    if len(short) >= 5 and long_.startswith(short):
        return True
    return len(short) >= 5 and a[0] == b[0] and fuzz.ratio(a, b) >= 90


def contains_phrase(toks: list[str], phrase: list[str]) -> int:
    """Index where `phrase` starts inside `toks`, or -1."""
    n = len(phrase)
    for i in range(len(toks) - n + 1):
        if toks[i:i + n] == phrase:
            return i
    return -1


@dataclass(frozen=True)
class Size:
    total_value: float
    unit: str  # base unit: oz | fl oz | ct
    dimension: str  # mass | volume | count
    pack_count: int
    unit_value: float

    def as_dict(self) -> dict:
        return asdict(self)

    def equals(self, other: "Size") -> bool:
        return (self.dimension == other.dimension
                and abs(self.total_value - other.total_value)
                <= SIZE_TOLERANCE * max(self.total_value, other.total_value))


def parse_size(raw: str) -> tuple[Size | None, str | None]:
    """-> (Size, None) or (None, SIZE_UNKNOWN | SIZE_ZERO_INVALID | SIZE_UNPARSEABLE)."""
    text = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", (raw or "").casefold())  # "fl. oz." -> "fl oz"
    text = re.sub(r"(\d+)/([1-9]\d*)", lambda m: f"{int(m[1]) / int(m[2]):g}", text)  # 1/2 gal
    text = re.sub(r"[\s-]+", " ", text).strip()  # "18-count" -> "18 count"
    if not text:
        return None, "SIZE_UNKNOWN"
    m = _SIZE_RE.match(text)
    if not m:
        return None, "SIZE_UNPARSEABLE"
    pack = int(m.group(1) or 1)
    value = float(m.group(2))
    unit = m.group(3).replace(" ", "")
    if unit not in UNITS:
        return None, "SIZE_UNPARSEABLE"
    if value <= 0 or pack <= 0:
        return None, "SIZE_ZERO_INVALID"
    dimension, factor = UNITS[unit]
    unit_value = round(value * factor, 3)
    return Size(round(unit_value * pack, 3), BASE_UNIT[dimension], dimension, pack,
                unit_value), None


def aisle_category(retailer_category: str) -> str | None:
    words = set(tokens(retailer_category))
    return next((cat for word, cat in AISLE_WORDS if word in words), None)


def mentions_pet(toks: list[str]) -> bool:
    return any(t in PET_WORDS and not (t == "dog" and i and toks[i - 1] in HUMAN_DOG_FOODS)
               for i, t in enumerate(toks))


def parse_organic(toks: list[str]) -> tuple[bool, bool]:
    """-> (organic, explicit). No organic word = non-organic, inferred (decided policy)."""
    for i, t in enumerate(toks):
        if t == "organic":
            negated = i > 0 and toks[i - 1] in {"non", "not"}
            return (not negated), True
    return False, False


def unit_price(price_cents: int | None, size: Size | None) -> dict | None:
    if price_cents is None or size is None:
        return None
    return {"cents_per_unit": round(price_cents / size.total_value, 4), "unit": size.unit}


class BrandBook:
    """Approved brand allowlist: normalized alias -> canonical brand."""

    def __init__(self, aliases: dict[str, list[str]], catalog_brands=()):
        self.alias_to_brand: dict[str, str] = {}
        for brand, names in aliases.items():
            if brand.startswith("_"):
                continue
            for name in [brand, *names]:
                self.alias_to_brand[clean_text(name)] = brand
        for brand in catalog_brands:  # a catalog brand is always its own approved alias
            if brand:
                self.alias_to_brand.setdefault(clean_text(brand), brand)
        # longest first so "farmhouse farms" wins over "farmhouse"
        self._phrases = sorted(self.alias_to_brand, key=lambda a: -len(a))

    @classmethod
    def from_file(cls, path: str | Path, catalog_brands=()) -> "BrandBook":
        return cls(json.loads(Path(path).read_text(encoding="utf-8-sig")), catalog_brands)

    def resolve(self, brand_raw: str, name_tokens: list[str]) -> tuple[str | None, str, list[str]]:
        """-> (brand, status, brand_tokens). status: approved | unknown | missing.

        brand_tokens are the name tokens that spelled the brand, so callers can drop them."""
        cleaned = clean_text(brand_raw)
        if cleaned:
            brand_toks = [singular(t) for t in cleaned.split()]
            if cleaned in self.alias_to_brand:
                return self.alias_to_brand[cleaned], "approved", brand_toks
            return None, "unknown", brand_toks
        for alias in self._phrases:  # no brand field: look for an approved brand in the title
            alias_toks = [singular(t) for t in alias.split()]
            if contains_phrase(name_tokens, alias_toks) >= 0:
                return self.alias_to_brand[alias], "approved", alias_toks
        return None, "missing", []
