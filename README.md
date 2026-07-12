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
case ──> similarity.py ──> triage.py ──────────> policy.py ──> result
         (deterministic:    (context judgment:    (risk invariants
          Jaro-Winkler,      LLM w/ strict JSON,   as code + audit
          Double Metaphone)  or offline heuristic) trail)
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
- `evals/run_eval.py` — confusion matrix, per-label precision/recall, and the
  metric that matters most for triage: high-risk false negatives.
- `tests/test_policy.py` — the instruction set restated as 12 executable
  tests, each citing the rule it enforces.

## Results (offline mode, 100 labeled synthetic cases)

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
python -m pytest tests/            # 12 invariant tests
python evals/run_eval.py           # offline eval, no API key needed
python evals/run_eval.py --show-misses
streamlit run app.py               # interactive demo (5 canonical cases)

# Optional: LLM context judgment
export ANTHROPIC_API_KEY=...
python evals/run_eval.py
```

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
