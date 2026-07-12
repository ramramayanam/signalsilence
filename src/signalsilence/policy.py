"""Risk policy: the v2 instruction-set invariants as enforceable code.

In the CustomGPT era these rules were *requests* to a language model.
Here they are *guarantees*: whatever the LLM's contextual judgment says,
the final risk/action classification passes through this deterministic
policy layer, and the invariants cannot be violated by a persuasive but
wrong model output. The audit trail (invariant_notes) records every rule
that fired.

Source of truth: prompts/v2_instruction_set.txt. Each rule below cites
the instruction it implements.
"""
from .schema import Action, ContextJudgment, Risk, SimilarityScores

STRONG_PHONETIC = 0.85   # "Phonetic similarity >= 0.85 counts as strong similarity"
STRONG_LEXICAL = 0.85
MODERATE = 0.70


def strong_similarity(s: SimilarityScores) -> bool:
    """'Strong similarity (lexical OR phonetic)' — dimensions never averaged."""
    return s.lexical >= STRONG_LEXICAL or s.phonetic >= STRONG_PHONETIC


def classify(s: SimilarityScores, ctx: ContextJudgment, same_class: bool):
    """Return (Risk, Action, notes) applying the v2 invariants in order.

    Invariants implemented:
      I1. Near-identical mark + same class -> HIGH.
      I2. Strong similarity + adjacent goods -> HIGH; MEDIUM must NOT be
          assigned; descriptive added wording must NOT reduce it; absence
          of behavioral signal must NOT reduce it.
      I3. Similar mark + strong behavioral signal -> HIGH.
      I4. Plausible affiliation -> action defaults to REVIEW (not ESCALATE)
          unless adverse intent is evident; risk may drop below HIGH.
      I5. Partial or high similarity + unrelated goods, no behavioral
          signal -> LOW ("similarity and risk are separate").
      I6. Otherwise moderate similarity + somewhat related goods -> MEDIUM.
    """
    notes = []
    adjacent = ctx.goods_adjacent or same_class

    # I4 affiliation carve-out is evaluated first for the ACTION, but it
    # does not silently erase similarity facts (enforcement rule: "always
    # state similarity truthfully").
    if ctx.plausible_affiliation and not ctx.behavioral_signal:
        notes.append("I4: plausible affiliation -> default action REVIEW")
        risk = Risk.REVIEW if strong_similarity(s) and adjacent else Risk.LOW
        return risk, Action.REVIEW, notes

    if strong_similarity(s) and same_class:
        notes.append("I1: strong/near-identical mark + same class -> HIGH")
        return Risk.HIGH, Action.ESCALATE, notes

    if strong_similarity(s) and adjacent:
        notes.append("I2: strong similarity + adjacent goods -> HIGH (non-downgradable)")
        if ctx.added_wording_descriptive:
            notes.append("I2a: descriptive added wording ignored for risk reduction")
        if not ctx.behavioral_signal:
            notes.append("I2b: absence of behavioral signal does not reduce risk")
        return Risk.HIGH, Action.ESCALATE, notes

    if s.lexical >= MODERATE or s.phonetic >= MODERATE:
        if ctx.behavioral_signal:
            notes.append("I3: similar mark + behavioral signal -> HIGH")
            return Risk.HIGH, Action.ESCALATE, notes
        if adjacent:
            notes.append("I6: moderate similarity + related goods -> MEDIUM")
            return Risk.REVIEW, Action.REVIEW, notes
        notes.append("I5: similarity present but goods unrelated, no signal -> LOW")
        return Risk.LOW, Action.MONITOR, notes

    if strong_similarity(s) and not adjacent:
        notes.append("I5: high similarity but unrelated goods -> LOW (context override)")
        return Risk.LOW, Action.MONITOR, notes

    notes.append("default: weak similarity, no signals -> LOW")
    return Risk.LOW, Action.MONITOR, notes
