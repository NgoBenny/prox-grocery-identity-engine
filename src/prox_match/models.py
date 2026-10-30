"""Validated input records and the JSONL loader shared by the CLI, API and tests."""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CanonicalProduct(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    canonical_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    brand: str | None = None  # None = unbranded / generic
    category: str = Field(min_length=1)
    type: str = Field(min_length=1)
    form: str = Field(min_length=1)
    organic: bool
    size_value: float = Field(gt=0)
    size_unit: str = Field(min_length=1)


class RetailerListing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    listing_id: str = Field(min_length=1)
    retailer: str = Field(min_length=1)
    raw_name: str = Field(min_length=1)
    brand_raw: str = ""
    size_raw: str = ""
    retailer_category: str = ""
    price_cents: int | None = Field(default=None, ge=0)  # None = price not provided


class TruthLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    listing_id: str
    expected_canonical_id: str | None  # None = ABSTAIN is the correct answer
    expected_category: str | None  # None = no catalog category applies
    split: Literal["dev", "heldout"]
    case: str
    note: str
    reviewed_by_candidate: bool


class FixtureError(ValueError):
    """A fixture file is missing, malformed or fails schema validation."""


def load_jsonl[M: BaseModel](path: str | Path, model: type[M]) -> list[M]:
    path = Path(path)
    if not path.is_file():
        raise FixtureError(f"{path}: file not found")
    records = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            records.append(model.model_validate(json.loads(line)))
        except (json.JSONDecodeError, ValidationError) as e:
            raise FixtureError(f"{path}:{lineno}: {e}") from e
    return records
