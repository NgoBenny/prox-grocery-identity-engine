"""Category safeguard: the approved catalog category wins over retailers and upstream AI.

Rules:
  matched listing  -> assigned_category = canonical category, always.
                      Upstream CATEGORY_UNCERTAIN / timeout never changes it.
                      A confident, different upstream category only sets reviewer_flag,
                      unless the caller passes conflict_review=True (an explicit, flagged
                      human-review decision), which applies the upstream category.
  abstained listing -> the category its plausible candidates agree on, else a confident
                      upstream suggestion (flagged), else UNKNOWN.
"""

import threading
import time

from .index import CatalogIndex
from .normalize import aisle_category

UNCERTAIN = "CATEGORY_UNCERTAIN"
UNKNOWN = "UNKNOWN"
UPSTREAM_TIMEOUT_S = 0.2
_upstream_slots = threading.BoundedSemaphore(16)
_IDENTITY_VETOES = {"TYPE_MISMATCH", "FORM_MISMATCH", "PET_HUMAN_CONFLICT"}


class FakeUpstreamWorker:
    """Deterministic stand-in for an upstream AI category resolver. No network.

    mode: "uncertain" -> CATEGORY_UNCERTAIN; "timeout" -> sleeps past the deadline;
          "confident" -> returns `category`."""

    def __init__(self, mode: str, category: str | None = None, delay_s: float = 1.0):
        if mode not in {"uncertain", "timeout", "confident"}:
            raise ValueError(f"unknown upstream mode {mode!r}")
        self.mode, self.category, self.delay_s = mode, category, delay_s

    def suggest(self, listing) -> str:
        if self.mode == "timeout":
            time.sleep(self.delay_s)
        return self.category if self.mode == "confident" and self.category else UNCERTAIN


def ask_upstream(worker, listing, timeout_s: float = UPSTREAM_TIMEOUT_S) -> tuple[str, str | None]:
    """-> (category or CATEGORY_UNCERTAIN, reason code or None). Never raises.

    No waiting queue: saturated calls return uncertainty while existing workers finish."""
    slots = _upstream_slots
    if not slots.acquire(blocking=False):
        return UNCERTAIN, "UPSTREAM_TIMEOUT"
    result: dict = {}

    def call():
        try:
            result["value"] = worker.suggest(listing)
        except Exception:  # noqa: BLE001 - a crashing resolver is treated like an uncertain one
            result["error"] = True
        finally:
            slots.release()

    # shortcut: threads cannot be cancelled; use process isolation for real workers that may hang.
    try:
        thread = threading.Thread(target=call, daemon=True, name="upstream")
        thread.start()
    except RuntimeError:
        slots.release()
        return UNCERTAIN, "UPSTREAM_ERROR"
    thread.join(timeout_s)
    if thread.is_alive():
        return UNCERTAIN, "UPSTREAM_TIMEOUT"
    if "error" in result:
        return UNCERTAIN, "UPSTREAM_ERROR"
    return result["value"], None


def assign_category(decision: dict, index: CatalogIndex, listing, worker=None,
                    conflict_review: bool = False, timeout_s: float = UPSTREAM_TIMEOUT_S) -> dict:
    reasons = decision["reason_codes"]
    suggestion, upstream_reason = (None, None)
    if worker is not None:
        suggestion, upstream_reason = ask_upstream(worker, listing, timeout_s)
        reasons.append(upstream_reason or
                       ("UPSTREAM_CATEGORY_UNCERTAIN" if suggestion == UNCERTAIN else
                        "UPSTREAM_CATEGORY_SUGGESTED"))
    confident = suggestion not in (None, UNCERTAIN)

    if decision["canonical_id"]:
        approved = index.products[decision["canonical_id"]].category
        decision["assigned_category"] = approved
        retailer_says = aisle_category(listing.retailer_category)
        if retailer_says and retailer_says != approved:
            reasons.append("RETAILER_CATEGORY_OVERRIDDEN")
        if worker is not None and suggestion != approved:
            if confident and conflict_review:
                decision["assigned_category"] = suggestion
                reasons.append("CATEGORY_OVERRIDDEN_BY_CONFLICT_REVIEW")
            else:
                reasons.append("APPROVED_CATEGORY_PRESERVED")
            if confident:
                reasons.append("CATEGORY_CONFLICT_REVIEW")
                decision["reviewer_flag"] = True
        return decision

    plausible = {index.products[c["canonical_id"]].category for c in decision["top_candidates"]
                 if not _IDENTITY_VETOES & set(c["vetoes"])}
    if len(plausible) == 1:
        decision["assigned_category"] = plausible.pop()
        reasons.append("CATEGORY_FROM_CANDIDATES")
    elif confident:
        decision["assigned_category"] = suggestion
        reasons.append("CATEGORY_FROM_UPSTREAM")
    else:
        decision["assigned_category"] = UNKNOWN
        reasons.append("CATEGORY_UNKNOWN")
    decision["reviewer_flag"] = True
    return decision
