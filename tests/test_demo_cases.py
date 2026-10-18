"""Regression baseline for the 5 canonical demo cases (offline mode).

Expected values were recorded from the unmodified pipeline at commit
1657fbe (Phase 0.5); demo_4/demo_5 notes updated for rules-v3 (D1).
If one of these fails, a change has altered
existing scoring output — that requires explicit approval, not an
edit to this file.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

BASELINE = {
    "demo_1": ("high", "escalate", 0.98, 1.0,
               ["I1: strong/near-identical mark + same class -> HIGH"]),
    "demo_2": ("high", "escalate", 0.95, 1.0,
               ["I1: strong/near-identical mark + same class -> HIGH"]),
    "demo_3": ("high", "escalate", 0.88, 1.0,
               ["I2: strong similarity + adjacent goods -> HIGH (non-downgradable)",
                "I2a: descriptive added wording ignored for risk reduction",
                "I2b: absence of behavioral signal does not reduce risk"]),
    "demo_4": ("low", "ignore/monitor", 0.9, 0.85,
               ["I5: high similarity but unrelated goods -> LOW (context override)"]),
    "demo_5": ("low", "ignore/monitor", 0.78, 1.0,
               ["I5: high similarity but unrelated goods -> LOW (context override)"]),
}


def test_demo_queue_is_exactly_the_five_canonical_cases():
    assert sorted(c.case_id for c in CANONICAL.values()) == sorted(BASELINE)


def test_demo_case_outputs_match_baseline():
    for case in CANONICAL.values():
        r = triage(case, use_llm=False)
        got = (r.risk.value, r.action.value, r.scores.lexical,
               r.scores.phonetic, r.invariant_notes)
        assert got == BASELINE[case.case_id], case.case_id
