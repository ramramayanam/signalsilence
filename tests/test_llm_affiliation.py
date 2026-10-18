"""Phase 2.1 (rules-v4, context-prompt-v2): LLM mode cannot establish affiliation.

The context prompt no longer asks about affiliation, any plausible_affiliation
key the model returns is ignored, and every LLM attempt records the prompt
version and the model. All model calls are faked; nothing reaches the network.
"""
import json
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402
from signalsilence.policy import POLICY_VERSION, classify  # noqa: E402
from signalsilence.schema import Case, ContextJudgment, Risk, SimilarityScores  # noqa: E402
from signalsilence.triage import (  # noqa: E402
    CONTEXT_PROMPT_VERSION, DEFAULT_CONTEXT_MODEL, render_context_prompt, triage)

KNOCKOFF = Case("p21_knockoff", "LULULEMON", "LULULEMMON", "025", "yoga pants",
                "Lululemon Knockoffs LLC", "corporation", True)
GENUINE_NAME = Case("p21_canada", "LULULEMON", "LULULEMMON", "025", "yoga pants",
                    "Lululemon Athletica Canada Inc", "corporation", True)


def reply(**facts):
    base = {"goods_adjacent": True, "added_wording_descriptive": False,
            "behavioral_signal": False, "rationale": "model rationale"}
    base.update(facts)
    return json.dumps(base)


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a fake `anthropic`; returns the list of create() calls made."""
    calls = []

    def install(text, reported_model=None):
        class Client:
            @property
            def messages(self):
                return self

            def create(self, **kwargs):
                calls.append(kwargs)
                return types.SimpleNamespace(
                    model=reported_model,
                    content=[types.SimpleNamespace(type="text", text=text)])

        mod = types.ModuleType("anthropic")
        mod.AnthropicError = type("AnthropicError", (Exception,), {})
        mod.Anthropic = Client
        monkeypatch.setitem(sys.modules, "anthropic", mod)
        return calls
    return install


# --- Prompt ------------------------------------------------------------------

def test_rendered_prompt_no_longer_asks_about_affiliation():
    prompt = render_context_prompt(KNOCKOFF)
    assert "plausible_affiliation" not in prompt
    assert "Judge ONLY the three context questions" in prompt
    assert ("An applicant name that resembles or contains the protected mark is not "
            "evidence of any relationship to the mark owner.") in prompt
    for key in ("goods_adjacent", "added_wording_descriptive", "behavioral_signal"):
        assert key in prompt


def test_rendered_prompt_labels_applicant_entity_type():
    prompt = render_context_prompt(KNOCKOFF)
    assert "applicant_entity_type: corporation" in prompt
    assert "owner_entity_type" not in prompt
    assert KNOCKOFF.owner_entity_type == "corporation"  # schema field is unchanged


def test_prompt_sent_to_model_is_the_rendered_prompt(fake_llm):
    calls = fake_llm(reply())
    triage(KNOCKOFF, use_llm=True)
    [call] = calls
    assert call["messages"] == [{"role": "user", "content": render_context_prompt(KNOCKOFF)}]


# --- Parsing -----------------------------------------------------------------

def test_reply_without_affiliation_key_is_a_valid_llm_judgment(fake_llm):
    fake_llm(reply())
    r = triage(KNOCKOFF, use_llm=True)
    assert r.assessment_mode == "llm" and r.fallback_reason is None
    assert r.context.plausible_affiliation is False


@pytest.mark.parametrize("value", [True, "true", "maybe", None])
def test_unexpected_affiliation_key_is_ignored(fake_llm, value):
    fake_llm(reply(plausible_affiliation=value))
    r = triage(KNOCKOFF, use_llm=True)
    assert r.assessment_mode == "llm"  # extra key never makes the reply malformed
    assert r.context.plausible_affiliation is False


@pytest.mark.parametrize("key", ["goods_adjacent", "added_wording_descriptive", "behavioral_signal"])
def test_remaining_facts_keep_strict_parsing(fake_llm, key):
    fake_llm(reply(**{key: "false"}))
    assert getattr(triage(KNOCKOFF, use_llm=True).context, key) is False
    fake_llm(reply(**{key: "maybe"}))
    r = triage(KNOCKOFF, use_llm=True)
    assert (r.assessment_mode, r.fallback_reason) == ("llm_fallback_offline", "malformed_response")
    fake_llm(json.dumps({k: v for k, v in json.loads(reply()).items() if k != key}))
    assert triage(KNOCKOFF, use_llm=True).fallback_reason == "malformed_response"


# --- Decisions ---------------------------------------------------------------

@pytest.mark.parametrize("case", [KNOCKOFF, GENUINE_NAME], ids=["knockoff", "athletica-canada"])
def test_llm_affiliation_claim_does_not_downgrade(fake_llm, case):
    """Even a genuine-sounding affiliate escalates: no explicit evidence exists,
    so the analyst decides (this is the intended rules-v4 behavior)."""
    fake_llm(reply(plausible_affiliation=True))
    r = triage(case, use_llm=True)
    assert (r.risk.value, r.action.value) == ("high", "escalate")
    assert r.invariant_notes[0].startswith("I1")
    assert not any(n.startswith("I4") for n in r.invariant_notes)


def test_i4_policy_rule_itself_is_intact():
    """Dormant, not deleted: given explicit affiliation, I4 still applies."""
    ctx = ContextJudgment(goods_adjacent=True, added_wording_descriptive=False,
                          plausible_affiliation=True, behavioral_signal=False)
    risk, action, notes = classify(SimilarityScores(lexical=0.95, phonetic=1.0), ctx, same_class=True)
    assert risk == Risk.REVIEW and notes[0].startswith("I4")
    assert POLICY_VERSION == "rules-v4"


# --- Provenance ----------------------------------------------------------------

def test_prompt_version_and_reported_model_recorded(fake_llm, monkeypatch):
    monkeypatch.delenv("SIGNALSILENCE_MODEL", raising=False)
    calls = fake_llm(reply(), reported_model="claude-sonnet-4-6-20260115")
    r = triage(KNOCKOFF, use_llm=True)
    assert calls[0]["model"] == DEFAULT_CONTEXT_MODEL
    assert r.prompt_version == CONTEXT_PROMPT_VERSION == "context-prompt-v2"
    assert r.llm_model == "claude-sonnet-4-6-20260115"  # what the API says it used


def test_requested_model_recorded_when_response_has_none(fake_llm, monkeypatch):
    monkeypatch.setenv("SIGNALSILENCE_MODEL", "configured-model-id")
    calls = fake_llm(reply(), reported_model=None)
    r = triage(KNOCKOFF, use_llm=True)
    assert calls[0]["model"] == "configured-model-id"
    assert r.llm_model == "configured-model-id"


def test_fallback_records_attempt_without_claiming_success(monkeypatch):
    monkeypatch.setenv("SIGNALSILENCE_MODEL", "configured-model-id")
    monkeypatch.setitem(sys.modules, "anthropic", None)  # package missing
    r = triage(KNOCKOFF, use_llm=True)
    assert (r.assessment_mode, r.fallback_reason) == ("llm_fallback_offline", "package_missing")
    assert (r.prompt_version, r.llm_model) == ("context-prompt-v2", "configured-model-id")
    assert "LLM unavailable" in r.context.rationale


def test_offline_mode_has_no_llm_provenance():
    r = triage(KNOCKOFF, use_llm=False)
    assert (r.assessment_mode, r.prompt_version, r.llm_model) == ("offline", None, None)
    assert (r.risk.value, r.action.value) == ("high", "escalate")


def test_decision_snapshot_preserves_prompt_version_and_model(fake_llm, tmp_path):
    fake_llm(reply(plausible_affiliation=True), reported_model="claude-sonnet-4-6-20260115")
    r = triage(KNOCKOFF, use_llm=True)
    db = tmp_path / "reviews.db"
    review_store.record_decision(db, KNOCKOFF, r, "refer_legal_review",
                                 assessment_mode=r.assessment_mode)
    [event] = review_store.case_history(db, KNOCKOFF.case_id)
    snap = json.loads(event["system_snapshot"])
    assert event["assessment_mode"] == "llm" and event["policy_version"] == "rules-v4"
    assert snap["system_assessment"]["prompt_version"] == "context-prompt-v2"
    assert snap["system_assessment"]["llm_model"] == "claude-sonnet-4-6-20260115"
    assert snap["system_assessment"]["context"]["plausible_affiliation"] is False
