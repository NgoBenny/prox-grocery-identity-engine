"""Regenerate fixtures/retailer_listings.jsonl, or verify it with --check.

    uv run python scripts/generate_fixtures.py          # write
    uv run python scripts/generate_fixtures.py --check  # exit 1 if the committed file differs
"""

import argparse
import sys

from prox_match.fixtures import DEFAULT_SEED, write_or_check


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--check", action="store_true", help="verify instead of writing")
    args = parser.parse_args()
    ok, message = write_or_check(args.check, args.seed)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
