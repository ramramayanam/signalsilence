# SignalSilence — Current State (Phase 0 Audit)

Audit date: 2026-10-17 · Read-only audit, no application code changed.
Audited path: `Downloads/SignalSilence-v2-CC-Fable5/signalsilence/signalsilence`
Local commit: `bfddd5b` (2026-07-12, "SignalSilence v3: evals-first trademark triage")

> **Superseded baseline:** sections 1–9 describe the original audit of `bfddd5b`. As of Phase 0.5 the
> baseline is GitHub `main` `1657fbe`. See §10 for the reconciliation and its verified results.

---

## 1. Headline: the brief assumes a different kind of system

The brief is written for a web app with a frontend, a backend API, a database, migrations and authentication. **None of those exist.** SignalSilence today is:

- a **Python library** (`src/signalsilence/`, four modules, about 350 lines),
- a **single-page Streamlit demo** (`app.py`, 83 lines),
- an **offline eval script** (`evals/run_eval.py`),
- **12 pytest tests**,
- a **100-row synthetic CSV**.

There's no persistence, no case queue, no database, no API and no auth. The brief's database-safety, migration and API-contract rules have nothing to apply to yet. Building the review workspace (Workstream 1/2) means **adding a persistence layer for the first time**, which needs a product decision (see §9).

**The baseline is also ambiguous.** The GitHub remote (`origin/main` = `1657fbe`, 2026-08-28) is **4 commits ahead** of this local checkout:

| Commit | Content |
|---|---|
| `2d722bb`, `f733c53` | `governance/` docs (NIST AI RMF risk assessment, intake rubric) |
| `4612548` | `retrieval.py` (BM25 precedent RAG), `evals/judge.py` (LLM-as-judge), triage/eval changes, 9 new tests |
| `1657fbe` | README results update |

The same RAG/judge code also exists as `Downloads/signalsilence_rag_judge_update.zip`. The brief says "do not introduce a new RAG architecture", but RAG **already exists upstream**. I cloned the remote into a scratch folder: its 21 tests pass. Its default (no `--rag`) eval output is identical to local (75%). With `--rag` it scores 78% with high recall of 1.00.

---

## 2. Architecture and scoring flow

```
Case ─► similarity.py ─────► triage.py ───────────────► policy.py ─► TriageResult
        lexical (Jaro-Winkler)  context judgment:          invariants I1–I6     risk, action,
        phonetic (Metaphone     LLM (if ANTHROPIC_API_KEY)  -> Risk + Action     scores, context,
        + Soundex rung)         else offline heuristics     + invariant_notes    insight, notes
```

| Area | Current reality |
|---|---|
| Frontend | Streamlit (`app.py`): "Canonical cases" tab (5 hard-coded cases) plus a "Try your own" form |
| Backend/API | None; the app calls `triage()` in-process |
| Database/schema | None. Dataclasses in `schema.py`: `Case`, `SimilarityScores`, `ContextJudgment`, `TriageResult` |
| Risk categories | `Risk` enum: `low` / `review` / `high` (`review` is "MEDIUM" in the v2 prompt) |
| Separate action | `Action` enum: `escalate` / `review` / `ignore/monitor`, a **system recommendation** |
| Overall score | **None.** No weighted score and no weights. Classification is rule-based on thresholds |
| Thresholds | `STRONG_LEXICAL = STRONG_PHONETIC = 0.85`, `MODERATE = 0.70` (`policy.py:15-17`) |
| Rule order | I4 affiliation, then I1 strong + same class, then I2 strong + adjacent, then moderate band (I3 behavioral / I6 adjacent to REVIEW / I5 to LOW), then default LOW |
| LLM | Anthropic SDK, `SIGNALSILENCE_MODEL` env var, default `claude-sonnet-4-6`. It answers 4 boolean context facts only, never risk |
| Mode switch | LLM mode turns on **automatically** if `ANTHROPIC_API_KEY` is set (`triage.py:121-122`) |
| Audit trail | `invariant_notes` per result, shown in a Streamlit expander. Kept in memory only |
| Dependencies | `jellyfish`, `anthropic`, `streamlit`, `pytest` (unpinned) |

### Signals that actually exist vs. the brief's examples

| Brief signal | Status |
|---|---|
| Name similarity | ✅ Lexical, Jaro-Winkler with segmentation and core-token handling |
| Phonetic | ✅ **Already exists and already drives classification** (Workstream 4.1 assumes it doesn't) |
| Semantic similarity | ❌ `SimilarityScores.semantic` field exists but is **never populated** (always `None`) |
| Class overlap | ⚠️ A **dataset input flag** (`goods_class_overlap`), not computed. The protected mark's class isn't modeled at all |
| Goods/services similarity | ❌ None. Offline "adjacency" is a class-set + keyword heuristic hard-coded around class 025 |
| Behavioral signal | ✅ `recent_filing_count >= 10` (offline) |
| Affiliation / descriptive wording | ✅ Booleans (LLM or heuristic) |

### Source information available per case

The data has: `case_id`, protected mark, candidate mark, candidate class, goods text, applicant name, owner entity type, `source_type` (all `synthetic`).

**Not available:** filing date, application/serial number, protected-mark owner, protected-mark class/goods, source link, last-updated time. I won't fabricate these.

---

## 3. Tests and eval: run results

| Run | Result |
|---|---|
| `pytest tests/` (local) | **12 / 12 passed** (0.17 s, Python 3.14.4, pytest 9.1.1) |
| `evals/run_eval.py` (offline) | **Matches the README exactly:** 75% accuracy, low recall 1.00, high recall 0.90, review recall 0.23, 2 high→low misses (case_015, case_019) |
| Remote `origin/main` in a scratch clone | 21 / 21 tests pass. Offline eval is identical; `--rag` gives 78% with high recall 1.00 |
| Streamlit app | Booted headless (Windows Anaconda, Streamlit 1.37.1) and its health check returned `ok`. I didn't click through the UI in a browser and took no screenshots |
| LLM mode | **Not run** (no API key; avoided a paid call) |

I ran tests with `PYTHONDONTWRITEBYTECODE=1 -p no:cacheprovider`, so the repo wasn't touched.

### Baseline outputs of the 5 canonical demo cases (offline, captured as a regression reference)

| Case | Risk / Action | Lex | Phon | Rule fired |
|---|---|---|---|---|
| LULULEMON vs LULULEMMON | high / escalate | 0.98 | 1.00 | I1 |
| NIKE vs NIKKE (18 filings) | high / escalate | 0.95 | 1.00 | I1 (**not** I3 behavioral) |
| BATA vs BAATA LACES | high / escalate | 0.88 | 1.00 | I2, I2a, I2b |
| LULULEMON vs LULULIME (juice bar) | low / monitor | 0.90 | 0.85 | I5 |
| PHISH vs FISH | low / monitor | 0.78 | 1.00 | I5 |

---

## 4. What works well and should be preserved

1. **The policy layer as code.** `policy.classify` is deterministic, ordered, cites its rules, and the LLM can't override it. This is the core design asset.
2. **The LLM fence.** The model returns 4 structured booleans and never a risk level.
3. **Deterministic similarity:** reproducible, free, no network.
4. **Offline mode.** The whole pipeline, eval and demo run with no API key and no cost.
5. **The eval harness.** It already reports a confusion matrix, per-label precision/recall and high-risk false negatives (partly covers Workstream 5).
6. **Honest README.** Its numbers match the code, and its limitations are stated plainly.
7. **Label provenance** (`source_type=synthetic`) is already in the dataset.
8. **The legal disclaimer** is in the UI caption.
9. **The canonical demo cases** and their current outputs (table above).

---

## 5. Fragile areas and regression risks

| # | Risk | Where |
|---|---|---|
| F1 | **Output depends on the environment.** Setting `ANTHROPIC_API_KEY` silently switches app, eval and `triage()` to LLM mode with different results. Baseline regression tests must pin `use_llm=False`. | `triage.py:121` |
| F2 | **Rule order is load-bearing.** I4 runs before I1, and I1 before I3. Reordering changes outputs (for example, NIKKE fires I1, not the behavioral rule its demo label advertises). | `policy.py:46-78` |
| F3 | Behavioral rule I3 is only reachable in the moderate band when the strong rules don't fire. It can't escalate a strong but non-adjacent mark. | `policy.py:63-66` |
| F4 | **The "class overlap" input is inconsistent with the class column.** Class 009/041 rows have `True` and some class 025 rows have `False` (for example, case_024 LULUNOVA/running shorts). Policy treats this flag as "same class" for I1. Any UI that displays "Class overlap: Yes" will be showing this flag. | data, `policy.py:51` |
| F5 | No protected-mark class or goods in the model, so real class overlap can't be computed today. | `schema.py` |
| F6 | LLM call errors (network, auth, rate limit) are **not caught**: only JSON parse errors fall back. App and eval would crash mid-run. | `triage.py:82-98` |
| F7 | The "fail toward caution" comment is inaccurate: the fallback uses offline heuristics, which aren't more cautious. | `triage.py:110` |
| F8 | Offline affiliation heuristic: an applicant name containing the protected word (for example "Lululemon Knockoffs LLC") is treated as **affiliated**, which caps risk at REVIEW. An adversarial name downgrades risk. | `triage.py:65-68` |
| F9 | Eval loader ignores `recent_filing_count` (the CSV has no such column), so the behavioral signal never fires in evals. | `run_eval.py:28-40` |
| F10 | Unpinned dependencies. Local Python is 3.14. Two environments are in play: WSL `python3` has jellyfish and pytest but no streamlit; Windows Anaconda has streamlit and jellyfish but no anthropic. | `requirements.txt` |
| F11 | Streamlit state: the result block is shared below both tabs. A custom-case result shows only on the button-press rerun and reverts to the canonical case on any later interaction. Adding pages or state around this needs care. | `app.py:39-60` |
| F12 | The working tree shows 2 modified files (`data/synthetic_cases.csv`, `prompts/v2_instruction_set.txt`), but they are **line-ending-only (CRLF) changes**: `git diff -w --ignore-cr-at-eol` is empty. Harmless, but they'll pollute diffs and commits. | git |

---

## 6. Places where the code differs from its own docs (noted, not fixed)

- **Phonetic algorithm.** The README and docstrings say "Double Metaphone". The code uses `jellyfish.metaphone` (original Metaphone) plus a **Soundex** match for the 0.85 rung, not a secondary-key match (`similarity.py:48-75`).
- **Unreachable branch.** `policy.py:73-75` ("I5: high similarity but unrelated goods… context override") can never execute, because any strong score is already caught by the `>= MODERATE` branch above it. So the v2 enforcement rule "explicitly say 'high similarity'" is never emitted. `test_high_similarity_unrelated_goods_is_low` passes only because it asserts the weak substring `"similarity"`.
- The dataset's precomputed similarity scores differ from recomputed ones by a mean of 0.23. This is intentional (the README says they aren't trusted) but worth knowing for any "dataset vs. system" display.
- `lexical_similarity`'s core-token rule is asymmetric: it only splits the candidate mark.

Fixing any of these would change outputs or docs, so each needs approval first.

---

## 7. Mapping the brief onto reality

| Brief item | Reality | Implication |
|---|---|---|
| "Low / Review / High" | ✅ exists (`Risk`) | Reuse as is |
| "Overall score, if available" | ❌ none | Show the separate signals; don't invent a score |
| "Don't change scoring weights" | No weights; thresholds plus rule order | Freeze thresholds and rule order with regression tests |
| Review state (Unreviewed/Confirmed/…) | ❌ none | New |
| "Escalate" as an analyst decision | ⚠️ `Action.ESCALATE` already means the **system's** recommendation | Needs distinct naming in the UI and data |
| Audit trail | Partial (`invariant_notes`, not persisted) | Persist alongside decisions |
| Rule/threshold version | ❌ none | A `POLICY_VERSION` constant would be additive |
| Model/version | Env var plus default model id | Record what was used (`offline` or model id) |
| Reviewer identity | ❌ no auth | Free-text name or "local user" |
| Database / migrations | ❌ none | Choose a store (decision) |
| Workstream 4.1 phonetic | Already exists and is in scoring | Re-scope (maybe doc fix plus an evidence display only) |
| Workstream 4.2 goods/services | Not present; protected-mark goods unknown | Needs protected-mark goods input |
| Workstream 5 eval | ~60% there | Add FPR, baselines, label provenance |
| "Don't introduce RAG" | RAG already exists on GitHub `main` | Depends on the baseline decision |

---

## 8. Untouched

No application code, data, tests or git state changed. The only file added is this `CURRENT_STATE.md`. The remote comparison clone lives in the session scratchpad, outside the repo.

## 9. Decisions needed before Phase 1

1. **Baseline:** local `bfddd5b`, or GitHub `main` `1657fbe` (adds RAG, judge and governance)?
2. **Persistence for reviews and audit:** none exists. Options: SQLite (stdlib, single file, additive), an append-only JSONL log, or something else.
3. **Queue source:** use the 100 synthetic CSV cases plus the 5 canonical cases as "incoming filings"?
4. **Missing source fields** (filing date, application ID, link): show "not available", or add clearly labeled synthetic columns?
5. **Naming:** how to separate the system's `escalate` recommendation from the analyst's "Escalate" decision.
6. **The doc/code mismatches in §6:** leave as is, fix docs only, or fix code (output-changing, so tests come first)?

---

## 10. Phase 0.5: baseline reconciliation (2026-10-17)

### What was done

| Step | Result |
|---|---|
| Line-ending changes (`data/synthetic_cases.csv`, `prompts/v2_instruction_set.txt`) | Verified **CR-only**: identical to HEAD after stripping `\r` (101 and 169 lines, every line differed only by a trailing CR), and `git diff --ignore-cr-at-eol` was empty. Backed up to the session scratchpad, then discarded with `git restore`. Nothing was committed. |
| Fetch | `origin/main` = `1657fbe` |
| Local `main` | Fast-forwarded `bfddd5b` → `1657fbe` (no local commits existed) |
| Feature branch | `phase1/analyst-review-workspace`, created from `origin/main` `1657fbe`. Upstream deliberately **unset**, so a bare `git push` can't target `main`. |
| ZIP | Not used. The `signalsilence_rag_judge_update.zip` contents are byte-identical to the files already on GitHub `main` |

### Verification on baseline `1657fbe` (offline, `ANTHROPIC_API_KEY` unset)

- `pytest tests/`: **21 / 21 passed** (12 policy, 9 retrieval and judge).
- `evals/run_eval.py` (default, no retrieval): **unchanged.** 75% accuracy, confusion `[[50,0,0],[15,7,8],[2,0,18]]`, 2 high→low misses.
- `evals/run_eval.py --rag`: 78% accuracy, confusion `[[50,0,0],[10,8,12],[0,0,20]]`, 0 high→low misses.
- **Field-by-field regression check.** I compared old `bfddd5b` against new `1657fbe` across the 5 demo cases plus 100 eval cases: risk, action, lexical, phonetic, semantic, all 4 context facts, rationale, insight and invariant notes. **0 of 105 cases differ.**
- The 5 demo-case outputs match the §3 table exactly.

### Retrieval functionality present (all opt-in; default behavior is no retrieval)

| Capability | How it's enabled | Default |
|---|---|---|
| `PrecedentIndex` BM25 precedent retrieval (`src/signalsilence/retrieval.py`) | `triage(case, retriever=PrecedentIndex(...))`, or `run_eval.py --rag` | **Off.** `retriever=None` means no retrieval |
| Dense-embedding backend | `SIGNALSILENCE_RETRIEVAL=embedding` plus `sentence-transformers` (not in requirements) | Off. BM25 is the backend when retrieval is on |
| Offline precedent adjacency vote | With retrieval on, at least 2 of the top 3 precedents labeled review/high can turn `goods_adjacent` False→True (never True→False) | Off |
| Precedents in the LLM prompt | With retrieval on in LLM mode, prompt contains "none available" when off | Off |
| `TriageResult.precedents` | Always present; empty list when retrieval is off | `[]` |
| LLM-as-judge (`evals/judge.py`) | `run_eval.py --judge audit|rationale`; needs an API key; grades explanations only | Off |

`app.py` doesn't use retrieval. The precedent corpus is the labeled synthetic dataset, so it's an eval-time capability, not a production precedent store.

### Discrepancies and risks found during reconciliation

- **R1. GitHub `main` tracks a duplicate folder and Windows metadata:** `signalsilence_rag_judge_update/`, the `.zip` itself, and 8 `*:Zone.Identifier` files. Consequence: a **bare `pytest` from the repo root fails collection** (3 errors), because the duplicate folder's partial `src/` shadows the package. The documented command `pytest tests/` works. Removing these would be cleanup that isn't required for the feature, so it's **not done**; it needs approval.
- R2. `__pycache__` contains `.pyc` files regenerated during this session (gitignored, harmless).
- All Phase 0 fragile areas (F1–F12, §5) and code/doc mismatches (§6) still apply unchanged on `1657fbe`.

### Documentation-only corrections identified (not applied)

| Where | Correction (no behavior change) |
|---|---|
| `README.md`, `similarity.py` module docstring | "Double Metaphone" → "Metaphone (plus Soundex rung)" |
| `similarity.py` `phonetic_similarity` docstring | 0.85 rung is a **Soundex** match, not a "primary of one matches secondary of the other" match |
| `triage.py:110` comment | The fallback is offline heuristics, not "toward caution" |
| `app.py` NIKKE label | Says "behavioral signal", but I1 fires; label or narrative only |

### Suspected logic defects (proposed regression tests only, not written)

| ID | Defect | Proposed failing test |
|---|---|---|
| D1 | `policy.py` "high similarity … context override" branch is unreachable, so the v2 rule "explicitly say 'high similarity'" is never emitted | `classify(lex=0.90, phon=0.85, not adjacent)` notes contain `"high similarity"`; currently fails |
| D2 | Offline affiliation: an applicant name containing the protected word is treated as affiliated, capping risk at REVIEW | Applicant "Lululemon Knockoffs LLC", LULULEMMON, class 025 → expect HIGH; currently REVIEW |
| D3 | Eval loader drops `recent_filing_count` | Not a scoring defect; the dataset lacks the column |
| D4 | Non-JSON LLM errors (network or auth) aren't caught | Mock client raises → expect offline fallback; currently raises |

Fixing D1 changes note text only. Fixing D2 or D4 could change outputs. Each needs approval.

### Product decisions recorded for Phase 1 (not yet implemented)

- Review and audit persistence: **SQLite**. The DB file must be gitignored and never committed.
- Analyst queue: **the 5 demo cases**. The 100-row CSV stays an evaluation dataset.
- Missing filing/source metadata: omitted or shown as **"Not available"**, never fabricated.
- Analyst decisions: **Confirm Flag / Dismiss Flag / Refer for Legal Review**, kept separate from the system's `Escalate` recommendation (`Action`).
