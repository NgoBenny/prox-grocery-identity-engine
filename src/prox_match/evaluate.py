"""Quality metrics against the hand-labeled truth file. Reads truth, never writes it.

Accounting (a prediction is a canonical ID or ABSTAIN = None):
  TP  expected ID, predicted the same ID
  TN  expected ABSTAIN, predicted ABSTAIN
  FP  predicted an ID that is not the expected one (including when ABSTAIN was expected)
  FN  expected an ID, predicted ABSTAIN or a different ID
A wrong-ID prediction is therefore both an FP and an FN. Zero denominators report None.
"""

import datetime as dt
import platform
from collections import Counter

from .fixtures import sha256
from .matcher import ACCEPT_THRESHOLD, HIGH_CONFIDENCE, MIN_MARGIN
from .models import TruthLabel


def _rate(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def score(decisions: dict[str, dict], truth: list[TruthLabel]) -> dict:
    missing = [t.listing_id for t in truth if t.listing_id not in decisions]
    if missing:
        raise ValueError(f"truth labels for unknown listings: {missing}")
    repeated = sorted(lid for lid, n in Counter(t.listing_id for t in truth).items() if n > 1)
    if repeated:
        raise ValueError(f"truth labels repeat listings: {repeated}")
    tp = tn = fp = fn = 0
    high_conf = high_conf_wrong = 0
    category_known = category_wrong = 0
    report = {"false_matches": [], "missed_matches": [], "correct_abstentions": [],
              "category_errors": []}

    for t in truth:
        d = decisions[t.listing_id]
        pred, exp = d["canonical_id"], t.expected_canonical_id
        row = {"listing_id": t.listing_id, "expected": exp, "predicted": pred,
               "confidence": d["confidence"], "reason_codes": d["reason_codes"], "note": t.note}
        if pred == exp:
            if exp is None:
                tn += 1
                report["correct_abstentions"].append(row)
            else:
                tp += 1
        else:
            if pred is not None:
                fp += 1
                report["false_matches"].append(row)
            if exp is not None:
                fn += 1
                if pred is None:
                    report["missed_matches"].append(row)
        if pred is not None and d["confidence"] >= HIGH_CONFIDENCE:
            high_conf += 1
            high_conf_wrong += pred != exp
        if t.expected_category is not None:
            category_known += 1
            assigned = None if d["assigned_category"] == "UNKNOWN" else d["assigned_category"]
            if assigned != t.expected_category:
                category_wrong += 1
                report["category_errors"].append(
                    {**row, "expected_category": t.expected_category, "assigned_category": assigned})

    n = len(truth)
    return {
        "n": n,
        "confusion": {"tp": tp, "tn": tn, "fp": fp, "fn": fn},
        "metrics": {
            "precision": _rate(tp, tp + fp),
            "recall": _rate(tp, tp + fn),
            "exact_id_accuracy": _rate(tp + tn, n),
            "abstention_rate": _rate(sum(decisions[t.listing_id]["canonical_id"] is None
                                         for t in truth), n),
            "high_confidence_false_positive_rate": _rate(high_conf_wrong, high_conf),
            "high_confidence_matches": high_conf,
            "category_error_rate": _rate(category_wrong, category_known),
        },
        "report": report,
    }


def evaluate(engine, truth: list[TruthLabel], truth_text: str, splits: list[str]) -> dict:
    out = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "truth_sha256": sha256(truth_text),
        "policy": {"accept_threshold": ACCEPT_THRESHOLD, "min_margin": MIN_MARGIN,
                   "high_confidence": HIGH_CONFIDENCE},
        "notes": ["confidence is a heuristic ranking score, not a calibrated probability",
                  f"{len(truth)} labels is far too few for statistical claims"],
        "splits": {},
    }
    for split in splits:
        subset = truth if split == "all" else [t for t in truth if t.split == split]
        out["splits"][split] = score(engine.decisions, subset)
    return out
