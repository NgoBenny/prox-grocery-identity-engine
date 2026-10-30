"""Metric math on hand-built decisions, plus truth-file immutability and the benchmark."""

import pytest

from prox_match import bench
from prox_match.cli import main
from prox_match.evaluate import score
from prox_match.fixtures import FIXTURES_DIR, sha256
from prox_match.models import TruthLabel


def _decision(cid, confidence=0.95, category="DAIRY"):
    return {"canonical_id": cid, "confidence": confidence, "assigned_category": category,
            "reason_codes": []}


def _label(lid, expected, category="DAIRY", split="dev"):
    return TruthLabel(listing_id=lid, expected_canonical_id=expected, expected_category=category,
                      split=split)


def test_confusion_accounting_and_rates():
    decisions = {
        "a": _decision("C1"),                       # TP
        "b": _decision(None, 0.0),                  # TN
        "c": _decision("C2"),                       # wrong ID: FP + FN
        "d": _decision(None, 0.0),                  # FN (missed)
        "e": _decision("C3", 0.80),                 # FP on an expected ABSTAIN, low confidence
    }
    truth = [_label("a", "C1"), _label("b", None), _label("c", "C9"), _label("d", "C4"),
             _label("e", None)]
    s = score(decisions, truth)
    assert s["confusion"] == {"tp": 1, "tn": 1, "fp": 2, "fn": 2}
    m = s["metrics"]
    assert m["precision"] == round(1 / 3, 4)
    assert m["recall"] == round(1 / 3, 4)
    assert m["exact_id_accuracy"] == 0.4
    assert m["abstention_rate"] == 0.4
    assert m["high_confidence_matches"] == 2  # a and c are >= 0.90
    assert m["high_confidence_false_positive_rate"] == 0.5
    assert [r["listing_id"] for r in s["report"]["false_matches"]] == ["c", "e"]
    assert [r["listing_id"] for r in s["report"]["missed_matches"]] == ["d"]


def test_zero_denominators_are_none_not_perfect():
    s = score({"a": _decision(None, 0.0)}, [_label("a", None)])
    assert s["metrics"]["precision"] is None and s["metrics"]["recall"] is None
    assert s["metrics"]["high_confidence_false_positive_rate"] is None


def test_category_errors_treat_unknown_as_no_category():
    decisions = {"a": _decision(None, 0.0, "UNKNOWN"), "b": _decision(None, 0.0, "UNKNOWN"),
                 "c": _decision("C1", category="MEAT")}
    truth = [_label("a", None, category=None), _label("b", None, category="PANTRY"),
             _label("c", "C1", category="PANTRY")]
    s = score(decisions, truth)
    assert s["metrics"]["category_error_rate"] == 1.0  # b and c wrong; a not counted
    assert {r["listing_id"] for r in s["report"]["category_errors"]} == {"b", "c"}


def test_unknown_listing_in_truth_is_an_error():
    with pytest.raises(ValueError, match="unknown listings"):
        score({}, [_label("ghost", None)])


def test_evaluate_cli_never_modifies_truth(tmp_path, capsys):
    truth = FIXTURES_DIR / "ground_truth.jsonl"
    before = sha256(truth.read_text(encoding="utf-8"))
    out = tmp_path / "report.json"
    assert main(["evaluate", "--split", "dev", "--output", str(out)]) == 0
    assert sha256(truth.read_text(encoding="utf-8")) == before
    assert out.is_file()


def test_percentile_nearest_rank():
    samples = list(range(1, 101))
    assert bench.percentile(samples, 50) == 50
    assert bench.percentile(samples, 95) == 95
    assert bench.percentile([7.0], 95) == 7.0


def test_benchmark_runs_requested_searches():
    result = bench.run(searches=12, warmup=2)
    assert result["search"]["count"] == 12
    assert result["search"]["p50_ms"] <= result["search"]["p95_ms"]
    with pytest.raises(ValueError):
        bench.run(searches=0)


def test_benchmark_on_a_corpus_without_our_retailers(tmp_path):
    listings = tmp_path / "listings.jsonl"
    listings.write_text('{"listing_id": "Z1", "retailer": "OtherMart", "raw_name": "Whole Milk",'
                        ' "size_raw": "1 gal"}\n', encoding="utf-8")
    assert bench.run(searches=10, warmup=0, listings=listings)["search"]["count"] == 10
