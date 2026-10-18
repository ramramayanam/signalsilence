"""UI smoke tests for the analyst review page (Streamlit AppTest).

Skipped when streamlit is not installed. Each test points the page at a
temporary database via SIGNALSILENCE_REVIEW_DB and forces offline mode.
"""
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[1] / "pages" / "1_Analyst_Review.py")


@pytest.fixture
def page(tmp_path, monkeypatch):
    db = tmp_path / "reviews.db"
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(db))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    return at, db


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
