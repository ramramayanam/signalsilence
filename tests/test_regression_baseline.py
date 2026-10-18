"""Permanent regression baseline: default (offline) outputs for 105 cases.

Covers the 5 canonical demo cases and the 100 evaluation cases. The
fixture (tests/fixtures/regression_baseline.json) records every
deterministic output field of triage() in its default configuration:
offline context judgment, no retrieval. LLM output and timestamps are
excluded because they are volatile.

If this test fails, an output changed. That is only acceptable as a
deliberate, reviewed change:

  1. bump POLICY_VERSION in src/signalsilence/policy.py, then
  2. python tests/test_regression_baseline.py --update
  3. review the fixture diff in the commit like any other code change.

--update refuses to rewrite changed outputs under an unchanged
POLICY_VERSION, so a rules change cannot silently keep the old label.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "evals"))

from run_eval import load_cases  # noqa: E402
from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.policy import POLICY_VERSION  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

FIXTURE = REPO / "tests" / "fixtures" / "regression_baseline.json"


def _cases():
    yield from CANONICAL.values()
    yield from load_cases(REPO / "data" / "synthetic_cases.csv")


def current_outputs() -> dict:
    out = {}
    for case in _cases():
        r = triage(case, use_llm=False)
        out[case.case_id] = {
            "risk": r.risk.value,
            "action": r.action.value,
            "lexical": r.scores.lexical,
            "phonetic": r.scores.phonetic,
            "semantic": r.scores.semantic,
            "goods_adjacent": r.context.goods_adjacent,
            "added_wording_descriptive": r.context.added_wording_descriptive,
            "plausible_affiliation": r.context.plausible_affiliation,
            "behavioral_signal": r.context.behavioral_signal,
            "rationale": r.context.rationale,
            "insight": r.insight,
            "invariant_notes": r.invariant_notes,
        }
    return out


def _diff(expected: dict, actual: dict) -> list:
    lines = [f"missing case {k}" for k in expected if k not in actual]
    lines += [f"new case {k}" for k in actual if k not in expected]
    for k in expected:
        if k in actual and expected[k] != actual[k]:
            fields = [f for f in expected[k] if expected[k][f] != actual[k].get(f)]
            lines.append(f"{k}: " + ", ".join(
                f"{f} {expected[k][f]!r} -> {actual[k].get(f)!r}" for f in fields))
    return lines


def test_fixture_matches_current_policy_version():
    baseline = json.loads(FIXTURE.read_text())
    assert baseline["policy_version"] == POLICY_VERSION, (
        "POLICY_VERSION changed: regenerate and review the fixture "
        "(python tests/test_regression_baseline.py --update)")


def test_default_outputs_match_baseline():
    baseline = json.loads(FIXTURE.read_text())
    assert len(baseline["cases"]) == 105
    changes = _diff(baseline["cases"], current_outputs())
    assert not changes, (
        f"{len(changes)} case(s) changed default output — scoring changes need "
        "explicit approval (see module docstring):\n" + "\n".join(changes[:20]))


if __name__ == "__main__" and "--update" in sys.argv:
    actual = current_outputs()
    if FIXTURE.exists():
        old = json.loads(FIXTURE.read_text())
        changes = _diff(old["cases"], actual)
        if changes and old["policy_version"] == POLICY_VERSION:
            sys.exit(f"Refusing: {len(changes)} output change(s) under unchanged "
                     f"POLICY_VERSION {POLICY_VERSION!r}. Bump it first.")
        print(f"{len(changes)} case(s) changed")
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(json.dumps(
        {"policy_version": POLICY_VERSION,
         "mode": "offline context judgment, no retrieval (triage use_llm=False)",
         "cases": actual},
        indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(f"wrote {FIXTURE.relative_to(REPO)} ({len(actual)} cases)")
