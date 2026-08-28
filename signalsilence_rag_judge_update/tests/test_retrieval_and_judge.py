"""Tests for the RAG layer and the LLM-as-judge harness.

Same philosophy as test_policy.py: the design rules stated in the
README, restated as executable tests.
"""
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "evals"))

from signalsilence.retrieval import (  # noqa: E402
    PrecedentIndex, precedent_adjacency_vote)
from signalsilence.schema import Case  # noqa: E402
from signalsilence.triage import triage  # noqa: E402
import judge as judge_mod  # noqa: E402

DATA = Path(__file__).resolve().parents[1] / "data" / "synthetic_cases.csv"


def _cases():
    out = []
    with open(DATA, newline="") as f:
        for row in csv.DictReader(f):
            out.append(Case(
                case_id=row["case_id"], protected_mark=row["protected_mark"],
                candidate_mark=row["candidate_mark"],
                candidate_class=row["candidate_class"],
                candidate_goods=row["candidate_goods"],
                applicant_name=row["applicant_name"],
                owner_entity_type=row["owner_entity_type"],
                goods_class_overlap=row["goods_class_overlap"].strip().lower() == "true",
                string_similarity_score=float(row["string_similarity_score"]),
                phonetic_match_score=float(row["phonetic_match_score"]),
                ground_truth_label=row["ground_truth_label"].strip().lower(),
            ))
    return out


# --- RAG: retrieval rules ---

def test_leave_one_out_never_retrieves_self():
    """Eval rule: a case must not retrieve its own adjudication —
    otherwise the ground-truth label leaks into the prediction."""
    cases = _cases()
    idx = PrecedentIndex(cases)
    for case in cases[:10]:
        for p in idx.retrieve(case, k=3, exclude_case_id=case.case_id):
            assert p.case_id != case.case_id


def test_retrieval_is_deterministic():
    """BM25 backend: identical query -> identical ranked precedents."""
    cases = _cases()
    idx = PrecedentIndex(cases)
    a = idx.retrieve(cases[0], k=3, exclude_case_id=cases[0].case_id)
    b = idx.retrieve(cases[0], k=3, exclude_case_id=cases[0].case_id)
    assert [p.case_id for p in a] == [p.case_id for p in b]


def test_retrieval_finds_goods_neighbors():
    """A yoga-instruction filing should retrieve yoga/fitness precedents,
    not juice bars — goods wording drives adjacency."""
    cases = _cases()
    idx = PrecedentIndex(cases)
    target = next(c for c in cases if "yoga instruction" in c.candidate_goods)
    got = idx.retrieve(target, k=3, exclude_case_id=target.case_id)
    assert any("yoga" in p.candidate_goods or "fitness" in p.candidate_goods
               for p in got)


def test_single_noisy_neighbor_cannot_flip_adjacency():
    """Precedent vote requires >= 2 above-low neighbors: one noisy
    precedent must not move the context judgment."""
    from signalsilence.retrieval import Precedent
    one_high = [Precedent("x", "M", "g", "025", "high", 5.0),
                Precedent("y", "M2", "g2", "032", "low", 4.0),
                Precedent("z", "M3", "g3", "030", "low", 3.0)]
    assert precedent_adjacency_vote(one_high) is False
    two_high = one_high[:1] + [Precedent("y", "M2", "g2", "025", "review", 4.0),
                               one_high[2]]
    assert precedent_adjacency_vote(two_high) is True


def test_rag_cannot_override_policy_invariants():
    """The fence: retrieval feeds the context judgment, never the policy.
    A low-similarity mark stays low even if every precedent screams high —
    invariants require similarity, and precedents cannot supply it."""
    cases = _cases()
    idx = PrecedentIndex(cases)
    weak = Case(
        case_id="test_weak", protected_mark="LULULEMON",
        candidate_mark="ZEBRAFISH", candidate_class="025",
        candidate_goods="yoga pants", applicant_name="X",
        owner_entity_type="corporation", goods_class_overlap=True)
    result = triage(weak, use_llm=False, retriever=idx)
    assert result.risk.value == "low"


def test_precedents_recorded_in_audit_trail():
    """Every retrieved precedent lands in the result for auditability."""
    cases = _cases()
    idx = PrecedentIndex(cases)
    result = triage(cases[0], use_llm=False, retriever=idx, exclude_self=True)
    assert len(result.precedents) == 3
    assert all(p.case_id != cases[0].case_id for p in result.precedents)


# --- LLM-as-judge: harness rules (judge model mocked; no API needed) ---

class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeMessages:
    def __init__(self, payload):
        self._payload = payload

    def create(self, **kwargs):
        class _Msg:
            content = [_FakeBlock(self._payload)]
        _Msg.content = [_FakeBlock(self._payload)]
        return _Msg()


class _FakeClient:
    def __init__(self, payload):
        self.messages = _FakeMessages(payload)


def _one_result():
    cases = _cases()
    case = cases[0]
    return case, triage(case, use_llm=False)


def test_judge_parses_strict_json_and_passes():
    case, result = _one_result()
    payload = json.dumps({"faithfulness": 5, "invariant_citation": 5,
                          "evidence_integrity": 4, "verdict": "pass",
                          "comment": "clean"})
    graded = judge_mod.judge_one(case, result, client=_FakeClient(payload))
    assert graded["verdict"] == "pass" and graded["parse_ok"]


def test_judge_flags_low_scores_regardless_of_model_verdict():
    """Verdict is recomputed from the rubric threshold — a judge cannot
    talk itself into 'pass' while scoring a dimension at 2."""
    case, result = _one_result()
    payload = json.dumps({"faithfulness": 2, "invariant_citation": 5,
                          "evidence_integrity": 5, "verdict": "pass",
                          "comment": "generous"})
    graded = judge_mod.judge_one(case, result, client=_FakeClient(payload))
    assert graded["verdict"] == "flag"


def test_unparseable_judge_output_flags_for_human_review():
    case, result = _one_result()
    graded = judge_mod.judge_one(case, result,
                                 client=_FakeClient("sorry, no JSON here"))
    assert graded["verdict"] == "flag" and not graded["parse_ok"]
