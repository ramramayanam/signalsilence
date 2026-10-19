"""UI smoke tests for the analyst review page (Streamlit AppTest).

Skipped when streamlit is not installed. Each test points the page at a
temporary database via SIGNALSILENCE_REVIEW_DB and forces offline mode.
"""
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[1] / "views" / "analyst_review.py")


@pytest.fixture
def page(tmp_path, monkeypatch):
    db = tmp_path / "reviews.db"
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    return at, db


def record_button(at):
    return next(b for b in at.button if b.label == "Record decision")


def _text(at):
    return " ".join(str(e.value) for e in
                    list(at.markdown) + list(at.info) + list(at.caption) + list(at.subheader))


def test_queue_lists_five_demo_cases_unreviewed(page):
    at, _ = page
    queue = at.radio[0]
    assert queue.options == [
        "**LULULEMON** vs **LULULEMMON**", "**NIKE** vs **NIKKE**",
        "**BATA** vs **BAATA LACES**", "**LULULEMON** vs **LULULIME**",
        "**PHISH** vs **FISH**"]
    assert "5 cases · 3 high · 0 review · 2 low · 0 reviewed" in _text(at)
    assert ":gray-background[Unreviewed]" in _text(at)


def test_page_separates_recommendation_from_decision(page):
    at, _ = page
    text = _text(at)
    assert "SignalSilence recommends. The analyst decides." in text
    assert "System assessment" in text and "Analyst decision" in text
    assert ":gray-background[Escalate]" in text  # system styling, never analyst blue
    assert at.radio(key="decision_demo_1").options == [
        "Confirm Flag", "Dismiss Flag", "Refer for Legal Review"]
    assert "Not available" in text  # missing source metadata is not fabricated


def test_recording_a_decision_persists_and_updates_status(page):
    at, db = page
    at.radio[0].set_value("demo_3").run()
    at.radio(key="decision_demo_3").set_value("refer_legal_review")
    at.text_area[0].set_value("Shoelaces are adjacent to footwear.")
    at.button[0].click().run()
    assert not at.exception
    [event] = review_store.case_history(db, "demo_3")
    assert event["analyst_decision"] == "refer_legal_review"
    assert event["analyst_note"] == "Shoelaces are adjacent to footwear."
    assert event["system_risk"] == "high" and event["system_action"] == "escalate"
    text = _text(at)
    assert ":blue-background[**Referred for Legal Review**]" in text
    assert "1 reviewed" in text
    assert at.dataframe[0].value["Analyst decision"].tolist() == ["Refer for Legal Review"]


def test_submitting_without_a_decision_records_nothing(page):
    at, db = page
    at.button[0].click().run()
    assert any("Choose a decision" in str(w.value) for w in at.warning)
    assert review_store.case_history(db, "demo_1") == []


def test_llm_fallback_is_shown_and_recorded_as_fallback(tmp_path, monkeypatch):
    """With LLM mode on but the API failing, the page must say so and record
    llm_fallback_offline, never a successful LLM assessment."""
    import streamlit as st
    from test_llm_fallback import fake_anthropic

    db = tmp_path / "reviews.db"
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic("RateLimitError"))
    st.cache_data.clear()  # assess() is cached per process
    try:
        at = AppTest.from_file(PAGE, default_timeout=30).run()
        assert not at.exception
        at.radio[0].set_value("demo_4").run()
        assert any("LLM unavailable (rate_limit)" in str(w.value) for w in at.warning)
        assert "llm_fallback_offline" in _text(at)
        at.radio(key="decision_demo_4").set_value("dismiss_flag")
        record_button(at).click().run()
        assert not at.exception
    finally:
        st.cache_data.clear()
    [event] = review_store.case_history(db, "demo_4")
    assert event["assessment_mode"] == "llm_fallback_offline"
    assert event["system_risk"] == "low" and event["system_action"] == "review"
    snap = json.loads(event["system_snapshot"])["system_assessment"]
    assert (snap["assessment_mode"], snap["fallback_reason"]) == ("llm_fallback_offline", "rate_limit")


def test_offline_decision_is_recorded_as_offline(page):
    at, db = page
    at.radio(key="decision_demo_1").set_value("confirm_flag")
    at.button[0].click().run()
    [event] = review_store.case_history(db, "demo_1")
    assert event["assessment_mode"] == "offline"


def test_llm_assessment_records_prompt_version_and_model(tmp_path, monkeypatch):
    """A successful (fake) LLM assessment shows and stores its provenance."""
    import types
    import streamlit as st

    class Client:
        @property
        def messages(self):
            return self

        def create(self, **kwargs):
            text = json.dumps({"goods_adjacent": True, "added_wording_descriptive": False,
                               "behavioral_signal": False, "plausible_affiliation": True,
                               "rationale": "fake model rationale"})
            return types.SimpleNamespace(model="fake-model-2026",
                                         content=[types.SimpleNamespace(type="text", text=text)])

    fake = types.ModuleType("anthropic")
    fake.AnthropicError = type("AnthropicError", (Exception,), {})
    fake.Anthropic = Client
    db = tmp_path / "reviews.db"
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    st.cache_data.clear()
    try:
        at = AppTest.from_file(PAGE, default_timeout=30).run()
        assert not at.exception
        assert "llm context judgment: fake-model-2026, context-prompt-v2" in _text(at)
        at.radio(key="decision_demo_1").set_value("confirm_flag")
        at.button[0].click().run()
        assert not at.exception
    finally:
        st.cache_data.clear()
    [event] = review_store.case_history(db, "demo_1")
    snap = json.loads(event["system_snapshot"])["system_assessment"]
    assert event["assessment_mode"] == "llm"
    assert (snap["llm_model"], snap["prompt_version"]) == ("fake-model-2026", "context-prompt-v2")
    assert snap["context"]["plausible_affiliation"] is False


def test_every_case_switch_is_honored(page):
    """Regression: an unkeyed queue radio with a changing `index` got a new widget
    identity after each switch, so every other click was silently dropped."""
    at, _ = page
    for case_id in ["demo_3", "demo_1", "demo_5", "demo_2", "demo_1", "demo_4"]:
        at.radio[0].set_value(case_id).run()
        assert at.radio[0].value == case_id
        assert f"case {case_id}" in _text(at)
