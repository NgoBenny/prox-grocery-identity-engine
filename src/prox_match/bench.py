"""Local benchmark: engine build (index + matching every listing + search index) and repeated
searches. Reports measured wall-clock numbers only; timings vary run to run.

Cache policy: no result cache. The index is immutable and built once at startup, and match
decisions are computed once at load, so a search never re-runs the matcher.
"""

import math
import os
import platform
import time

from .engine import Engine

QUERIES = [  # cycled to reach the requested count; mixes exact, fuzzy, filtered and no-hit
    ("chicken breast", None), ("chicken breast", "FreshTown"), ("chiken brest", None),
    ("whole milk", None), ("oat milk", "ValueMart"), ("organic baby spinach", None),
    ("sharp cheddar", "MarketSquare"), ("dog food", None), ("Heritage", None),
    ("pretzels", None),
]


def percentile(samples: list[float], p: float) -> float:
    """Nearest-rank percentile."""
    ordered = sorted(samples)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def _summary(samples_ms: list[float]) -> dict:
    return {"count": len(samples_ms), "p50_ms": round(percentile(samples_ms, 50), 4),
            "p95_ms": round(percentile(samples_ms, 95), 4), "max_ms": round(max(samples_ms), 4)}


def run(searches: int = 100, warmup: int = 10, catalog=None, listings=None, aliases=None) -> dict:
    if searches < 1 or warmup < 0:
        raise ValueError("searches must be >= 1 and warmup >= 0")
    start = time.perf_counter_ns()
    engine = Engine.from_paths(catalog, listings, aliases)
    build_ms = (time.perf_counter_ns() - start) / 1e6

    # another corpus may not have our retailers: drop filters it can't honor
    retailers = {row.retailer for row in engine.listings.values()}
    queries = [(q, r if r in retailers else None) for q, r in QUERIES]
    plan = [queries[i % len(queries)] for i in range(warmup + searches)]
    for q, retailer in plan[:warmup]:
        engine.search(q, retailer)
    search_ms = []
    for q, retailer in plan[warmup:]:
        t = time.perf_counter_ns()
        engine.search(q, retailer)
        search_ms.append((time.perf_counter_ns() - t) / 1e6)

    match_ms = []
    for row in engine.listings.values():
        t = time.perf_counter_ns()
        engine.match(row)
        match_ms.append((time.perf_counter_ns() - t) / 1e6)

    return {
        "corpus": {"canonical_ids": len(engine.index.products), "listings": len(engine.listings),
                   "index_terms": len(engine.index.postings),
                   "search_terms": len(engine.search_index.postings)},
        "build_ms": round(build_ms, 2),
        "search": {**_summary(search_ms), "warmup": warmup, "distinct_queries": len(QUERIES)},
        "match_one_listing": _summary(match_ms),
        "percentile_method": "nearest-rank",
        "cache_policy": "no result cache; immutable in-memory index; decisions precomputed at load",
        "machine": {"platform": platform.platform(), "python": platform.python_version(),
                    "processor": platform.processor() or "unknown", "cpu_count": os.cpu_count()},
    }
