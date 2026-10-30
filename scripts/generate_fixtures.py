"""Regenerate fixtures/retailer_listings.jsonl, or verify it with --check.

    uv run python scripts/generate_fixtures.py          # write
    uv run python scripts/generate_fixtures.py --check  # exit 1 if the committed file differs
"""

import argparse
import sys

from prox_match.fixtures import DEFAULT_SEED, FIXTURES_DIR, render_listings, sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    args = parser.parse_args()

    target = FIXTURES_DIR / "retailer_listings.jsonl"
    expected = render_listings(seed=args.seed)
    if args.check:
        actual = target.read_text(encoding="utf-8") if target.is_file() else ""
        if actual != expected:
            print(f"MISMATCH: {target} differs from generator output (seed {args.seed})")
            return 1
        print(f"OK {target.name} sha256={sha256(actual)}")
        return 0
    target.write_text(expected, encoding="utf-8", newline="\n")
    print(f"wrote {target.name} ({expected.count(chr(10))} listings) sha256={sha256(expected)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
