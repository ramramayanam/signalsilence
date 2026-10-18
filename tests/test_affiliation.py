"""D2: offline mode does not infer affiliation from applicant-name text (rules-v2).

Before rules-v2, any applicant name containing the protected word or
"subsidiary"/"franchise"/"official" counted as plausibly affiliated, and
policy I4 then capped the case at REVIEW. Case has no explicit
affiliation field, so offline affiliation is now never established.
The I4 rule itself is unchanged; since rules-v4 the LLM cannot assert
affiliation either, so I4 is dormant in both modes (see test_llm_affiliation.py).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence.policy import POLICY_VERSION  # noqa: E402
from signalsilence.schema import Case  # noqa: E402
from signalsilence.triage import _offline_context, triage  # noqa: E402

# (case_id, protected, candidate, class, goods, applicant, entity, same_class,
#  expected risk/action under rules-v2, first rule, rules-v1 result for reference)
CASES = [
    ("d2_knockoff", "LULULEMON", "LULULEMMON", "025", "yoga pants",
     "Lululemon Knockoffs LLC", "corporation", True, ("high", "escalate"), "I1", ("review", "review")),
    ("d2_nikesh", "NIKE", "NIKKE", "025", "clothing",
     "Nikesh Patel", "individual", True, ("high", "escalate"), "I1", ("review", "review")),
    ("d2_batavia", "BATA", "BAATA LACES", "026", "shoelaces",
     "Batavia Shoe Supply", "corporation", False, ("high", "escalate"), "I2", ("review", "review")),
    ("d2_official", "LULULEMON", "LULULEMMON", "025", "yoga pants",
     "Official Athletic Wear LLC", "corporation", True, ("high", "escalate"), "I1", ("review", "review")),
    ("d2_fanclub", "LULULEMON", "LULUBLOOM", "041", "juice bar",
     "Lululemon Fan Club", "individual", False, ("low", "ignore/monitor"), "I5", ("low", "review")),
    # Normal applicant: never matched the old heuristic; result is unchanged.
    ("d2_normal", "LULULEMON", "LULULEMMON", "025", "yoga pants",
     "Peak Motion Labs LLC", "corporation", True, ("high", "escalate"), "I1", ("high", "escalate")),
]
IDS = [c[0] for c in CASES]


def _case(row):
    return Case(*row[:8])


def test_policy_version_is_current():
    assert POLICY_VERSION == "rules-v4"  # D2 shipped in rules-v2; current is v4


@pytest.mark.parametrize("row", CASES, ids=IDS)
def test_applicant_name_text_does_not_establish_affiliation(row):
    assert _offline_context(_case(row)).plausible_affiliation is False


@pytest.mark.parametrize("row", CASES, ids=IDS)
def test_rules_v2_risk_and_action(row):
    *_, expected, first_rule, _v1 = row
    r = triage(_case(row), use_llm=False)
    assert (r.risk.value, r.action.value) == expected
    assert r.invariant_notes[0].startswith(first_rule)
    assert not any(n.startswith("I4") for n in r.invariant_notes)


def test_llm_asserted_affiliation_is_ignored_since_rules_v4(monkeypatch):
    """rules-v4 deliberately reverses the old behavior (LLM claim -> I4 REVIEW):
    an LLM affiliation claim is not evidence, so I4 does not fire."""
    from test_llm_fallback import _reply, fake_anthropic
    monkeypatch.setitem(sys.modules, "anthropic",
                        fake_anthropic(_reply(goods_adjacent=True, plausible_affiliation=True)))
    r = triage(_case(CASES[-1]), use_llm=True)
    assert r.assessment_mode == "llm"
    assert r.context.plausible_affiliation is False
    assert (r.risk.value, r.action.value) == ("high", "escalate")
    assert not any(n.startswith("I4") for n in r.invariant_notes)
