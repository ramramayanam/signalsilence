"""Eval harness: run the triage pipeline against the labeled dataset.

Usage:
    python evals/run_eval.py                 # offline mode (deterministic + heuristics)
    ANTHROPIC_API_KEY=... python evals/run_eval.py   # LLM context judgment

Outputs per-label precision/recall, a confusion matrix, overall accuracy,
and — most important for a triage system — the false-negative rate on
'high' cases (a missed real threat is the expensive error; the 1-pager
target is <2%).
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence.schema import Case  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

LABELS = ["low", "review", "high"]


def load_cases(path):
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            yield Case(
                case_id=row["case_id"],
                protected_mark=row["protected_mark"],
                candidate_mark=row["candidate_mark"],
                candidate_class=row["candidate_class"],
                candidate_goods=row["candidate_goods"],
                applicant_name=row["applicant_name"],
                owner_entity_type=row["owner_entity_type"],
                goods_class_overlap=row["goods_class_overlap"].strip().lower() == "true",
                string_similarity_score=float(row["string_similarity_score"]),
                phonetic_match_score=float(row["phonetic_match_score"]),
                ground_truth_label=row["ground_truth_label"].strip().lower(),
            )


def main():
    data = Path(__file__).resolve().parents[1] / "data" / "synthetic_cases.csv"
    confusion = defaultdict(Counter)   # confusion[truth][predicted]
    misses = []

    for case in load_cases(data):
        result = triage(case)
        pred = result.risk.value
        truth = case.ground_truth_label
        confusion[truth][pred] += 1
        if pred != truth:
            misses.append((case, result))

    total = sum(sum(row.values()) for row in confusion.values())
    correct = sum(confusion[label][label] for label in LABELS)

    print(f"\nCases: {total}   Accuracy: {correct/total:.1%}\n")
    print("Confusion matrix (rows = ground truth, cols = predicted)")
    print(f"{'':>8}" + "".join(f"{c:>8}" for c in LABELS))
    for t in LABELS:
        print(f"{t:>8}" + "".join(f"{confusion[t][p]:>8}" for p in LABELS))

    print("\nPer-label metrics")
    for label in LABELS:
        tp = confusion[label][label]
        support = sum(confusion[label].values())
        predicted = sum(confusion[t][label] for t in LABELS)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        print(f"  {label:>7}: precision {precision:.2f}  recall {recall:.2f}  (n={support})")

    high_support = sum(confusion["high"].values())
    high_fn = high_support - confusion["high"]["high"]
    fn_to_low = confusion["high"]["low"]
    print(f"\nHigh-risk misses: {high_fn}/{high_support} "
          f"(downgraded to 'low': {fn_to_low} — the dangerous kind; target <2%)")

    if misses and "--show-misses" in sys.argv:
        print("\nMisclassified cases:")
        for case, result in misses:
            print(f"  {case.case_id}: {case.protected_mark} vs {case.candidate_mark} "
                  f"[{case.candidate_class}/{case.candidate_goods}] "
                  f"truth={case.ground_truth_label} pred={result.risk.value} "
                  f"lex={result.scores.lexical} phon={result.scores.phonetic} "
                  f"notes={result.invariant_notes}")


if __name__ == "__main__":
    main()
