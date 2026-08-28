"""Triage orchestration: deterministic scores -> context judgment -> policy.

Two context-judgment backends:

  * LLM mode (ANTHROPIC_API_KEY set): the model judges ONLY the four
    contextual questions the deterministic layer cannot answer —
    goods adjacency, descriptive wording, plausible affiliation,
    behavioral signal. It returns strict JSON. It does NOT decide risk;
    policy.py does. This keeps the LLM inside a fence: persuasive prose
    cannot move a classification, only structured context facts can.

  * Offline mode (no key): transparent heuristics approximate the same
    four judgments so the full pipeline, evals, and demo run at zero cost.
"""
import json
import os
import re

from .policy import classify
from .retrieval import format_precedents_for_prompt, precedent_adjacency_vote
from .schema import Case, ContextJudgment, SimilarityScores, TriageResult
from . import similarity

CONTEXT_PROMPT = """You are a trademark context analyst. Judge ONLY the four context questions below for this case. Do not classify risk. Return strict JSON, no markdown, no extra text.

Case:
protected_mark: {protected_mark}
candidate_mark: {candidate_mark}
candidate_class: {candidate_class}
candidate_goods: {candidate_goods}
applicant_name: {applicant_name}
owner_entity_type: {owner_entity_type}
recent_filing_count: {recent_filing_count}

Adjudicated precedents (retrieved similar past cases and their outcomes;
grounding evidence for the goods_adjacent judgment — weigh them, do not
copy them blindly):
{precedents}

Definitions (from the SignalSilence instruction set):
- goods_adjacent: goods are commercially adjacent (complements, accessories, line extensions, same channels/purchasers, or consumers could assume shared brand origin). Class differences do not control.
- added_wording_descriptive: the candidate mark is the core mark plus wording that is descriptive/generic (a product or category descriptor), not a distinctive element.
- plausible_affiliation: the applicant plausibly appears affiliated with the protected mark's owner (subsidiary, regional entity, franchise, aligned corporate identity).
- behavioral_signal: filing velocity or pattern suggests serial/opportunistic filing.

Return: {{"goods_adjacent": bool, "added_wording_descriptive": bool, "plausible_affiliation": bool, "behavioral_signal": bool, "rationale": "one short sentence"}}"""

# NICE classes that are commercially adjacent to apparel/footwear (025) for
# offline mode. Deliberately tiny: this is a demo heuristic, not a product.
_ADJACENT_TO_025 = {"018", "025", "026", "028", "035"}


def _offline_context(case: Case, precedents=None) -> ContextJudgment:
    """Zero-cost approximation of the four contextual judgments.

    With precedents (RAG offline mode), retrieval augments the adjacency
    heuristic: if the nearest adjudicated cases were decided above `low`,
    the goods relationship evidently mattered there, and that is evidence
    of adjacency here. Retrieval feeds the context judgment only —
    policy.py invariants still decide risk.
    """
    goods = (case.candidate_goods or "").lower()
    cand_class = str(case.candidate_class or "").zfill(3)

    adjacent = case.goods_class_overlap or (
        cand_class in _ADJACENT_TO_025
        and any(w in goods for w in (
            "shoe", "lace", "apparel", "clothing", "footwear", "bag",
            "sport", "athletic", "yoga", "legging", "sock", "accessor",
        ))
    )
    core = re.sub(r"[^A-Z]", "", case.protected_mark.upper())
    cand_tokens = re.findall(r"[A-Z]+", case.candidate_mark.upper())
    descriptive = (
        len(cand_tokens) > 1
        and similarity.lexical_similarity(case.protected_mark, cand_tokens[0]) >= 0.80
    )
    affiliated = any(
        w in (case.applicant_name or "").lower()
        for w in (core.lower(), "subsidiary", "franchise", "official")
    )
    behavioral = (case.recent_filing_count or 0) >= 10
    rationale = "offline heuristic judgment"
    if precedents and not adjacent and precedent_adjacency_vote(precedents):
        adjacent = True
        ids = ",".join(p.case_id for p in precedents)
        rationale = f"offline heuristic + precedent adjacency vote ({ids})"
    return ContextJudgment(
        goods_adjacent=bool(adjacent),
        added_wording_descriptive=bool(descriptive),
        plausible_affiliation=bool(affiliated),
        behavioral_signal=behavioral,
        rationale=rationale,
    )


def _llm_context(case: Case, precedents=None) -> ContextJudgment:
    import anthropic  # imported lazily so offline mode has no dependency

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.environ.get("SIGNALSILENCE_MODEL", "claude-sonnet-4-6"),
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": CONTEXT_PROMPT.format(
                protected_mark=case.protected_mark,
                candidate_mark=case.candidate_mark,
                candidate_class=case.candidate_class,
                candidate_goods=case.candidate_goods,
                applicant_name=case.applicant_name,
                owner_entity_type=case.owner_entity_type,
                recent_filing_count=case.recent_filing_count,
                precedents=format_precedents_for_prompt(precedents or []),
            ),
        }],
    )
    raw = "".join(b.text for b in msg.content if b.type == "text")
    try:
        data = json.loads(re.sub(r"```(json)?|```", "", raw).strip())
        return ContextJudgment(
            goods_adjacent=bool(data["goods_adjacent"]),
            added_wording_descriptive=bool(data["added_wording_descriptive"]),
            plausible_affiliation=bool(data["plausible_affiliation"]),
            behavioral_signal=bool(data["behavioral_signal"]),
            rationale=str(data.get("rationale", ""))[:200],
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        # v1-era safety rule preserved: on parse failure, fail toward caution.
        return _offline_context(case, precedents)


def triage(case: Case, use_llm: bool | None = None, retriever=None,
           exclude_self: bool = False) -> TriageResult:
    """Run one case through the full pipeline.

    retriever: optional PrecedentIndex (RAG). exclude_self=True enables
    leave-one-out retrieval for evals, so a case never retrieves itself.
    """
    lex, phon = similarity.score_case(case.protected_mark, case.candidate_mark)
    # Prefer freshly computed deterministic scores; dataset scores are kept
    # for comparison in evals, not trusted for classification.
    scores = SimilarityScores(lexical=lex, phonetic=phon)

    precedents = []
    if retriever is not None:
        precedents = retriever.retrieve(
            case, k=3,
            exclude_case_id=case.case_id if exclude_self else None)

    if use_llm is None:
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    ctx = (_llm_context(case, precedents) if use_llm
           else _offline_context(case, precedents))

    risk, action, notes = classify(scores, ctx, same_class=case.goods_class_overlap)
    insight = ctx.rationale or notes[-1]
    return TriageResult(
        case_id=case.case_id, risk=risk, action=action,
        scores=scores, context=ctx, insight=insight, invariant_notes=notes,
        precedents=precedents,
    )
