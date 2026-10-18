"""Eval harness: run the triage pipeline against the labeled dataset.

Usage:
    python evals/run_eval.py                 # offline mode (deterministic + heuristics)
    python evals/run_eval.py --rag           # + precedent retrieval (leave-one-out)
    python evals/run_eval.py --judge audit   # + LLM-as-judge on audit trails (needs key)
    python evals/run_eval.py --judge rationale --judge-sample 20
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

from signalsilence.retrieval import PrecedentIndex  # noqa: E402
from signalsilence.schema import Case  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

LABELS = ["low", "review", "high"]


def _optional_int(value):
    """Blank or missing -> None (unknown), else int. Unknown is not 0."""
    value = (value or "").strip()
    return int(value) if value else None


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
                # Optional column: behavioral signal input (offline threshold
                # in triage.py). Absent from data/synthetic_cases.csv today.
                recent_filing_count=_optional_int(row.get("recent_filing_count")),
                ground_truth_label=row["ground_truth_label"].strip().lower(),
            )


def main():
    data = Path(__file__).resolve().parents[1] / "data" / "synthetic_cases.csv"
    confusion = defaultdict(Counter)   # confusion[truth][predicted]
    misses = []
    results = []

    cases = list(load_cases(data))
    retriever = None
    if "--rag" in sys.argv:
        # Leave-one-out is enforced per-case below (exclude_self=True):
        # a case must never retrieve its own adjudication.
        retriever = PrecedentIndex(cases)
        print(f"\nRAG enabled: precedent retrieval, backend={retriever.backend}, "
              f"leave-one-out")

    for case in cases:
        result = triage(case, retriever=retriever, exclude_self=True)
        results.append((case, result))
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

    if "--judge" in sys.argv:
        from judge import run_judge  # noqa: E402  (same directory)
        target = sys.argv[sys.argv.index("--judge") + 1] \
            if len(sys.argv) > sys.argv.index("--judge") + 1 \
            and not sys.argv[sys.argv.index("--judge") + 1].startswith("--") \
            else "audit"
        sample = None
        if "--judge-sample" in sys.argv:
            sample = int(sys.argv[sys.argv.index("--judge-sample") + 1])
        run_judge(results, target=target, sample=sample)


if __name__ == "__main__":
    main()
