import threading
import time

import pytest

from prox_match.category import FakeUpstreamWorker, aisle_category, ask_upstream


def test_retailer_category_is_overridden_by_catalog(engine, listing):
    d = engine.match(listing("Heritage Chicken Broth", "32 fl oz", "Heritage",
                             retailer_category="Meat & Poultry"))
    assert d["canonical_id"] == "C104" and d["assigned_category"] == "PANTRY"
    assert "RETAILER_CATEGORY_OVERRIDDEN" in d["reason_codes"]


@pytest.mark.parametrize("mode,reason", [("uncertain", "UPSTREAM_CATEGORY_UNCERTAIN"),
                                         ("timeout", "UPSTREAM_TIMEOUT")])
def test_upstream_uncertainty_never_overwrites_approved_category(engine, listing, mode, reason):
    d = engine.match(listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse"),
                     FakeUpstreamWorker(mode))
    assert d["assigned_category"] == "MEAT"
    assert {reason, "APPROVED_CATEGORY_PRESERVED"} <= set(d["reason_codes"])


def test_timeout_is_bounded(engine, listing):
    start = time.perf_counter()
    engine.match(listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse"),
                 FakeUpstreamWorker("timeout", delay_s=2.0))
    assert time.perf_counter() - start < 1.0


def test_abandoned_timeouts_do_not_delay_later_calls(listing):  # issue #2
    row = listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse")
    slow = FakeUpstreamWorker("timeout", delay_s=2.0)
    for _ in range(6):  # more stuck calls than the old 4-thread pool had workers
        assert ask_upstream(slow, row, timeout_s=0.05) == ("CATEGORY_UNCERTAIN", "UPSTREAM_TIMEOUT")
    assert ask_upstream(FakeUpstreamWorker("confident", "MEAT"), row, timeout_s=0.5) == (
        "MEAT", None)


def test_upstream_saturation_is_bounded_and_recovers(monkeypatch, listing):
    from prox_match import category

    monkeypatch.setattr(category, "_upstream_slots", threading.BoundedSemaphore(2), raising=False)
    release = threading.Event()
    started = []

    class Blocked:
        def suggest(self, _):
            started.append(threading.current_thread())
            release.wait(2)
            return "MEAT"

    row = listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse")
    fast = FakeUpstreamWorker("confident", "MEAT")
    try:
        for _ in range(2):
            assert ask_upstream(Blocked(), row, timeout_s=0.01) == (
                "CATEGORY_UNCERTAIN", "UPSTREAM_TIMEOUT")
        assert ask_upstream(fast, row) == ("CATEGORY_UNCERTAIN", "UPSTREAM_TIMEOUT")
        assert len(started) == 2
    finally:
        release.set()
        for thread in started:
            thread.join(1)
    assert ask_upstream(fast, row) == ("MEAT", None)


def test_thread_start_failure_preserves_category_and_releases_capacity(monkeypatch, engine, listing):
    from prox_match import category

    monkeypatch.setattr(category, "_upstream_slots", threading.BoundedSemaphore(1), raising=False)
    row = listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse")
    worker = FakeUpstreamWorker("confident", "PET")

    def unavailable(_):
        raise RuntimeError("can't start new thread")

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", unavailable)
        decision = engine.match(row, worker)
        assert decision["assigned_category"] == "MEAT"
        assert "UPSTREAM_ERROR" in decision["reason_codes"]
    assert ask_upstream(worker, row) == ("PET", None)


def test_confident_conflict_flags_review_but_keeps_category(engine, listing):
    d = engine.match(listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse"),
                     FakeUpstreamWorker("confident", "PET"))
    assert d["assigned_category"] == "MEAT" and d["reviewer_flag"] is True
    assert "CATEGORY_CONFLICT_REVIEW" in d["reason_codes"]


def test_explicit_conflict_review_can_apply_upstream_category(engine, listing):
    d = engine.match(listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse"),
                     FakeUpstreamWorker("confident", "FROZEN"), conflict_review=True)
    assert d["assigned_category"] == "FROZEN"
    assert "CATEGORY_OVERRIDDEN_BY_CONFLICT_REVIEW" in d["reason_codes"]


def test_crashing_worker_is_treated_as_uncertain(engine, listing):
    class Broken:
        def suggest(self, _):
            raise RuntimeError("model server down")

    d = engine.match(listing("Farmhouse Chicken Breast", "1 lb", "Farmhouse"), Broken())
    assert d["assigned_category"] == "MEAT" and "UPSTREAM_ERROR" in d["reason_codes"]


def test_abstain_uses_shared_candidate_category(engine, listing):
    d = engine.match(listing("Whole Milk", "1 gal"))
    assert d["canonical_id"] is None and d["assigned_category"] == "DAIRY"


def test_abstain_with_mixed_candidates_is_unknown(engine, listing):
    d = engine.match(listing("SpiceWorks Chicken Breast Seasoning Rub", "2.5 oz", "SpiceWorks"))
    assert d["assigned_category"] == "UNKNOWN"


@pytest.mark.parametrize("label,category", [("Canned Fish", "PANTRY"), ("Meat & Poultry", "MEAT"),
                                            ("Pet Supplies", "PET"), ("Gadgets", None),
                                            ("Fresh Veggies", None), ("Petite Sizes", None)])
def test_aisle_category(label, category):
    assert aisle_category(label) == category
