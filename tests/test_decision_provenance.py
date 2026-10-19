"""Phase 3, Iteration 2: read-only Decision Provenance page.

Seeds a temporary review database with real recorded decisions (offline,
LLM via a fake model, and labelled fallback via a fake failing model) plus
one legacy Phase-1-shaped row whose snapshot lacks later provenance fields.
No network calls; the real reviews.db is never touched.
"""
import ast
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "pages" / "2_Decision_Provenance.py")
sys.path.insert(0, str(ROOT / "src"))

from signalsilence import review_store  # noqa: E402
from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

DEMO = {c.case_id: c for c in CANONICAL.values()}
NOT_RECORDED = "Not recorded at decision time"


def _page_function(name):
    """Load one top-level function from the page source without running Streamlit."""
    tree = ast.parse(Path(PAGE).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), PAGE, "exec"), namespace)
    return namespace[name]


# --- Derived outcome badge ------------------------------------------------------

@pytest.mark.parametrize("action, decision, expected", [
    ("escalate", "dismiss_flag", "Override down"),
    ("ignore/monitor", "confirm_flag", "Override up"),
    ("ignore/monitor", "refer_legal_review", "Override up"),
    ("review", "confirm_flag", "System deferred to analyst"),
    ("review", "dismiss_flag", "System deferred to analyst"),
    ("review", "refer_legal_review", "System deferred to analyst"),
    ("escalate", "confirm_flag", "Consistent"),
    ("escalate", "refer_legal_review", "Consistent"),
    ("ignore/monitor", "dismiss_flag", "Consistent"),
])
def test_outcome_badge_mapping(action, decision, expected):
    assert _page_function("outcome_badge")(action, decision) == expected


# --- Store: read-only listing ---------------------------------------------------

def test_list_events_is_read_only_and_never_creates_a_database(tmp_path):
    missing = tmp_path / "none.db"
    assert review_store.list_events(missing) == []
    assert not missing.exists()


def test_list_events_returns_all_cases_in_recording_order(tmp_path):
    db = tmp_path / "r.db"
    for cid, decision in [("demo_1", "confirm_flag"), ("demo_4", "dismiss_flag"), ("demo_1", "refer_legal_review")]:
        review_store.record_decision(db, DEMO[cid], triage(DEMO[cid], use_llm=False), decision,
                                     assessment_mode="offline")
    events = review_store.list_events(db)
    assert [(e["case_id"], e["analyst_decision"]) for e in events] == [
        ("demo_1", "confirm_flag"), ("demo_4", "dismiss_flag"), ("demo_1", "refer_legal_review")]
    assert [e["event_id"] for e in events] == sorted(e["event_id"] for e in events)


# --- Page (needs streamlit) -------------------------------------------------------

def _seed(db, monkeypatch):
    """Return {label: event_id} for a realistic mix of recorded decisions."""
    from test_llm_fallback import _reply, fake_anthropic
    ids = {}

    def rec(label, case_id, result, decision, note=None):
        ids[label] = review_store.record_decision(db, DEMO[case_id], result, decision, note,
                                                  assessment_mode=result.assessment_mode)

    rec("confirm_offline", "demo_1", triage(DEMO["demo_1"], use_llm=False), "confirm_flag", "Clear knock-off.")
    rec("override_down", "demo_1", triage(DEMO["demo_1"], use_llm=False), "dismiss_flag", "Licensed partner.")
    rec("override_up", "demo_5", triage(DEMO["demo_5"], use_llm=False), "refer_legal_review")
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic("RateLimitError"))
    rec("fallback", "demo_4", triage(DEMO["demo_4"], use_llm=True), "refer_legal_review", "LLM was down.")
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic(_reply(goods_adjacent=True)))
    llm = triage(DEMO["demo_2"], use_llm=True)
    llm.llm_model = "fake-model-2026"  # the fake client reports no model id
    rec("llm", "demo_2", llm, "dismiss_flag", "Different market.")
    # Legacy Phase-1-shaped row: no policy_version, free-text mode, snapshot
    # without prompt/model/fallback/mode keys.
    legacy_snapshot = {"case_inputs": {"protected_mark": "BATA", "candidate_mark": "BAATA LACES"},
                       "system_assessment": {"risk": "high", "action": "escalate",
                                             "invariant_notes": ["I2: strong similarity + adjacent goods -> HIGH (non-downgradable)"],
                                             "insight": "offline heuristic judgment",
                                             "context": {"goods_adjacent": True}}}
    with sqlite3.connect(db) as conn:
        cur = conn.execute(
            """INSERT INTO review_events (case_id, protected_mark, candidate_mark, system_risk,
               system_action, lexical_similarity, phonetic_similarity, assessment_mode,
               policy_version, system_snapshot, analyst_decision, analyst_note, recorded_at)
               VALUES ('demo_3','BATA','BAATA LACES','high','escalate',0.88,1.0,
                       'offline heuristic context judgment',NULL,?,'dismiss_flag',NULL,
                       '2026-07-01T10:00:00+00:00')""", (json.dumps(legacy_snapshot),))
        ids["legacy"] = cur.lastrowid
    return ids


@pytest.fixture
def page(tmp_path, monkeypatch):
    st = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    db = tmp_path / "reviews.db"
    ids = _seed(db, monkeypatch)
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    return at, db, ids


def text(at):
    parts = [e.value for e in list(at.markdown) + list(at.caption) + list(at.info)
             + list(at.title) + list(at.subheader)]
    return " ".join(str(p) for p in parts)


def table(at):
    return at.dataframe[0].value


def open_event(at, event_id, view=None):
    if view:
        at.radio(key="prov_filter").set_value(view).run()
    at.selectbox(key="prov_event").set_value(event_id).run()
    assert not at.exception


def test_default_filter_is_dismissals_and_escalations_only(page):
    at, _, _ = page
    assert at.radio(key="prov_filter").value == "Dismissals & Escalations"
    assert set(table(at)["Analyst decision"]) == {"Dismiss Flag", "Refer for Legal Review"}
    assert "Confirm Flag" not in set(table(at)["Analyst decision"])


def test_all_decisions_includes_confirm_flag(page):
    at, _, ids = page
    at.radio(key="prov_filter").set_value("All Decisions").run()
    df = table(at)
    assert "Confirm Flag" in set(df["Analyst decision"])
    assert len(df) == len(ids)                         # nothing permanently hidden
    assert list(df["Decision #"]) == sorted(ids.values(), reverse=True)  # most recently recorded event first


def test_list_columns_and_derived_badges(page):
    at, _, ids = page
    at.radio(key="prov_filter").set_value("All Decisions").run()
    df = table(at).set_index("Decision #")
    assert list(df.columns) == ["Decision recorded (UTC)", "Case", "Protected mark", "New filing",
                                "System risk", "System recommendation", "Analyst decision",
                                "Outcome (derived)"]
    assert df.loc[ids["override_down"], "Outcome (derived)"] == "Override down"
    assert df.loc[ids["override_up"], "Outcome (derived)"] == "Override up"
    assert df.loc[ids["fallback"], "Outcome (derived)"] == "System deferred to analyst"
    assert df.loc[ids["confirm_offline"], "Outcome (derived)"] == "Consistent"


def test_badge_is_described_as_derived(page):
    at, _, _ = page
    assert ("Outcome is derived when this page is viewed, from the recorded system recommendation "
            "and analyst decision. It was not captured at decision time.") in text(at)


def test_selected_decision_renders_stored_system_evidence(page):
    at, _, ids = page
    open_event(at, ids["override_down"])
    t = text(at)
    assert "Decision #%d: LULULEMON vs LULULEMMON" % ids["override_down"] in t
    assert ":red-background[**HIGH**]" in t and "Recommendation: :gray-background[Escalate]" in t
    assert "Lexical similarity: **0.98**" in t and "Phonetic similarity: **1.00**" in t
    assert "Goods commercially adjacent: True" in t
    assert "`I1: strong/near-identical mark + same class -> HIGH`" in t
    assert "**Insight:** offline heuristic judgment" in t
    assert "Dismiss Flag" in t and "Note: Licensed partner." in t
    assert "Decision recorded (UTC):" in t
    assert "Rules version: rules-v4" in t and "Assessment mode: `offline`" in t
    assert "Prompt version: None (offline assessment, no LLM used)" in t
    assert "Fallback: No fallback" in t
    assert "Applicant: Global Brand Holdings Ltd" in t     # recorded case inputs


def test_llm_and_fallback_provenance_as_stored(page):
    at, _, ids = page
    open_event(at, ids["llm"])
    t = text(at)
    assert "Assessment mode: `llm`" in t and "Prompt version: context-prompt-v2" in t
    assert "Model id: fake-model-2026" in t
    open_event(at, ids["fallback"])
    t = text(at)
    assert "Assessment mode: `llm_fallback_offline`" in t
    assert "Fallback: Yes: LLM unavailable (rate_limit); offline assessment used" in t


def test_missing_fields_show_not_recorded_and_are_not_backfilled(page):
    at, _, ids = page
    open_event(at, ids["legacy"])
    t = text(at)
    assert "Assessment mode: `offline heuristic context judgment`" in t   # shown as stored
    for field in ("Rules version", "Prompt version", "Model id", "Fallback", "Data source",
                  "Assessment produced (UTC)"):
        assert f"{field}: {NOT_RECORDED}" in t, field
    assert f"Added wording descriptive: {NOT_RECORDED}" in t
    assert "Note: No note entered" in t


def test_no_assessment_produced_time_is_invented(page):
    """Rows recorded without assessed_at (all seeded rows here) are never given one."""
    at, _, ids = page
    open_event(at, ids["confirm_offline"], view="All Decisions")
    assert f"Assessment produced (UTC): {NOT_RECORDED}" in text(at)


def test_full_snapshot_available(page):
    at, db, ids = page
    open_event(at, ids["llm"])
    assert "Full stored snapshot (audit view)" in [e.label for e in at.expander]
    [shown] = at.get("json")
    stored = next(e for e in review_store.list_events(db) if e["event_id"] == ids["llm"])
    assert json.loads(shown.proto.body) == json.loads(stored["system_snapshot"])


def test_page_is_read_only(page):
    at, db, ids = page
    before = (len(review_store.list_events(db)), hashlib.sha256(Path(db).read_bytes()).hexdigest())
    at.radio(key="prov_filter").set_value("All Decisions").run()
    for event_id in ids.values():
        open_event(at, event_id)
    after = (len(review_store.list_events(db)), hashlib.sha256(Path(db).read_bytes()).hexdigest())
    assert before == after
    assert at.get("button") == [] and at.text_area == [] and at.get("form") == []


def test_empty_database_shows_empty_state_and_creates_nothing(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    db = tmp_path / "absent.db"
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    assert "No decisions recorded yet" in text(at)
    assert not db.exists()


def test_public_demo_notice(page):
    at, _, _ = page
    assert ("Public demo: review history is temporary and may be shared across demo visitors. "
            "Do not enter confidential or personal information.") in text(at)


def test_no_chain_of_thought_claim(page):
    at, _, ids = page
    t = text(at)
    assert ("Decision Provenance preserves the evidence and system state associated with a decision. "
            "It does not expose hidden model reasoning or chain-of-thought.") in t
    open_event(at, ids["llm"])
    lowered = text(at).lower()
    assert lowered.count("chain-of-thought") == 1          # only the disclaimer
    for claim in ("model reasoning:", "reasoning trace", "why the model"):
        assert claim not in lowered


def test_no_uspto_claim_for_demo_records(page):
    at, _, ids = page
    at.radio(key="prov_filter").set_value("All Decisions").run()
    for event_id in ids.values():
        open_event(at, event_id)
        assert "uspto" not in text(at).lower()
        assert f"Data source: {NOT_RECORDED}" in text(at)
