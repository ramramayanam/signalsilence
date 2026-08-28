"""Core data types for SignalSilence.

Design principle: every field an AI judgment consumes or produces is
explicit and typed. No hidden state, no free-form blobs in the pipeline.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Risk(str, Enum):
    LOW = "low"
    REVIEW = "review"  # a.k.a. MEDIUM in the v2 instruction set
    HIGH = "high"


class Action(str, Enum):
    ESCALATE = "escalate"
    REVIEW = "review"
    MONITOR = "ignore/monitor"


@dataclass
class Case:
    """One trademark comparison: a protected mark vs. a new filing."""
    case_id: str
    protected_mark: str
    candidate_mark: str
    candidate_class: str
    candidate_goods: str
    applicant_name: str
    owner_entity_type: str  # "individual" | "corporation"
    goods_class_overlap: bool
    # Optional precomputed scores (dataset era). If absent, similarity.py fills them.
    string_similarity_score: Optional[float] = None
    phonetic_match_score: Optional[float] = None
    # Behavioral signal: filings by this applicant in the recent window, if known.
    recent_filing_count: Optional[int] = None
    ground_truth_label: Optional[str] = None


@dataclass
class SimilarityScores:
    """Three independent similarity dimensions (v2 rule: never blindly averaged)."""
    lexical: float          # Jaro-Winkler, deterministic
    phonetic: float         # Double Metaphone agreement, deterministic
    semantic: Optional[float] = None  # LLM-assisted; None in offline mode


@dataclass
class ContextJudgment:
    """LLM-assisted (or heuristic) contextual assessment of a case."""
    goods_adjacent: bool          # commercially adjacent per the v2 framework
    added_wording_descriptive: bool  # e.g. "LACES" in "BAATA LACES"
    plausible_affiliation: bool   # applicant may be related to the mark owner
    behavioral_signal: bool       # e.g. high filing velocity
    rationale: str = ""


@dataclass
class TriageResult:
    case_id: str
    risk: Risk
    action: Action
    scores: SimilarityScores
    context: ContextJudgment
    insight: str = ""
    invariant_notes: list = field(default_factory=list)  # policy enforcement audit trail
    precedents: list = field(default_factory=list)  # retrieved precedents (RAG), for audit
