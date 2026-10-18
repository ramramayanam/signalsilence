"""Filing-volume (behavioral signal) rule: plumbing and boundary tests.

Field: Case.recent_filing_count. Offline heuristic (triage.py):
behavioral_signal = recent_filing_count >= 10. Policy rule I3 (policy.py):
similar mark (lexical or phonetic >= 0.70) + behavioral signal -> HIGH,
evaluated after I4/I1/I2, so it only fires when those do not.

The cases below are a small synthetic slice written for these tests.
Their expected values are derived from the current rules (rules-v1),
not legal ground truth. Each one is fed through a CSV and the eval
loader, so the test covers the full path: data -> load_cases -> triage.
"""
import csv
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "evals"))

from run_eval import load_cases  # noqa: E402
from signalsilence.similarity import score_case  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

# (case_id, protected, candidate, class, goods, same_class, filings,
#  expect_behavioral, expect_risk, expect_action, expect_rule, purpose)
SLICE = [
    ("fv_blank", "LULULEMON", "LULUFLOW", "009", "smartwatch software", False, "",
     False, "low", "ignore/monitor", "I5", "unknown count is not a signal"),
    ("fv_zero", "LULULEMON", "LULUFLOW", "009", "smartwatch software", False, "0",
     False, "low", "ignore/monitor", "I5", "zero filings"),
    ("fv_below", "LULULEMON", "LULUFLOW", "009", "smartwatch software", False, "9",
     False, "low", "ignore/monitor", "I5", "one below threshold"),
    ("fv_at", "LULULEMON", "LULUFLOW", "009", "smartwatch software", False, "10",
     True, "high", "escalate", "I3", "exactly at threshold; I3 is the rule that fires"),
    ("fv_above", "LULULEMON", "LULUFLOW", "009", "smartwatch software", False, "25",
     True, "high", "escalate", "I3", "above threshold; I3 fires"),
    ("fv_moderate", "LULULEMON", "LULUNOVA", "009", "fitness software", False, "30",
     True, "high", "escalate", "I3", "moderate-only similarity (lex 0.84) + volume -> I3"),
    ("fv_weak", "LULULEMON", "RIVER MOSS", "009", "fitness software", False, "40",
     True, "low", "ignore/monitor", "default", "volume alone does not escalate a dissimilar mark"),
    ("fv_masked", "NIKE", "NIKKE", "025", "clothing", True, "18",
     True, "high", "escalate", "I1", "signal present but masked: I1 fires first"),
]

FIELDS = ["case_id", "protected_mark", "candidate_mark", "candidate_class",
          "candidate_goods", "applicant_name", "owner_entity_type",
          "string_similarity_score", "phonetic_match_score", "goods_class_overlap",
          "ground_truth_label", "source_type", "recent_filing_count"]


def _write_slice(path: Path, include_count_column: bool = True) -> Path:
    fields = FIELDS if include_count_column else FIELDS[:-1]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for (cid, pm, cm, cls, goods, same, filings, _, risk, *_rest) in SLICE:
            lex, phon = score_case(pm, cm)  # informational columns; not used to classify
            w.writerow({
                "case_id": cid, "protected_mark": pm, "candidate_mark": cm,
                "candidate_class": cls, "candidate_goods": goods,
                "applicant_name": "Peak Motion Labs LLC", "owner_entity_type": "corporation",
                "string_similarity_score": lex, "phonetic_match_score": phon,
                "goods_class_overlap": str(same), "ground_truth_label": risk,
                "source_type": "synthetic", "recent_filing_count": filings,
            })
    return path


@pytest.fixture
def slice_cases(tmp_path):
    return {c.case_id: c for c in load_cases(_write_slice(tmp_path / "fv.csv"))}


def test_loader_reads_filing_count(slice_cases):
    assert slice_cases["fv_blank"].recent_filing_count is None
    assert slice_cases["fv_zero"].recent_filing_count == 0
    assert slice_cases["fv_at"].recent_filing_count == 10


def test_loader_without_column_gives_unknown_count(tmp_path):
    cases = list(load_cases(_write_slice(tmp_path / "fv.csv", include_count_column=False)))
    assert cases and all(c.recent_filing_count is None for c in cases)


def test_eval_dataset_has_no_filing_counts():
    """Why the 105-case baseline is unaffected: the eval CSV carries no counts."""
    cases = list(load_cases(REPO / "data" / "synthetic_cases.csv"))
    assert len(cases) == 100
    assert all(c.recent_filing_count is None for c in cases)


@pytest.mark.parametrize("row", SLICE, ids=[r[0] for r in SLICE])
def test_filing_volume_slice(row, slice_cases):
    cid, *_, expect_behavioral, expect_risk, expect_action, expect_rule, purpose = row
    r = triage(slice_cases[cid], use_llm=False)
    assert r.context.behavioral_signal is expect_behavioral, purpose
    assert (r.risk.value, r.action.value) == (expect_risk, expect_action), purpose
    assert r.invariant_notes[0].startswith(expect_rule), (purpose, r.invariant_notes)
    fired_i3 = any(n.startswith("I3") for n in r.invariant_notes)
    assert fired_i3 is (expect_rule == "I3"), purpose
