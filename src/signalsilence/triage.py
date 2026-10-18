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

If LLM mode is requested but the model is unavailable (package missing,
auth, network, rate limit, unusable response), triage never crashes: it
uses the offline judgment, labels the result "llm_fallback_offline" with
a safe failure category, keeps the offline risk, and raises a MONITOR
action to REVIEW so a degraded assessment is not silently dismissed.
"""
import json
import os
import re

from .policy import classify
from .retrieval import format_precedents_for_prompt, precedent_adjacency_vote
from .schema import Action, Case, ContextJudgment, SimilarityScores, TriageResult
from . import similarity

MODE_OFFLINE = "offline"
MODE_LLM = "llm"
MODE_FALLBACK = "llm_fallback_offline"


class LLMUnavailable(Exception):
    """The LLM context judgment could not be used. Carries a safe category only."""

    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


def _failure_category(exc: Exception, anthropic) -> str:
    """Map an SDK exception to a safe category by type; message text is never read."""
    checks = (  # most specific first: APITimeoutError subclasses APIConnectionError
        ("AuthenticationError", "authentication"),
        ("PermissionDeniedError", "authentication"),
        ("RateLimitError", "rate_limit"),
        ("APITimeoutError", "timeout"),
        ("APIConnectionError", "connection"),
        ("AnthropicError", "api_error"),
    )
    for name, category in checks:
        cls = getattr(anthropic, name, None)
        if isinstance(cls, type) and isinstance(exc, cls):
            return category
    return "unexpected_error"  # e.g. TypeError when no API key can be resolved


def _strict_bool(value) -> bool:
    """Accept only JSON booleans or the strings "true"/"false" (any case).

    Anything else (numbers, "yes", null, ...) is ambiguous and rejected,
    so the caller falls back instead of inventing a fact.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        return value.strip().lower() == "true"
    raise ValueError("not a boolean")

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
    cand_tokens = re.findall(r"[A-Z]+", case.candidate_mark.upper())
    descriptive = (
        len(cand_tokens) > 1
        and similarity.lexical_similarity(case.protected_mark, cand_tokens[0]) >= 0.80
    )
    # Affiliation is not established offline (rules-v2). Applicant-name text
    # is not evidence: a brand inside a name is as typical of knock-offs
    # ("Lululemon Knockoffs LLC") as of affiliates, and substring matching
    # misfires ("Nikesh" contains "nike"). Case has no explicit affiliation
    # field, so only LLM mode can assert it.
    affiliated = False
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
    """LLM context judgment. Raises LLMUnavailable on any failure; triage() falls back."""
    prompt = CONTEXT_PROMPT.format(
        protected_mark=case.protected_mark,
        candidate_mark=case.candidate_mark,
        candidate_class=case.candidate_class,
        candidate_goods=case.candidate_goods,
        applicant_name=case.applicant_name,
        owner_entity_type=case.owner_entity_type,
        recent_filing_count=case.recent_filing_count,
        precedents=format_precedents_for_prompt(precedents or []),
    )
    try:
        import anthropic  # imported lazily so offline mode has no dependency
    except ImportError:
        raise LLMUnavailable("package_missing") from None
    try:
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=os.environ.get("SIGNALSILENCE_MODEL", "claude-sonnet-4-6"),
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in msg.content if b.type == "text")
    except Exception as exc:  # any client/transport failure must degrade, not crash
        raise LLMUnavailable(_failure_category(exc, anthropic)) from None
    try:
        data = json.loads(re.sub(r"```(json)?|```", "", raw).strip())
        return ContextJudgment(
            goods_adjacent=_strict_bool(data["goods_adjacent"]),
            added_wording_descriptive=_strict_bool(data["added_wording_descriptive"]),
            plausible_affiliation=_strict_bool(data["plausible_affiliation"]),
            behavioral_signal=_strict_bool(data["behavioral_signal"]),
            rationale=str(data.get("rationale", ""))[:200],
        )
    except (ValueError, KeyError, TypeError):  # JSONDecodeError is a ValueError
        raise LLMUnavailable("malformed_response") from None


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
    mode, fallback_reason = MODE_OFFLINE, None
    if use_llm:
        try:
            ctx, mode = _llm_context(case, precedents), MODE_LLM
        except LLMUnavailable as exc:
            mode, fallback_reason = MODE_FALLBACK, exc.category
            ctx = _offline_context(case, precedents)
            ctx.rationale = f"{ctx.rationale} (LLM unavailable: {fallback_reason})"
    else:
        ctx = _offline_context(case, precedents)

    risk, action, notes = classify(scores, ctx, same_class=case.goods_class_overlap)
    if mode == MODE_FALLBACK:
        # Risk is kept exactly as the offline policy decided. Only a MONITOR
        # action is raised, so a degraded assessment still gets human review.
        if action == Action.MONITOR:
            action = Action.REVIEW
            notes.append(f"LLM fallback ({fallback_reason}): offline assessment used; "
                         "action raised MONITOR -> REVIEW because the LLM was unavailable")
        else:
            notes.append(f"LLM fallback ({fallback_reason}): offline assessment used; "
                         "action unchanged")
    insight = ctx.rationale or notes[-1]
    return TriageResult(
        case_id=case.case_id, risk=risk, action=action,
        scores=scores, context=ctx, insight=insight, invariant_notes=notes,
        precedents=precedents, assessment_mode=mode, fallback_reason=fallback_reason,
    )
