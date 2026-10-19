"""Phase 2.2: explicit per-case "Retry LLM assessment" for fallback results.

The Analyst Review cache (st.cache_data) is process-wide, shared by all
sessions, and never expires, so a temporary LLM failure would otherwise stick
until restart. Fallbacks are never retried automatically; the retry button
clears only the selected case's entry. The model is a fake that can be
switched between failing and succeeding and counts calls per case.
"""
import json
import re
import sys
import types
from collections import Counter
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
import streamlit as st  # noqa: E402
from streamlit.testing.v1 import AppTest  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402

PAGE = str(Path(__file__).resolve().parents[1] / "views" / "analyst_review.py")
FALLBACK = "llm_fallback_offline"


class FakeLLM:
    """Fake `anthropic` module. `.fail` toggles failure; `.calls` counts per candidate mark."""

    def __init__(self):
        self.fail = True
        self.calls = Counter()
        self.module = types.ModuleType("anthropic")
        self.module.AnthropicError = type("AnthropicError", (Exception,), {})
        self.module.RateLimitError = type("RateLimitError", (self.module.AnthropicError,), {})
        fake = self

        class Client:
            @property
            def messages(self):
                return self

            def create(self, **kwargs):
                prompt = kwargs["messages"][0]["content"]
                fake.calls[re.search(r"candidate_mark: (.+)", prompt).group(1)] += 1
                if fake.fail:
                    raise fake.module.RateLimitError()
                text = json.dumps({"goods_adjacent": True, "added_wording_descriptive": False,
                                   "behavioral_signal": False, "rationale": "fake ok"})
                return types.SimpleNamespace(
                    model="fake-model-2026",
                    content=[types.SimpleNamespace(type="text", text=text)])

        self.module.Anthropic = Client

    @property
    def total(self):
        return sum(self.calls.values())


@pytest.fixture
def llm(tmp_path, monkeypatch):
    fake = FakeLLM()
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(tmp_path / "reviews.db"))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setitem(sys.modules, "anthropic", fake.module)
    st.cache_data.clear()
    yield fake
    st.cache_data.clear()


def open_page():
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    return at


def mode(at):
    caption = next(str(c.value) for c in at.caption if "Produced by" in str(c.value))
    return FALLBACK if FALLBACK in caption else "llm" if "llm context judgment" in caption else "offline"


def retry_buttons(at):
    return [b for b in at.button if b.label == "Retry LLM assessment"]


def record(at, case_id, decision):
    at.radio(key=f"decision_{case_id}").set_value(decision)
    next(b for b in at.button if b.label == "Record decision").click().run()
    assert not at.exception


def test_no_automatic_retry_after_recovery(llm):
    at = open_page()
    assert mode(at) == FALLBACK and llm.total == 5   # one attempt per queued case
    llm.fail = False
    at.run()
    at.run()
    assert mode(at) == FALLBACK and llm.total == 5   # recovery alone re-calls nothing
    assert mode(open_page()) == FALLBACK and llm.total == 5


def test_retry_button_only_for_fallback(llm, monkeypatch):
    at = open_page()
    assert len(retry_buttons(at)) == 1
    llm.fail = False
    retry_buttons(at)[0].click().run()
    assert mode(at) == "llm" and retry_buttons(at) == []     # successful LLM: no button
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    offline = open_page()
    assert mode(offline) == "offline" and retry_buttons(offline) == []


def test_retry_makes_one_call_for_selected_case_only(llm):
    at = open_page()
    llm.fail = False
    before = Counter(llm.calls)
    retry_buttons(at)[0].click().run()                    # demo_1 is selected by default
    assert not at.exception
    assert llm.total == 6
    assert llm.calls - before == Counter({"LULULEMMON": 1})
    assert mode(at) == "llm"
    assert any("Retry succeeded" in str(s.value) for s in at.success)
    at.radio[0].set_value("demo_2").run()                 # other cases stay cached
    assert mode(at) == FALLBACK and llm.total == 6


def test_failed_retry_remains_fallback(llm):
    at = open_page()
    retry_buttons(at)[0].click().run()                    # still failing
    assert not at.exception
    assert llm.total == 6 and mode(at) == FALLBACK
    assert any("Retry failed (rate_limit)" in str(w.value) for w in at.warning)
    assert len(retry_buttons(at)) == 1


def test_successful_retry_is_shared_with_other_sessions(llm):
    first = open_page()
    llm.fail = False
    retry_buttons(first)[0].click().run()
    other = open_page()                                   # a separate session
    assert mode(other) == "llm" and llm.total == 6


def test_history_keeps_fallback_snapshot_then_records_llm_snapshot(llm, tmp_path):
    at = open_page()
    record(at, "demo_1", "dismiss_flag")                  # decided on the fallback
    llm.fail = False
    retry_buttons(at)[0].click().run()
    record(at, "demo_1", "confirm_flag")                  # decided on the LLM result
    before, after = review_store.case_history(tmp_path / "reviews.db", "demo_1")
    snap_before = json.loads(before["system_snapshot"])["system_assessment"]
    snap_after = json.loads(after["system_snapshot"])["system_assessment"]
    assert before["assessment_mode"] == FALLBACK and snap_before["fallback_reason"] == "rate_limit"
    assert after["assessment_mode"] == "llm" and snap_after["llm_model"] == "fake-model-2026"
    assert before["analyst_decision"] == "dismiss_flag"   # earlier event untouched


def test_offline_mode_unchanged_and_never_calls_model(llm, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    at = open_page()
    assert mode(at) == "offline" and llm.total == 0 and retry_buttons(at) == []
    record(at, "demo_1", "confirm_flag")
    [event] = review_store.case_history(review_store.default_db_path(), "demo_1")
    assert event["assessment_mode"] == "offline" and event["system_risk"] == "high"
