"""D4: LLM/API failures degrade to a labeled offline assessment, never crash.

No network: the `anthropic` module is replaced by a fake whose exception
classes mirror the SDK hierarchy, or (where the SDK is installed) the real
exception classes are raised from a fake client.
"""
import json
import sys
import types
from dataclasses import asdict
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402
from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.schema import Case  # noqa: E402
from signalsilence.triage import MODE_FALLBACK, MODE_LLM, MODE_OFFLINE, triage  # noqa: E402

DEMO = {c.case_id: c for c in CANONICAL.values()}
SECRET = "sk-ant-api03-SECRET-TOKEN"
# Offline I6 case: moderate similarity (lex 0.84) + same class -> REVIEW / REVIEW.
REVIEW_CASE = Case("t_review", "LULULEMON", "LULUNOVA", "025", "running shorts",
                   "Peak Motion Labs LLC", "corporation", True)


def _reply(**facts):
    base = {"goods_adjacent": False, "added_wording_descriptive": False,
            "plausible_affiliation": False, "behavioral_signal": False,
            "rationale": "model rationale"}
    base.update(facts)
    return json.dumps(base)


def fake_anthropic(outcome):
    """Fake SDK module. outcome: exception class name to raise, or reply text."""
    mod = types.ModuleType("anthropic")
    mod.AnthropicError = type("AnthropicError", (Exception,), {})
    mod.APIError = type("APIError", (mod.AnthropicError,), {})
    mod.APIStatusError = type("APIStatusError", (mod.APIError,), {})
    mod.APIConnectionError = type("APIConnectionError", (mod.APIError,), {})
    mod.APITimeoutError = type("APITimeoutError", (mod.APIConnectionError,), {})
    for name in ("AuthenticationError", "PermissionDeniedError", "RateLimitError"):
        setattr(mod, name, type(name, (mod.APIStatusError,), {}))

    class Client:
        @property
        def messages(self):
            return self

        def create(self, **kwargs):
            if outcome in vars(mod) or outcome == "TypeError":
                exc = TypeError if outcome == "TypeError" else getattr(mod, outcome)
                raise exc(f"request failed with key {SECRET}")
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(type="text", text=outcome)])

    mod.Anthropic = Client
    return mod


@pytest.fixture
def llm(monkeypatch):
    def install(outcome):
        monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic(outcome))
    return install


# --- Boolean parsing ---------------------------------------------------------

def test_string_false_parses_as_false(llm):
    llm(_reply(goods_adjacent="false", added_wording_descriptive="FALSE",
               plausible_affiliation=" False ", behavioral_signal="false"))
    r = triage(DEMO["demo_4"], use_llm=True)
    assert r.assessment_mode == MODE_LLM
    ctx = r.context
    assert (ctx.goods_adjacent, ctx.added_wording_descriptive,
            ctx.plausible_affiliation, ctx.behavioral_signal) == (False, False, False, False)
    assert (r.risk.value, r.action.value) == ("low", "ignore/monitor")  # not the old all-True HIGH


def test_string_true_parses_as_true(llm):
    llm(_reply(goods_adjacent="true", added_wording_descriptive="True"))
    r = triage(DEMO["demo_4"], use_llm=True)
    assert r.assessment_mode == MODE_LLM
    assert r.context.goods_adjacent is True and r.context.added_wording_descriptive is True
    assert r.context.plausible_affiliation is False


def test_json_booleans_are_a_normal_llm_judgment(llm):
    llm(_reply(goods_adjacent=True))
    r = triage(DEMO["demo_4"], use_llm=True)
    assert r.assessment_mode == MODE_LLM and r.fallback_reason is None
    assert r.context.rationale == "model rationale"
    assert not any("LLM fallback" in n for n in r.invariant_notes)


@pytest.mark.parametrize("reply", [
    _reply(goods_adjacent="maybe"),
    _reply(goods_adjacent=1),
    _reply(goods_adjacent=None),
    _reply(behavioral_signal="yes"),
    json.dumps({"goods_adjacent": False}),            # missing keys
    json.dumps([True, False, False, False]),          # not an object
    "Probably adjacent goods, high risk.",            # not JSON
    "",                                               # empty
], ids=["maybe", "number", "null", "yes", "missing-keys", "list", "prose", "empty"])
def test_malformed_response_triggers_labeled_fallback(llm, reply):
    llm(reply)
    r = triage(DEMO["demo_4"], use_llm=True)
    assert r.assessment_mode == MODE_FALLBACK
    assert r.fallback_reason == "malformed_response"


# --- Transport / API failures ------------------------------------------------

@pytest.mark.parametrize("error, category", [
    ("AuthenticationError", "authentication"),
    ("PermissionDeniedError", "authentication"),
    ("APIConnectionError", "connection"),
    ("APITimeoutError", "timeout"),
    ("RateLimitError", "rate_limit"),
    ("APIStatusError", "api_error"),
    ("TypeError", "unexpected_error"),  # what the SDK raises when no API key resolves
])
def test_api_failures_fall_back_without_crashing(llm, error, category):
    llm(error)
    r = triage(DEMO["demo_4"], use_llm=True)
    assert r.assessment_mode == MODE_FALLBACK
    assert r.fallback_reason == category


def test_missing_anthropic_package_falls_back(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)  # makes `import anthropic` fail
    r = triage(DEMO["demo_4"], use_llm=True)
    assert r.assessment_mode == MODE_FALLBACK
    assert r.fallback_reason == "package_missing"


def test_real_sdk_exception_classes_are_categorized(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    if not hasattr(anthropic, "RateLimitError"):
        pytest.skip("real anthropic SDK not available")

    def raising(cls):
        class Client:
            @property
            def messages(self):
                return self

            def create(self, **kwargs):
                raise cls.__new__(cls)  # real class, no HTTP objects needed
        return Client

    for name, category in [("RateLimitError", "rate_limit"),
                           ("AuthenticationError", "authentication"),
                           ("APIConnectionError", "connection"),
                           ("APITimeoutError", "timeout"),
                           ("InternalServerError", "api_error")]:
        monkeypatch.setattr(anthropic, "Anthropic", raising(getattr(anthropic, name)))
        r = triage(DEMO["demo_4"], use_llm=True)
        assert (r.assessment_mode, r.fallback_reason) == (MODE_FALLBACK, category), name


def test_failure_details_do_not_leak_secrets(llm):
    llm("AuthenticationError")  # exception message contains SECRET
    r = triage(DEMO["demo_4"], use_llm=True)
    assert SECRET not in json.dumps(asdict(r), default=str)


# --- Fallback safety behavior ----------------------------------------------

def test_fallback_from_low_monitor_raises_action_to_review_only(llm):
    offline = triage(DEMO["demo_4"], use_llm=False)
    assert (offline.risk.value, offline.action.value) == ("low", "ignore/monitor")
    llm("RateLimitError")
    r = triage(DEMO["demo_4"], use_llm=True)
    assert (r.risk.value, r.action.value) == ("low", "review")
    assert r.invariant_notes[:-1] == offline.invariant_notes
    assert "action raised MONITOR -> REVIEW because the LLM was unavailable" in r.invariant_notes[-1]
    assert r.context.rationale == "offline heuristic judgment (LLM unavailable: rate_limit)"
    assert r.scores == offline.scores
    facts = ("goods_adjacent", "added_wording_descriptive",
             "plausible_affiliation", "behavioral_signal")
    assert [getattr(r.context, f) for f in facts] == [getattr(offline.context, f) for f in facts]


@pytest.mark.parametrize("case, expected", [
    (DEMO["demo_1"], ("high", "escalate")),
    (REVIEW_CASE, ("review", "review")),
], ids=["escalate", "review"])
def test_fallback_never_lowers_review_or_escalate(llm, case, expected):
    assert (triage(case, use_llm=False).risk.value,
            triage(case, use_llm=False).action.value) == expected
    llm("APIConnectionError")
    r = triage(case, use_llm=True)
    assert (r.risk.value, r.action.value) == expected
    assert r.invariant_notes[-1].endswith("offline assessment used; action unchanged")


def test_offline_mode_is_unchanged_and_labeled_offline():
    r = triage(DEMO["demo_4"], use_llm=False)
    assert (r.assessment_mode, r.fallback_reason) == (MODE_OFFLINE, None)
    assert r.context.rationale == "offline heuristic judgment"
    assert (r.risk.value, r.action.value) == ("low", "ignore/monitor")


# --- Provenance in the decision record ----------------------------------------

def test_decision_record_stores_fallback_mode(llm, tmp_path):
    llm("RateLimitError")
    case = DEMO["demo_4"]
    result = triage(case, use_llm=True)
    db = tmp_path / "reviews.db"
    review_store.record_decision(db, case, result, "confirm_flag",
                                 assessment_mode=result.assessment_mode)
    [event] = review_store.case_history(db, "demo_4")
    assert event["assessment_mode"] == "llm_fallback_offline"
    assert event["system_action"] == "review"
    snap = json.loads(event["system_snapshot"])["system_assessment"]
    assert snap["assessment_mode"] == "llm_fallback_offline"
    assert snap["fallback_reason"] == "rate_limit"
