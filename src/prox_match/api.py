"""HTTP adapter. Thin: every route calls the shared Engine.

    uv run uvicorn prox_match.api:app --port 8000      # docs at /docs
"""

from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from . import __version__
from .category import FakeUpstreamWorker
from .engine import Engine
from .models import RetailerListing


def create_app(engine: Engine | None = None) -> FastAPI:
    engine = engine or Engine.from_paths()
    app = FastAPI(title="prox-match", version=__version__)

    @app.exception_handler(ValueError)
    async def bad_request(_, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/health")
    def health():
        return {"status": "ok", "version": __version__,
                "catalog_count": len(engine.index.products),
                "listing_count": len(engine.listings),
                "retailer_count": len({r.retailer for r in engine.listings.values()}),
                "catalog_duplicate_clusters": engine.index.duplicate_clusters}

    @app.post("/match")
    def match(listing: RetailerListing,
              upstream: Literal["none", "uncertain", "timeout", "confident"] = "none",
              upstream_category: str | None = None, conflict_review: bool = False):
        """Match one listing. `upstream` simulates the AI category worker (offline fake)."""
        if upstream == "confident" and not upstream_category:
            raise ValueError("upstream=confident needs upstream_category")
        worker = None if upstream == "none" else FakeUpstreamWorker(upstream, upstream_category)
        return engine.match(listing, worker, conflict_review)

    @app.get("/match/{listing_id}")
    def match_by_id(listing_id: str):
        if listing_id not in engine.decisions:
            raise HTTPException(status_code=404, detail=f"unknown listing_id {listing_id!r}")
        return engine.decisions[listing_id]

    @app.get("/search")
    def search(q: str = Query(min_length=1, max_length=200), retailer: str | None = None,
               limit: int = Query(10, ge=1, le=50)):
        return engine.search(q, retailer, limit)

    return app


app = create_app()
