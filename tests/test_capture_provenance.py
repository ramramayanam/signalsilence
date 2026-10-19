"""Phase 3, Iteration 3: capture-time provenance (data_source, assessed_at).

New decisions store, inside the existing system_snapshot JSON, where the
case came from and when the reviewed assessment was produced. assessed_at
is stamped inside the cached assessment, so reruns, case switches and other
sessions reuse it; only a new assessment (e.g. after Retry) gets a new one.
No schema change; fake LLMs only.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from signalsilence import review_store  # noqa: E402
from signalsilence.demo_cases import CANONICAL, data_source  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

REVIEW_PAGE = str(ROOT / "pages" / "1_Analyst_Review.py")
PROV_PAGE = str(ROOT / "pages" / "2_Decision_Provenance.py")
DEMO = {c.case_id: c for c in CANONICAL.values()}
NOT_RECORDED = "Not recorded at decision time"


def snapshot(event):
    return json.loads(event["system_snapshot"])


def parse_utc(value):
    ts = datetime.fromisoformat(value)
    assert ts.tzinfo is not None and ts.utcoffset().total_seconds() == 0
    return ts


# --- Store and source descriptor (no streamlit) -----------------------------------------

def test_record_decision_stores_provenance_when_given(tmp_path):
    db = tmp_path / "r.db"
    at = datetime.now(timezone.utc).isoformat(timespec="microseconds")
    review_store.record_decision(db, DEMO["demo_1"], triage(DEMO["demo_1"], use_llm=False),
                                 "confirm_flag", assessment_mode="offline",
                                 data_source=data_source("demo_1"), assessed_at=at)
    [event] = review_store.case_history(db, "demo_1")
    snap = snapshot(event)
    assert snap["data_source"] == {"type": "synthetic_demo_case", "reference": "demo_cases:demo_1"}
    assert snap["assessed_at"] == at


def test_record_decision_backward_compatible_without_provenance(tmp_path):
    db = tmp_path / "r.db"
    review_store.record_decision(db, DEMO["demo_1"], triage(DEMO["demo_1"], use_llm=False),
                                 "dismiss_flag", "old-style call", "offline")
    [event] = review_store.case_history(db, "demo_1")
    assert "data_source" not in snapshot(event) and "assessed_at" not in snapshot(event)
    assert event["analyst_note"] == "old-style call"


def test_caller_can_supply_a_different_source_descriptor(tmp_path):
    db = tmp_path / "r.db"
    custom = {"type": "example_feed", "reference": "feed:123"}
    review_store.record_decision(db, DEMO["demo_2"], triage(DEMO["demo_2"], use_llm=False),
                                 "confirm_flag", data_source=custom)
    assert snapshot(review_store.case_history(db, "demo_2")[0])["data_source"] == custom


def test_demo_source_is_synthetic_and_never_uspto():
    for case_id in DEMO:
        source = data_source(case_id)
        assert source == {"type": "synthetic_demo_case", "reference": f"demo_cases:{case_id}"}
        assert "uspto" not in json.dumps(source).lower()


# --- Analyst Review page (needs streamlit) ----------------------------------------------

st = AppTest = None  # bound by the env fixture once streamlit is known to be importable


@pytest.fixture
def env(tmp_path, monkeypatch):
    global st, AppTest
    st = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    from test_review_retry import FakeLLM
    db = tmp_path / "reviews.db"
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake = FakeLLM()
    monkeypatch.setitem(sys.modules, "anthropic", fake.module)
    st.cache_data.clear()
    yield fake, db, monkeypatch
    st.cache_data.clear()


def llm_on(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")


def open_page(case_id="demo_1"):
    at = AppTest.from_file(REVIEW_PAGE, default_timeout=30).run()
    if case_id != "demo_1":
        at.radio[0].set_value(case_id).run()
    assert not at.exception
    return at


def shown_assessed_at(at):
    caption = next(str(c.value) for c in at.caption if "Produced by" in str(c.value))
    m = re.search(r"Assessment produced (\S+ \S+) UTC\.", caption)
    assert m, caption
    return m.group(1)


def record(at, case_id, decision):
    at.radio(key=f"decision_{case_id}").set_value(decision)
    next(b for b in at.button if b.label == "Record decision").click().run()
    assert not at.exception


def retry(at):
    next(b for b in at.button if b.label == "Retry LLM assessment").click().run()
    assert not at.exception


def stored_at(db, case_id, index=-1):
    return snapshot(review_store.case_history(db, case_id)[index])["assessed_at"]


def as_display(iso):
    return iso.replace("T", " ").replace("+00:00", "")


def test_new_offline_decision_stores_source_and_utc_assessed_at(env):
    _, db, _ = env
    at = open_page("demo_1")
    record(at, "demo_1", "confirm_flag")
    [event] = review_store.case_history(db, "demo_1")
    snap = snapshot(event)
    assert snap["data_source"] == {"type": "synthetic_demo_case", "reference": "demo_cases:demo_1"}
    produced = parse_utc(snap["assessed_at"])                 # valid UTC ISO-8601
    assert produced <= parse_utc(event["recorded_at"].replace("+00:00", ".999999+00:00"))
    assert as_display(snap["assessed_at"]) == shown_assessed_at(at)


def test_cached_reruns_keep_the_same_assessed_at(env):
    _, db, _ = env
    at = open_page("demo_1")
    first = shown_assessed_at(at)
    at.run()
    at.run()
    assert shown_assessed_at(at) == first
    record(at, "demo_1", "confirm_flag")
    record(at, "demo_1", "dismiss_flag")
    assert stored_at(db, "demo_1", 0) == stored_at(db, "demo_1", 1)
    assert as_display(stored_at(db, "demo_1")) == first


def test_switching_cases_and_back_keeps_the_same_assessed_at(env):
    at = open_page("demo_1")
    first = shown_assessed_at(at)
    at.radio[0].set_value("demo_3").run()
    at.radio[0].set_value("demo_1").run()
    assert shown_assessed_at(at) == first


def test_other_session_sees_the_same_assessed_at(env):
    at = open_page("demo_2")
    assert shown_assessed_at(open_page("demo_2")) == shown_assessed_at(at)


def test_fallback_has_its_own_assessed_at_and_retry_creates_a_new_one(env):
    fake, db, monkeypatch = env
    llm_on(monkeypatch)
    at = open_page("demo_1")
    fallback_at = shown_assessed_at(at)
    record(at, "demo_1", "dismiss_flag")                       # decided on the fallback
    fake.fail = False
    retry(at)
    new_at = shown_assessed_at(at)
    assert new_at != fallback_at and new_at > fallback_at
    record(at, "demo_1", "confirm_flag")                       # decided on the LLM result
    before, after = review_store.case_history(db, "demo_1")
    assert snapshot(before)["system_assessment"]["assessment_mode"] == "llm_fallback_offline"
    assert as_display(snapshot(before)["assessed_at"]) == fallback_at
    assert snapshot(after)["system_assessment"]["assessment_mode"] == "llm"
    assert as_display(snapshot(after)["assessed_at"]) == new_at


def test_reviewed_after_block_stores_the_new_assessments_time(env):
    fake, db, monkeypatch = env
    llm_on(monkeypatch)
    a = open_page("demo_4")
    old_at = shown_assessed_at(a)
    fake.fail = False
    retry(open_page("demo_4"))                                 # another session retries
    record(a, "demo_4", "dismiss_flag")                        # blocked: assessment changed
    assert review_store.case_history(db, "demo_4") == []       # nothing written
    new_at = shown_assessed_at(a)
    assert new_at != old_at
    record(a, "demo_4", "confirm_flag")                        # after reviewing the update
    [event] = review_store.case_history(db, "demo_4")
    assert as_display(snapshot(event)["assessed_at"]) == new_at


def test_identical_reassessment_records_the_time_the_analyst_saw(env):
    """Retry in another session while the LLM is still down produces an identical
    fallback (same fingerprint, so the submit is not blocked) with a later
    assessed_at; the decision keeps the time of the assessment this analyst saw."""
    fake, db, monkeypatch = env
    llm_on(monkeypatch)
    a = open_page("demo_1")
    seen_at = shown_assessed_at(a)
    retry(open_page("demo_1"))                                 # still failing: same content
    record(a, "demo_1", "refer_legal_review")
    [event] = review_store.case_history(db, "demo_1")
    assert as_display(snapshot(event)["assessed_at"]) == seen_at
    assert shown_assessed_at(open_page("demo_1")) != seen_at   # the cache did move on


# --- Decision Provenance rendering -------------------------------------------------------

def test_provenance_page_distinguishes_produced_from_recorded(env):
    _, db, _ = env
    at = open_page("demo_5")
    record(at, "demo_5", "refer_legal_review")
    [event] = review_store.case_history(db, "demo_5")
    prov = AppTest.from_file(PROV_PAGE, default_timeout=30).run()
    assert not prov.exception
    text = " ".join(str(e.value) for e in list(prov.markdown) + list(prov.caption))
    assert f"Assessment produced (UTC): {as_display(snapshot(event)['assessed_at'])}" in text
    assert f"Decision recorded (UTC): {as_display(event['recorded_at'])}" in text
    assert "Data source: Synthetic demo case · Reference: demo_cases:demo_5" in text
    assert ("Assessment produced is when the system generated the assessment the analyst "
            "reviewed; Decision recorded is when the analyst saved the decision.") in text
    assert "uspto" not in text.lower()
