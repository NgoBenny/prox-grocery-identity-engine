"""One engine object shared by the CLI, the API, the benchmark and the tests."""

from pathlib import Path

from .category import assign_category
from .fixtures import FIXTURES_DIR
from .index import CatalogIndex
from .matcher import match_listing
from .models import CanonicalProduct, RetailerListing, load_jsonl
from .normalize import BrandBook
from .search import SearchIndex


class Engine:
    def __init__(self, catalog: list[CanonicalProduct], listings: list[RetailerListing],
                 brands: BrandBook):
        self.index = CatalogIndex(catalog, brands)
        self.listings = {row.listing_id: row for row in listings}
        if len(self.listings) != len(listings):
            raise ValueError("duplicate listing_id in listings")
        # Match once at load (ingest time); search reads these decisions.
        self.decisions = {lid: self.match(row) for lid, row in self.listings.items()}
        self.search_index = SearchIndex(self)

    def search(self, q: str, retailer: str | None = None, limit: int = 10) -> dict:
        return self.search_index.search(q, retailer, limit)

    @classmethod
    def from_paths(cls, catalog: str | Path | None = None, listings: str | Path | None = None,
                   aliases: str | Path | None = None) -> "Engine":
        catalog_rows = load_jsonl(catalog or FIXTURES_DIR / "canonical_catalog.jsonl",
                                  CanonicalProduct)
        listing_rows = load_jsonl(listings or FIXTURES_DIR / "retailer_listings.jsonl",
                                  RetailerListing)
        brands = BrandBook.from_file(aliases or FIXTURES_DIR / "brand_aliases.json",
                                     [p.brand for p in catalog_rows])
        return cls(catalog_rows, listing_rows, brands)

    def match(self, listing: RetailerListing, worker=None, conflict_review: bool = False) -> dict:
        decision = match_listing(self.index, listing)
        return assign_category(decision, self.index, listing, worker, conflict_review)
