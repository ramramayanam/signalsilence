# SignalSilence

**AI trademark triage that learns when to stay silent — built evals-first.**

Trademark monitoring tools are too loud: similarity-based alerting buries the one
filing that matters (a deliberate knock-off) under dozens that don't (a juice bar
that happens to rhyme with your brand). SignalSilence triages new filings into
**escalate / review / ignore-monitor** using a layered pipeline in which every
judgment is either deterministic and auditable, or LLM-assisted and fenced by
deterministic policy.

> Awarded **Best Ethical AI Approach**, Agentic AI Institute Pitch Day (2026),
> for the evaluation-driven, human-in-the-loop design.

## Design principles

1. **Deterministic where possible, LLM only where necessary.** Lexical and
   phonetic similarity are classical algorithms (Jaro-Winkler, Double
   Metaphone) — reproducible, testable, free. The LLM judges only four
   contextual questions the algorithms cannot: goods adjacency, descriptive
   wording, plausible affiliation, behavioral signal.
2. **The LLM does not decide risk.** It returns structured context facts;
   `policy.py` — the instruction-set invariants as code — makes the
   classification. A persuasive but wrong model output cannot move a risk
   level; only structured facts can. Every decision carries an audit trail of
   which invariants fired.
3. **Similarity and risk are separate, and similarity is never misstated.**
   A high-similarity mark in an unrelated market is truthfully reported as
   high-similarity, low-risk. The system is not allowed to distort its
   evidence to justify its conclusion.
4. **Evals are the product.** The repo centers on a 100-case labeled dataset
   and a harness that measures the pipeline against it. Every design claim
   below is a measured result, not an assertion.

## Architecture

```
                        retrieval.py (RAG)
                        precedent corpus, BM25
                        or dense embeddings
                              │ top-3 adjudicated precedents
                              ▼
case ──> similarity.py ──> triage.py ──────────> policy.py ──> result
         (deterministic:    (context judgment:    (risk invariants     │
          Jaro-Winkler,      LLM w/ strict JSON,   as code + audit     ▼ evals only
          Double Metaphone)  or offline heuristic) trail)        LLM-as-judge
                                                                 grades explanations,
                                                                 never classifications
```

- `src/signalsilence/similarity.py` — deterministic scoring, including the
  core-mark rule (added wording like "…LACES" does not dilute similarity).
- `src/signalsilence/policy.py` — the risk logic from the production
  instruction set, implemented as non-negotiable invariants (e.g. *strong
  similarity + commercially adjacent goods is HIGH and cannot be downgraded
  by descriptive wording or absence of behavioral signal*; *plausible
  affiliation defaults the action to REVIEW, not ESCALATE*).
- `src/signalsilence/triage.py` — orchestration; LLM context judgment with
  strict-JSON output and fail-toward-caution parsing, or a transparent
  offline heuristic mode (no API key required to run everything).
- `src/signalsilence/retrieval.py` — precedent retrieval (RAG): dual-mode
  (lexical BM25 by default — pure Python, deterministic, zero cost; optional
  dense embeddings via sentence-transformers). Retrieval feeds the context
  judgment only — it can never override a policy invariant — and evals use
  leave-one-out retrieval so a case never sees its own adjudication.
- `evals/run_eval.py` — confusion matrix, per-label precision/recall, and the
  metric that matters most for triage: high-risk false negatives.
- `evals/judge.py` — LLM-as-judge for *explanation quality*: classification
  stays graded against ground-truth labels (a deterministic grader beats a
  model wherever one exists); the judge grades what only a model can — whether
  each audit trail / rationale is faithful to the evidence. Three-dimension
  rubric (faithfulness, invariant citation, evidence integrity), strict JSON,
  a different model than the pipeline (no grading your own homework), and no
  write access: a judge score can flag a case for human review but can never
  change a classification.
- `tests/test_policy.py` — the instruction set restated as 12 executable
  tests, each citing the rule it enforces.
  
## Governance

This system ships with its own governance artifacts:
- [AI Intake & Risk-Tiering Rubric](governance/ai-intake-risk-tiering-rubric.md) — the program "front door" (NIST AI RMF, EU AI Act tiers)
- [Risk & Impact Assessment](governance/risk-impact-assessment-signalsilence.md) — completed NIST AI RMF-mapped assessment with agent registry entry and autonomy reclassification gates
## Results (offline mode, 100 labeled synthetic cases)

Without retrieval:

| | predicted low | predicted review | predicted high |
|---|---|---|---|
| **truth: low** (n=50) | **50** | 0 | 0 |
| **truth: review** (n=30) | 15 | **7** | 8 |
| **truth: high** (n=20) | 2 | 0 | **18** |

Accuracy 75% overall; `low` recall 1.00 (zero false alarms from the noise
class — the "silence" in SignalSilence); `high` recall 0.90.

**The interesting finding is the two dangerous misses.** Both are
high-similarity marks filed in *different classes but commercially adjacent
markets* (yoga instruction; online activewear retail). The offline keyword
heuristics cannot see that adjacency — which is precisely the contextual
judgment the architecture reserves for the LLM layer. The eval doesn't just
score the system; it locates the boundary between what determinism handles
and where an LLM earns its cost. Run with `ANTHROPIC_API_KEY` set to measure
the LLM-context configuration on the same cases.

With retrieval (`--rag`, BM25, leave-one-out):

| | predicted low | predicted review | predicted high |
|---|---|---|---|
| **truth: low** (n=50) | **50** | 0 | 0 |
| **truth: review** (n=30) | 10 | **8** | 12 |
| **truth: high** (n=20) | 0 | 0 | **20** |

Accuracy 78%; `high` recall 0.90 → **1.00** — **precedent retrieval recovers
both dangerous misses** — while `low` recall stays 1.00 (the zero-false-alarm
guarantee is preserved). Both recovered cases pattern-match to previously
adjudicated filings with similar goods wording: the nearest precedents were
decided above `low`, which is evidence of commercial adjacency the keyword
heuristics could not see. The honest trade-off: a few more borderline
`review` cases now escalate to `high` (precision 0.69 → 0.62) — over-caution,
the cheap error in triage, and exactly the failure direction the product
chooses on purpose.

## Results (LLM context judgment + RAG, live run)

With `ANTHROPIC_API_KEY` set (context model: claude-sonnet-4-6, retrieved
precedents grounding the prompt), measured on the same 100 cases:

| | predicted low | predicted review | predicted high |
|---|---|---|---|
| **truth: low** (n=50) | **50** | 0 | 0 |
| **truth: review** (n=30) | 8 | **9** | 13 |
| **truth: high** (n=20) | 0 | 0 | **20** |

Accuracy 79%. Both safety guarantees hold with the live model in the loop:
`low` recall 1.00 (zero false alarms) and `high` recall 1.00 (zero dangerous
misses). `review` recall improves to 0.30 vs. 0.27 offline+RAG, with the
same deliberate over-caution pattern on borderline cases. The honest
finding: on this synthetic set, the LLM layer's marginal gain over
offline+RAG is real but modest — the point of measuring it rather than
assuming it. Real-world goods descriptions are far messier than the
synthetic ones, which is where contextual judgment is expected to earn
more of its keep (see Limitations).

### LLM-as-judge (explanation quality, live run)

A different model (claude-haiku-4-5) graded the pipeline's audit trails
against the evidence — faithfulness, invariant citation, and evidence
integrity, scored 1-5 with strict JSON (sample of 5 cases):

| dimension | mean |
|---|---|
| faithfulness | 4.80 / 5 |
| invariant citation | 5.00 / 5 |
| evidence integrity | 4.80 / 5 |
| flagged for human review | 0 / 5 |

Classification correctness is never judge-graded — ground-truth labels
handle that above. The judge grades only what a deterministic grader
cannot: whether each explanation is faithful to its evidence. Judge
scores can flag a case for human review but can never change a
classification.

The dataset's precomputed similarity scores were also NOT trusted: the
pipeline recomputes similarity deterministically, and the eval compares
against ground-truth labels only.

## Two prompt eras (project history)

The system evolved through measured iteration, preserved in `prompts/`:

- `v1_mep_system_prompt.txt` — the original Minimum Evaluable Product
  classifier (n8n + Supabase era, March 2026): a simple low/review/high
  prompt with conservative defaults.
- `v2_instruction_set.txt` — the production instruction set that grew out of
  v1's failure modes: independent similarity dimensions, the related-goods
  adjacency framework, non-downgradable risk invariants, the affiliation
  carve-out, behavioral signals.

This repo is the third era: v2's rules moved from *requested prompt behavior*
to *enforced code*, with the LLM confined to the judgments that genuinely
need it. The original n8n workflow design is documented in `legacy/`.

## Quick start

```bash
pip install -r requirements.txt
python -m pytest                   # 44 tests; the 4 UI tests are skipped without streamlit
python evals/run_eval.py           # offline eval, no API key needed
python evals/run_eval.py --rag     # + precedent retrieval (leave-one-out)
python evals/run_eval.py --show-misses
streamlit run app.py               # interactive demo + "Analyst Review" page in the sidebar

# Optional: LLM context judgment (RAG precedents ground the prompt)
export ANTHROPIC_API_KEY=...
python evals/run_eval.py --rag

# Optional: LLM-as-judge on explanation quality (needs API key)
python evals/run_eval.py --rag --judge audit --judge-sample 20
python evals/run_eval.py --rag --judge rationale --judge-sample 20

# Optional: dense-embedding retrieval backend
pip install sentence-transformers
SIGNALSILENCE_RETRIEVAL=embedding python evals/run_eval.py --rag
```

## Analyst Review workspace (prototype)

**SignalSilence recommends. The analyst decides.** The Analyst Review page
(`pages/1_Analyst_Review.py`) puts a human decision on top of the unchanged
triage pipeline.

- **Launch:** `streamlit run app.py`, then open **Analyst Review** in the sidebar.
- **Queue:** the 5 canonical demo cases, each with its system risk
  (Low / Review / High), system recommendation (Escalate / Review /
  Ignore-Monitor) and review status. The 100-case dataset stays an
  evaluation set and isn't in the queue.
- **Case view:** the system assessment comes first (lexical and phonetic
  scores, the four context facts, the rules that fired, and the rules
  version). It's kept separate from the analyst's decision. Source metadata
  the data doesn't contain (filing date, application number, owner, link)
  shows as *Not available* and is never filled in.
- **Analyst decisions:** **Confirm Flag**, **Dismiss Flag**, or **Refer for
  Legal Review**, plus an optional note. These are deliberately distinct from
  the system's *Escalate* recommendation.
- **Persistence:** a local SQLite file, `reviews.db` (gitignored; override it
  with `SIGNALSILENCE_REVIEW_DB`). It uses only Python's built-in `sqlite3`.
- **Append-only history:** each decision is a new row holding a snapshot of
  the system assessment at that moment and the rules version (`rules-v2`,
  `POLICY_VERSION` in `policy.py`). Database triggers block updates and
  deletes, so changing a decision keeps the earlier one, and current status
  is the latest decision.

Prototype limitations:
- **No authentication,** so no reviewer identity is recorded. Reviewer
  identity is deliberately unsupported rather than self-reported.
- **Single-user, local file.** There's no concurrency control or backup.
- **Demo data only.** The cases come from the canonical demo set, not a
  live filing feed.
- **LLM mode:** when `ANTHROPIC_API_KEY` is set, the assessment is an LLM
  judgment that can vary between sessions. The decision snapshot records
  the assessment the analyst actually saw.
- **Not legal advice.** The page is decision support for preliminary review.

**Regression guard:** `tests/test_regression_baseline.py` pins the default
(offline, no-retrieval) outputs of all 105 cases (5 demo plus 100 eval) to
`tests/fixtures/regression_baseline.json`. Any intentional change to the
outputs must bump `POLICY_VERSION` and regenerate the fixture with
`python tests/test_regression_baseline.py --update`, and the diff gets
reviewed in the commit.

## Human-in-the-loop design (production shape)

The MVP design (see `legacy/`) wraps this engine in two human gates:
a weekly suppression-review digest (catches false negatives) and an
approval gate before any drafted cease-and-desist is sent. Every AI
decision, human override, and final outcome is logged — the feedback
dataset that improves thresholds over time and constitutes the long-term
moat. Ingestion is decoupled: the demo runs on a static synthetic
snapshot; a production deployment swaps in the USPTO bulk-data loader
(`load_from_feed` interface) and a scheduled pull.

## Limitations (stated plainly)

- **Synthetic data.** All 100 cases are generated around a single protected
  mark (LULULEMON). Real USPTO filings are messier; per-mark results will
  not transfer without real-data evaluation.
- **Single-mark scope.** Multi-mark portfolios, house-mark families, and
  crowded-field analysis are out of scope.
- **Ground-truth labels are the author's**, not a trademark attorney's. The
  eval measures consistency with the design intent, not legal accuracy.
- **Offline adjacency heuristics are deliberately minimal** — they exist so
  the pipeline runs at zero cost, and their measured failures (above)
  motivate the LLM layer honestly.
- **No legal advice.** Output is an AI-assisted assessment for preliminary
  review and does not constitute legal advice.

## License

MIT
