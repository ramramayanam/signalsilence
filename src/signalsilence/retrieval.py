"""Precedent retrieval (RAG layer).

When a new filing arrives, retrieve the most similar *previously
adjudicated* cases and feed them into the context judgment as grounding
evidence. In this repo the precedent corpus is the labeled synthetic
dataset; in a production deployment it is the firm's own adjudication
log — the same feedback dataset that the human-in-the-loop design
accumulates over time.

Design rules (mirroring the rest of the system):

1. **Retrieval feeds the context judgment, never the policy.** Retrieved
   precedents ground the goods-adjacency call (LLM mode) or vote on it
   (offline mode); `policy.py` invariants still make the classification.
   A precedent cannot override a non-downgradable rule.
2. **Dual-mode, like triage.** The default backend is lexical BM25 —
   pure Python, deterministic, zero dependencies, runs everywhere.
   An optional dense-embedding backend (sentence-transformers) can be
   enabled for semantic retrieval; the eval harness measures both.
3. **Leave-one-out in evals.** When evaluating case N, case N is
   excluded from its own retrieval — otherwise the ground-truth label
   leaks into the prediction.
"""
import math
import os
import re
from collections import Counter
from dataclasses import dataclass


@dataclass
class Precedent:
    """One retrieved prior adjudication, with its outcome."""
    case_id: str
    candidate_mark: str
    candidate_goods: str
    candidate_class: str
    label: str          # adjudicated outcome: low | review | high
    score: float        # retrieval similarity (backend-specific scale)


def _doc_tokens(goods: str, candidate_class: str, mark: str) -> list:
    """Tokenize a case for retrieval.

    Goods wording dominates (that is where adjacency lives), the NICE
    class is one token, and the mark contributes character trigrams so
    lookalike marks also pull together.
    """
    tokens = re.findall(r"[a-z0-9]+", (goods or "").lower())
    tokens.append(f"class_{str(candidate_class).zfill(3)}")
    m = re.sub(r"[^A-Z0-9]", "", (mark or "").upper())
    tokens.extend(m[i:i + 3].lower() for i in range(max(len(m) - 2, 0)))
    return tokens


class _BM25:
    """Minimal BM25 (Okapi), pure Python. Deterministic, dependency-free."""

    K1, B = 1.5, 0.75

    def __init__(self, docs: list):
        self.docs = [Counter(d) for d in docs]
        self.doc_len = [sum(d.values()) for d in self.docs]
        self.avg_len = (sum(self.doc_len) / len(self.doc_len)) if self.docs else 0.0
        df = Counter()
        for d in self.docs:
            df.update(d.keys())
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query_tokens: list, index: int) -> float:
        d, dl = self.docs[index], self.doc_len[index]
        s = 0.0
        for t in query_tokens:
            if t not in d:
                continue
            tf = d[t]
            denom = tf + self.K1 * (1 - self.B + self.B * dl / (self.avg_len or 1))
            s += self.idf.get(t, 0.0) * tf * (self.K1 + 1) / denom
        return s


class PrecedentIndex:
    """Retrieval index over adjudicated cases.

    backend: "bm25" (default) or "embedding". The embedding backend
    lazily imports sentence-transformers; if unavailable it raises with
    a clear message rather than silently degrading.
    """

    def __init__(self, cases, backend: str = None):
        self.backend = (backend or os.environ.get(
            "SIGNALSILENCE_RETRIEVAL", "bm25")).lower()
        self.cases = [c for c in cases if c.ground_truth_label]
        self._texts = [
            f"{c.candidate_mark} {c.candidate_goods} class {c.candidate_class}"
            for c in self.cases
        ]
        if self.backend == "embedding":
            self._model = self._load_embedder()
            self._vecs = self._model.encode(self._texts, normalize_embeddings=True)
        else:
            self._bm25 = _BM25([
                _doc_tokens(c.candidate_goods, c.candidate_class, c.candidate_mark)
                for c in self.cases
            ])

    @staticmethod
    def _load_embedder():
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise ImportError(
                "Embedding retrieval requires sentence-transformers: "
                "pip install sentence-transformers "
                "(or use the default BM25 backend)"
            ) from e
        return SentenceTransformer(
            os.environ.get("SIGNALSILENCE_EMBED_MODEL", "all-MiniLM-L6-v2"))

    def retrieve(self, case, k: int = 3, exclude_case_id: str = None) -> list:
        """Top-k precedents for a case; excludes the case itself in evals."""
        if self.backend == "embedding":
            q = self._model.encode(
                [f"{case.candidate_mark} {case.candidate_goods} "
                 f"class {case.candidate_class}"],
                normalize_embeddings=True)[0]
            scored = [(float(v @ q), i) for i, v in enumerate(self._vecs)]
        else:
            q = _doc_tokens(case.candidate_goods, case.candidate_class,
                            case.candidate_mark)
            scored = [(self._bm25.score(q, i), i)
                      for i in range(len(self.cases))]

        scored.sort(key=lambda t: (-t[0], self.cases[t[1]].case_id))
        out = []
        for score, i in scored:
            c = self.cases[i]
            if exclude_case_id and c.case_id == exclude_case_id:
                continue
            out.append(Precedent(
                case_id=c.case_id, candidate_mark=c.candidate_mark,
                candidate_goods=c.candidate_goods,
                candidate_class=str(c.candidate_class),
                label=c.ground_truth_label, score=round(float(score), 3)))
            if len(out) == k:
                break
        return out


def precedent_adjacency_vote(precedents: list, min_votes: int = 2) -> bool:
    """Offline-mode use of retrieval: do the nearest adjudicated
    precedents suggest the goods are commercially adjacent?

    A precedent votes "adjacent" if it was adjudicated above `low`
    (review/high both imply the goods relationship mattered) and it
    actually matched on content (score > 0). Requires `min_votes` of the
    retrieved set — a single noisy neighbor cannot flip the judgment.
    """
    votes = sum(1 for p in precedents if p.label in ("review", "high") and p.score > 0)
    return votes >= min_votes


def format_precedents_for_prompt(precedents: list) -> str:
    """Render precedents as grounding evidence for the LLM context prompt."""
    if not precedents:
        return "none available"
    lines = []
    for p in precedents:
        lines.append(
            f"- {p.candidate_mark} | class {p.candidate_class} | "
            f"{p.candidate_goods} | adjudicated: {p.label}")
    return "\n".join(lines)
