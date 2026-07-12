"""Deterministic similarity scoring.

Design decision: lexical and phonetic similarity are computed with
classical algorithms (Jaro-Winkler, Double Metaphone), not an LLM.
They are cheap, reproducible, testable, and explainable — an auditor can
re-run them and get the same number. The LLM is reserved for judgments
that genuinely require context (semantic similarity, goods adjacency).

This mirrors the original MVP design (n8n era): "Matching Engine:
Phonetic + String Distance ... AI or No-AI: No-AI."
"""
import re

import jellyfish


def _normalize(mark: str) -> str:
    """Uppercase, strip punctuation, collapse whitespace.

    'LULU LEMON' and 'LULULEMON' should compare on their letters;
    segmentation tricks are a known evasion pattern.
    """
    return re.sub(r"[^A-Z0-9 ]", "", mark.upper()).strip()


def lexical_similarity(mark_a: str, mark_b: str) -> float:
    """Jaro-Winkler similarity on normalized marks, in [0, 1].

    Jaro-Winkler over plain edit distance: it up-weights shared prefixes,
    and trademark knock-offs overwhelmingly preserve the prefix
    (LULULEMON -> LULULEMMON, NIKE -> NIKKE).
    """
    a, b = _normalize(mark_a), _normalize(mark_b)
    # Compare space-stripped forms to catch segmentation variants.
    fused = jellyfish.jaro_winkler_similarity(a.replace(" ", ""), b.replace(" ", ""))
    plain = jellyfish.jaro_winkler_similarity(a, b)
    # Core-mark rule (v2 instruction set): when a filing is a core mark plus
    # added wording ("BAATA LACES"), similarity is driven by the core token,
    # not diluted by the modifier. Compare each token of the longer mark
    # against the shorter mark and keep the best.
    token_best = max(
        (jellyfish.jaro_winkler_similarity(a.replace(" ", ""), tok) for tok in b.split()),
        default=0.0,
    )
    return round(max(fused, plain, token_best), 2)


def phonetic_similarity(mark_a: str, mark_b: str) -> float:
    """Phonetic similarity via Double Metaphone key agreement, in [0, 1].

    1.0  -> primary keys identical (sound-alike: LULULEMON / LULULEMMON)
    0.85 -> primary of one matches secondary of the other
    else -> Jaro-Winkler similarity of the primary keys (graded, not cliff-edged)

    The 0.85 rung is deliberate: the v2 instruction set treats
    phonetic >= 0.85 as "strong similarity", so a secondary-key match
    lands exactly at the policy threshold rather than above or below it.
    """
    a = _normalize(mark_a).replace(" ", "")
    b_tokens = _normalize(mark_b).split()
    # Core-mark rule: score against the best-matching token as well as the
    # fused whole, so added wording does not dilute phonetic similarity.
    b = max(
        [_normalize(mark_b).replace(" ", "")] + b_tokens,
        key=lambda t: jellyfish.jaro_winkler_similarity(jellyfish.metaphone(a), jellyfish.metaphone(t)),
    )
    pa, sa = jellyfish.metaphone(a), jellyfish.soundex(a)
    pb, sb = jellyfish.metaphone(b), jellyfish.soundex(b)
    if pa and pa == pb:
        return 1.0
    if (sa and sa == sb):
        return 0.85
    if pa and pb:
        return round(jellyfish.jaro_winkler_similarity(pa, pb) * 0.85, 2)
    return 0.0


def score_case(protected_mark: str, candidate_mark: str):
    """Convenience: both deterministic dimensions at once."""
    return (
        lexical_similarity(protected_mark, candidate_mark),
        phonetic_similarity(protected_mark, candidate_mark),
    )
