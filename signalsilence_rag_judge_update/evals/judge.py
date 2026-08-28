"""LLM-as-judge: grade explanation quality, not classifications.

Classification is graded deterministically against ground-truth labels
(run_eval.py) — where a deterministic grader exists, it is strictly
better than a model. The judge grades the one thing only a model can:
whether the system's *explanations* are faithful to its evidence.

Two targets, selectable via `--judge <target>`:

  audit      the full audit trail (invariant notes + insight + scores +
             context facts) — available in offline and LLM modes alike
  rationale  the LLM context rationale specifically — only meaningful
             when the pipeline ran with ANTHROPIC_API_KEY set

Rubric (1-5 each, strict JSON):
  faithfulness        does the explanation match the actual evidence
                      (scores, context facts) with nothing invented?
  invariant_citation  does it cite the invariant that actually fired?
  evidence_integrity  is similarity stated truthfully, never distorted
                      to justify the conclusion? (README principle 3)

Guardrails:
  * The judge is a DIFFERENT model from the pipeline's context model by
    default (a model should not grade its own homework).
  * The judge has no write access to anything: scores are reported,
    logged, and spot-checkable; they cannot alter a classification.
  * Judge outputs are strict JSON; unparseable output flags the case
    for human review rather than being guessed at.
"""
import json
import os
import re
import statistics

JUDGE_PROMPT = """You are grading the explanation quality of an AI trademark \
triage system. You are NOT grading whether the classification is correct — \
only whether the explanation is faithful to the evidence shown.

Evidence (ground facts the system had):
  lexical similarity: {lexical}
  phonetic similarity: {phonetic}
  same NICE class: {same_class}
  context facts: goods_adjacent={goods_adjacent}, \
added_wording_descriptive={descriptive}, plausible_affiliation={affiliated}, \
behavioral_signal={behavioral}
  retrieved precedents: {precedents}

System output being graded:
  classification: {risk} / action: {action}
  {target_name}: {target_text}

Score 1-5 on each dimension (5 = flawless):
- faithfulness: the explanation matches the evidence above; nothing is \
invented, omitted facts don't contradict it.
- invariant_citation: it identifies the decision rule that actually drove \
the outcome (rules are named I1-I6 or described equivalently).
- evidence_integrity: similarity is stated truthfully; the explanation \
never downplays or inflates the scores to make the conclusion look better.

Return strict JSON only, no markdown, no extra text:
{{"faithfulness": int, "invariant_citation": int, "evidence_integrity": int, \
"verdict": "pass" or "flag", "comment": "one short sentence"}}
Use "flag" if any dimension scores 3 or below."""

PASS_THRESHOLD = 4  # any dimension below this => flag


def _default_client():
    import anthropic  # lazy: only needed when the judge actually runs
    return anthropic.Anthropic()


def judge_one(case, result, target: str = "audit", client=None,
              model: str = None) -> dict:
    """Grade one triage result. Returns the parsed rubric dict.

    client is injectable for testing; model defaults to a different
    model family than the pipeline's context model.
    """
    client = client or _default_client()
    model = model or os.environ.get("SIGNALSILENCE_JUDGE_MODEL",
                                    "claude-haiku-4-5")
    if target == "rationale":
        target_name = "context rationale"
        target_text = result.context.rationale or "(empty)"
    else:
        target_name = "audit trail"
        target_text = (f"insight: {result.insight} | "
                       f"invariants fired: {'; '.join(result.invariant_notes)}")

    precedents = "; ".join(
        f"{p.candidate_mark}({p.label})" for p in result.precedents) or "none"

    msg = client.messages.create(
        model=model, max_tokens=300,
        messages=[{"role": "user", "content": JUDGE_PROMPT.format(
            lexical=result.scores.lexical, phonetic=result.scores.phonetic,
            same_class=case.goods_class_overlap,
            goods_adjacent=result.context.goods_adjacent,
            descriptive=result.context.added_wording_descriptive,
            affiliated=result.context.plausible_affiliation,
            behavioral=result.context.behavioral_signal,
            precedents=precedents,
            risk=result.risk.value, action=result.action.value,
            target_name=target_name, target_text=target_text)}])
    raw = "".join(b.text for b in msg.content if b.type == "text")
    try:
        data = json.loads(re.sub(r"```(json)?|```", "", raw).strip())
        scores = {k: int(data[k]) for k in
                  ("faithfulness", "invariant_citation", "evidence_integrity")}
        verdict = "flag" if min(scores.values()) < PASS_THRESHOLD else "pass"
        return {**scores, "verdict": verdict,
                "comment": str(data.get("comment", ""))[:200],
                "case_id": case.case_id, "parse_ok": True}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        # Unparseable judge output is itself a finding: flag for human review.
        return {"faithfulness": 0, "invariant_citation": 0,
                "evidence_integrity": 0, "verdict": "flag",
                "comment": "judge output unparseable — human review",
                "case_id": case.case_id, "parse_ok": False}


def run_judge(results, target: str = "audit", sample: int = None,
              client=None, model: str = None):
    """Judge a batch of (case, result) pairs and print the report."""
    if target not in ("audit", "rationale"):
        raise ValueError("--judge target must be 'audit' or 'rationale'")
    batch = results[:sample] if sample else results
    graded = [judge_one(c, r, target=target, client=client, model=model)
              for c, r in batch]

    dims = ("faithfulness", "invariant_citation", "evidence_integrity")
    parsed = [g for g in graded if g["parse_ok"]]
    flags = [g for g in graded if g["verdict"] == "flag"]

    print(f"\nLLM-as-judge report  (target={target}, n={len(graded)}, "
          f"model={model or os.environ.get('SIGNALSILENCE_JUDGE_MODEL', 'claude-haiku-4-5')})")
    for d in dims:
        vals = [g[d] for g in parsed]
        mean = statistics.mean(vals) if vals else 0.0
        print(f"  {d:>18}: mean {mean:.2f}/5")
    print(f"  {'flagged':>18}: {len(flags)}/{len(graded)} "
          f"(pass threshold: all dims >= {PASS_THRESHOLD})")
    for g in flags:
        print(f"    - {g['case_id']}: {g['comment']}")
    return graded
