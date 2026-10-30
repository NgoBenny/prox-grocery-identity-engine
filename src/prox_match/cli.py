"""Command line adapter over the shared Engine. JSON on stdout; exit 2 on bad input."""

import argparse
import json
import sys
from pathlib import Path

from .category import FakeUpstreamWorker
from .engine import Engine
from .fixtures import write_or_check
from .models import FixtureError, RetailerListing, load_jsonl

DEMO_STEPS = [
    ("Positive match: brand alias 'Farm House' + '1 LB' = 16 oz", "T007", None),
    ("Corrected category: broth the retailer filed under 'Meat & Poultry'", "T008", None),
    ("Corrected category: dog food the retailer filed under 'Meat'", "T010", None),
    ("ABSTAIN: whole milk fits duplicate IDs C107 and C108", "T014", None),
    ("Veto: raw tuna steak never matches canned tuna", "T003", None),
    ("ABSTAIN: false brand alias 'Ocean Cache'", "T004", None),
    ("Upstream AI says CATEGORY_UNCERTAIN: approved category kept", "T006",
     ("uncertain", None)),
    ("Upstream AI times out: approved category kept", "T006", ("timeout", None)),
    ("Upstream AI confidently disagrees: category kept, reviewer flagged", "T006",
     ("confident", "PET")),
]


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _worker(args):
    if args.upstream == "none":
        return None
    if args.upstream == "confident" and not args.upstream_category:
        raise ValueError("--upstream confident needs --upstream-category")
    return FakeUpstreamWorker(args.upstream, args.upstream_category)


def cmd_demo(engine: Engine, args) -> int:
    report = []
    for title, lid, upstream in DEMO_STEPS:
        worker = FakeUpstreamWorker(*upstream) if upstream else None
        d = engine.match(engine.listings[lid], worker)
        print(f"\n## {title}\n   {lid}: {engine.listings[lid].raw_name!r}")
        print(f"   -> {d['canonical_id']} ({d['canonical_name']}), category {d['assigned_category']},"
              f" stage {d['match_stage']}, confidence {d['confidence']}, review {d['reviewer_flag']}")
        print(f"   reasons: {', '.join(d['reason_codes'])}")
        for c in d["top_candidates"]:
            print(f"     candidate {c['canonical_id']} score {c['score']} vetoes {c['vetoes']}")
        report.append({"title": title, "decision": d})
    for q, retailer in [("chicken breast", "FreshTown"), ("chicken breast", None),
                        ("chicken thighs", "FreshTown"), ("pretzels", None)]:
        s = engine.search(q, retailer)
        print(f"\n## Search {q!r} retailer={retailer} fallback={s['fallback']} reason={s['reason']}")
        for r in s["results"]:
            print(f"   {r['score']:.3f} {r['listing_id']} {r['retailer']}: {r['raw_name']}"
                  f" -> {r['canonical_id']} {r['assigned_category']}")
        report.append({"title": f"search {q} @ {retailer}", "search": s})
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                                 encoding="utf-8")
    print(f"\nwrote {args.output}")
    return 0


def cmd_match(engine: Engine, args) -> int:
    worker = _worker(args)
    if args.file:
        rows = load_jsonl(args.file, RetailerListing)
        _emit([engine.match(row, worker, args.conflict_review) for row in rows])
        return 0
    if args.listing_id not in engine.listings:
        raise ValueError(f"unknown listing_id {args.listing_id!r}")
    _emit(engine.match(engine.listings[args.listing_id], worker, args.conflict_review))
    return 0


def cmd_search(engine: Engine, args) -> int:
    _emit(engine.search(args.query, args.retailer, args.limit))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="prox-match", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def with_data(p):
        p.add_argument("--catalog", help="canonical catalog JSONL (default: fixtures/)")
        p.add_argument("--listings", help="retailer listings JSONL (default: fixtures/)")
        p.add_argument("--aliases", help="brand alias JSON (default: fixtures/)")
        return p

    demo = with_data(sub.add_parser("demo", help="offline end-to-end walkthrough"))
    demo.add_argument("--output", default="outputs/demo_output.json")

    match = with_data(sub.add_parser("match", help="match one listing or a JSONL file"))
    target = match.add_mutually_exclusive_group(required=True)
    target.add_argument("--listing-id")
    target.add_argument("--file", help="JSONL of listings to match")
    match.add_argument("--upstream", choices=["none", "uncertain", "timeout", "confident"],
                       default="none", help="simulated upstream AI category worker")
    match.add_argument("--upstream-category")
    match.add_argument("--conflict-review", action="store_true",
                       help="explicit human review: let a confident upstream category win")

    search = with_data(sub.add_parser("search", help="ranked listing search"))
    search.add_argument("--query", "-q", required=True)
    search.add_argument("--retailer")
    search.add_argument("--limit", type=int, default=10)

    fixtures = sub.add_parser("fixtures", help="regenerate or --check generated listings")
    fixtures.add_argument("--check", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    try:
        if args.command == "fixtures":
            ok, message = write_or_check(args.check)
            print(message)
            return 0 if ok else 1
        engine = Engine.from_paths(args.catalog, args.listings, args.aliases)
        return {"demo": cmd_demo, "match": cmd_match, "search": cmd_search}[args.command](
            engine, args)
    except (FixtureError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
