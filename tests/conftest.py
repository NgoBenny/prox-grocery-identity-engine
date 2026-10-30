import pytest

from prox_match.engine import Engine
from prox_match.models import RetailerListing


@pytest.fixture(scope="session")
def engine() -> Engine:
    return Engine.from_paths()


@pytest.fixture
def listing():
    """Build an ad-hoc listing; tests state their inputs instead of reusing truth fixtures."""
    def make(raw_name, size_raw, brand_raw="", retailer_category="", price_cents=399):
        return RetailerListing(listing_id="X", retailer="TestMart", raw_name=raw_name,
                               brand_raw=brand_raw, size_raw=size_raw,
                               retailer_category=retailer_category, price_cents=price_cents)
    return make
