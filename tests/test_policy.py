"""The v2 instruction-set rules, restated as executable tests.

Each test cites the instruction it enforces. If a future change to
policy.py breaks one of these, the change violates the spec — that is
the point of writing the spec as tests.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence.policy import classify  # noqa: E402
from signalsilence.schema import Action, ContextJudgment, Risk, SimilarityScores  # noqa: E402
from signalsilence.similarity import lexical_similarity, phonetic_similarity  # noqa: E402


def ctx(adjacent=False, descriptive=False, affiliated=False, behavioral=False):
    return ContextJudgment(
        goods_adjacent=adjacent, added_wording_descriptive=descriptive,
        plausible_affiliation=affiliated, behavioral_signal=behavioral,
    )


# --- RISK LOGIC: HIGH ---

def test_near_identical_same_class_is_high():
    """'Near-identical mark (lexical OR phonetic) + same class' -> HIGH."""
    s = SimilarityScores(lexical=0.95, phonetic=1.0)
    risk, action, _ = classify(s, ctx(adjacent=True), same_class=True)
    assert risk == Risk.HIGH and action == Action.ESCALATE


def test_strong_phonetic_plus_adjacent_goods_must_be_high():
    """'Strong phonetic similarity (>=0.85) + commercially adjacent goods
    MUST be classified as HIGH risk unless clear affiliation signals exist.'"""
    s = SimilarityScores(lexical=0.70, phonetic=0.85)
    risk, _, _ = classify(s, ctx(adjacent=True), same_class=False)
    assert risk == Risk.HIGH


def test_medium_must_not_be_assigned_when_strong_and_adjacent():
    """'In cases of strong similarity + adjacent goods, MEDIUM must NOT be assigned.'"""
    s = SimilarityScores(lexical=0.88, phonetic=0.80)
    risk, _, _ = classify(s, ctx(adjacent=True), same_class=False)
    assert risk != Risk.REVIEW


def test_descriptive_wording_does_not_reduce_risk():
    """'Descriptive added wording has no material impact on risk when core
    similarity is strong' — the BAATA LACES rule."""
    s = SimilarityScores(
        lexical=lexical_similarity("BATA", "BAATA LACES"),
        phonetic=phonetic_similarity("BATA", "BAATA LACES"),
    )
    risk, _, notes = classify(
        s, ctx(adjacent=True, descriptive=True), same_class=False,
    )
    assert risk == Risk.HIGH, f"scores={s} notes={notes}"


def test_no_behavioral_signal_does_not_save_strong_adjacent():
    """'Absence of behavioral signal must NOT reduce risk in cases of
    strong similarity + adjacent goods.'"""
    s = SimilarityScores(lexical=0.90, phonetic=0.90)
    risk, _, _ = classify(s, ctx(adjacent=True, behavioral=False), same_class=False)
    assert risk == Risk.HIGH


def test_behavioral_signal_escalates_moderate_similarity():
    """'Similar mark + strong behavioral signal' -> HIGH (the NIKKE case:
    18 filings in 30 days)."""
    s = SimilarityScores(lexical=0.78, phonetic=0.75)
    risk, action, _ = classify(s, ctx(adjacent=True, behavioral=True), same_class=True)
    assert risk == Risk.HIGH and action == Action.ESCALATE


# --- RISK LOGIC: LOW / context override ---

def test_high_similarity_unrelated_goods_is_low():
    """'Partial OR high similarity + unrelated goods' -> LOW. Similarity and
    risk are separate (the LULULIME-juice-bar case)."""
    s = SimilarityScores(lexical=0.86, phonetic=0.88)
    risk, action, notes = classify(s, ctx(adjacent=False), same_class=False)
    assert risk == Risk.LOW and action == Action.MONITOR
    # Enforcement: similarity is still stated truthfully in the audit trail.
    assert any("high similarity" in n for n in notes), notes


def test_moderate_similarity_unrelated_goods_is_not_called_high():
    """Below the strong threshold the note must not claim 'high similarity'."""
    s = SimilarityScores(lexical=0.78, phonetic=0.60)
    risk, action, notes = classify(s, ctx(adjacent=False), same_class=False)
    assert risk == Risk.LOW and action == Action.MONITOR
    assert not any("high similarity" in n for n in notes), notes


# --- AFFILIATION carve-out ---

def test_plausible_affiliation_defaults_to_review_not_escalate():
    """'If the applicant plausibly appears affiliated ... default action:
    REVIEW unless adverse evidence exists.'"""
    s = SimilarityScores(lexical=0.95, phonetic=1.0)
    risk, action, _ = classify(s, ctx(adjacent=True, affiliated=True), same_class=True)
    assert action == Action.REVIEW
    assert risk != Risk.HIGH  # 'risk may be MEDIUM or LOW depending on context'


def test_affiliation_with_adverse_behavior_still_escalates():
    """Affiliation carve-out yields to 'clear adverse intent' (behavioral signal)."""
    s = SimilarityScores(lexical=0.95, phonetic=1.0)
    risk, action, _ = classify(
        s, ctx(adjacent=True, affiliated=True, behavioral=True), same_class=True,
    )
    assert risk == Risk.HIGH and action == Action.ESCALATE


# --- SIMILARITY module sanity ---

def test_segmentation_variant_scores_high_lexical():
    """'STARBUCKS' vs 'STAR BUCKS' — segmentation must not defeat matching."""
    assert lexical_similarity("STARBUCKS", "STAR BUCKS") >= 0.95


def test_sound_alike_scores_high_phonetic():
    assert phonetic_similarity("LULULEMON", "LULULEMMON") >= 0.85


def test_unrelated_marks_score_low():
    assert lexical_similarity("TESLA", "GOLDEN ORANGE") < 0.6  # JW floor for unrelated ~0.5; policy thresholds start at 0.70
