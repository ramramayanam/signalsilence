"""Phase 2.3: submit-time assessment consistency on the Analyst Review page.

The assessment cache is shared across sessions, so another session can
replace a case's assessment (e.g. via Retry LLM assessment) between what
analyst A saw and A's submit. A decision is recorded only if the
fingerprint of the assessment A was shown still matches the current one;
otherwise nothing is written and A is asked to review the update.
"""
import ast
import hashlib
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = str(ROOT / "pages" / "1_Analyst_Review.py")
sys.path.insert(0, str(ROOT / "src"))

from signalsilence import review_store  # noqa: E402
from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

CHANGED = ("The system assessment changed since you reviewed this case. Please review "
           "the updated assessment below and record your decision again.")


def _page_fingerprint_function():
    """Load only assessment_fingerprint() from the page source (no Streamlit run)."""
    tree = ast.parse(Path(PAGE).read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "assessment_fingerprint")
    namespace = {"json": json, "hashlib": hashlib, "asdict": asdict}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), PAGE, "exec"), namespace)
    return namespace["assessment_fingerprint"]


def test_fingerprint_is_stable_and_content_sensitive():
    fingerprint = _page_fingerprint_function()
    case = next(iter(CANONICAL.values()))
    a, b = triage(case, use_llm=False), triage(case, use_llm=False)
    assert a is not b and fingerprint(a) == fingerprint(b)          # identical content
    assert len(fingerprint(a)) == 64                                 # sha256 hex
    assert fingerprint(replace(a, action=type(a.action)("review"))) != fingerprint(a)
    assert fingerprint(replace(a, assessment_mode="llm_fallback_offline")) != fingerprint(a)
    assert fingerprint(replace(a, invariant_notes=a.invariant_notes + ["x"])) != fingerprint(a)


# --- Page tests (need streamlit; skipped without it via the env fixture) --------------

st = AppTest = None  # bound by the env fixture once streamlit is known to be importable

@pytest.fixture
def env(tmp_path, monkeypatch):
    global st, AppTest
    st = pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    from test_review_retry import FakeLLM
    db = tmp_path / "reviews.db"
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    fake = FakeLLM()
    monkeypatch.setitem(sys.modules, "anthropic", fake.module)
    st.cache_data.clear()
    yield fake, db
    st.cache_data.clear()


def open_page(case_id="demo_1"):
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    if case_id != "demo_1":
        at.radio[0].set_value(case_id).run()
    assert not at.exception
    return at


def submit(at, case_id, decision, note=None):
    at.radio(key=f"decision_{case_id}").set_value(decision)
    if note is not None:
        at.text_area[0].set_value(note)
    next(b for b in at.button if b.label == "Record decision").click().run()
    assert not at.exception


def retry_in_other_session(case_id):
    other = open_page(case_id)
    next(b for b in other.button if b.label == "Retry LLM assessment").click().run()
    assert not other.exception
    return other


def warned(at):
    return any(CHANGED in str(w.value) for w in at.warning)


def badges(at):
    return " ".join(str(m.value) for m in at.markdown if "-background[**" in str(m.value))


def test_race_blocks_submit_after_other_session_retry(env):
    fake, db = env
    a = open_page("demo_1")                      # A sees the fallback
    fake.fail = False
    retry_in_other_session("demo_1")             # B replaces it with an LLM assessment
    submit(a, "demo_1", "refer_legal_review", note="Counsel should look at this.")
    assert review_store.case_history(db, "demo_1") == []       # nothing written
    assert warned(a)
    caption = next(str(c.value) for c in a.caption if "Produced by" in str(c.value))
    assert "llm context judgment" in caption                   # A now sees the update
    assert a.text_area[0].value == "Counsel should look at this."  # note kept


def test_low_to_high_change_does_not_record_dismiss_against_new_assessment(env):
    fake, db = env
    a = open_page("demo_4")
    assert ":green-background[**LOW**]" in badges(a)          # fallback LOW / REVIEW
    fake.fail = False
    retry_in_other_session("demo_4")                           # becomes HIGH / ESCALATE
    submit(a, "demo_4", "dismiss_flag")
    assert review_store.case_history(db, "demo_4") == []
    assert warned(a) and ":red-background[**HIGH**]" in badges(a)


def test_resubmit_after_review_records_exactly_one_event_with_new_snapshot(env):
    fake, db = env
    a = open_page("demo_4")
    fake.fail = False
    retry_in_other_session("demo_4")
    submit(a, "demo_4", "dismiss_flag")                        # blocked
    submit(a, "demo_4", "confirm_flag")                        # after reviewing the update
    [event] = review_store.case_history(db, "demo_4")
    snap = json.loads(event["system_snapshot"])["system_assessment"]
    assert event["analyst_decision"] == "confirm_flag"
    assert (event["assessment_mode"], event["system_risk"], event["system_action"]) == \
        ("llm", "high", "escalate")
    assert snap["llm_model"] == "fake-model-2026"
    assert not warned(a)


def test_no_false_alarm_when_assessment_unchanged(env):
    fake, db = env
    a = open_page("demo_1")
    a.run()                                                    # plain reruns
    open_page("demo_1")                                        # another session just viewing
    submit(a, "demo_1", "confirm_flag")
    assert len(review_store.case_history(db, "demo_1")) == 1 and not warned(a)


def test_offline_mode_records_normally(env, monkeypatch):
    fake, db = env
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    a = open_page("demo_1")
    open_page("demo_1").run()                                  # other offline session
    submit(a, "demo_1", "confirm_flag")
    submit(a, "demo_1", "dismiss_flag")
    assert [e["analyst_decision"] for e in review_store.case_history(db, "demo_1")] == \
        ["confirm_flag", "dismiss_flag"]
    assert not warned(a) and fake.total == 0


def test_switching_cases_does_not_create_false_mismatch(env):
    fake, db = env
    a = open_page("demo_1")
    a.radio[0].set_value("demo_3").run()
    a.radio[0].set_value("demo_1").run()
    submit(a, "demo_1", "confirm_flag")
    a.radio[0].set_value("demo_3").run()
    submit(a, "demo_3", "refer_legal_review")
    assert len(review_store.case_history(db, "demo_1")) == 1
    assert len(review_store.case_history(db, "demo_3")) == 1
    assert not warned(a)


def test_switching_away_and_back_after_change_shows_update_without_blocking(env):
    """If the change happened while A was on another case, A sees it on return."""
    fake, db = env
    a = open_page("demo_1")
    a.radio[0].set_value("demo_2").run()
    fake.fail = False
    retry_in_other_session("demo_1")
    a.radio[0].set_value("demo_1").run()                       # A is now shown the update
    submit(a, "demo_1", "confirm_flag")
    [event] = review_store.case_history(db, "demo_1")
    assert event["assessment_mode"] == "llm" and not warned(a)


def test_blocked_submit_preserves_earlier_history(env):
    fake, db = env
    a = open_page("demo_1")
    submit(a, "demo_1", "dismiss_flag", note="first look")     # recorded on the fallback
    [first] = review_store.case_history(db, "demo_1")
    fake.fail = False
    retry_in_other_session("demo_1")
    submit(a, "demo_1", "confirm_flag")                        # blocked
    assert review_store.case_history(db, "demo_1") == [first]  # unchanged, nothing added
    assert warned(a)
