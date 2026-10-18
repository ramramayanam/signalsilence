# SignalSilence test results

Latest run: Phase 1.2 (UI polish), 2026-10-17, branch `phase1/analyst-review-workspace`.
Results are unchanged from Phase 1.1 except for the updated UI tests noted below.
All runs are offline (`ANTHROPIC_API_KEY` unset). LLM mode was not exercised.

## Test suite (bare `pytest` from the repo root)

| Environment | Result |
|---|---|
| Windows Anaconda, Python 3.12.7, streamlit 1.37.1 | **44 passed** |
| WSL `python3`, Python 3.14.4, no streamlit | **40 passed, 1 skipped** (`tests/test_review_page.py`: 4 UI tests need streamlit) |

| File | Tests | Covers |
|---|---|---|
| `test_policy.py` | 12 | v2 instruction-set invariants (unchanged) |
| `test_retrieval_and_judge.py` | 9 | BM25 retrieval, leave-one-out, judge parsing (unchanged) |
| `test_demo_cases.py` | 2 | the 5-case queue and its baseline outputs |
| `test_regression_baseline.py` | 2 | all 105 default outputs vs. the fixture; fixture matches `POLICY_VERSION` |
| `test_review_store.py` | 15 | schema creation and re-init, decision snapshot, status, history kept on change, notes, append-only triggers, vocabulary, missing data, DB path, DB gitignored and untracked, `policy_version` recorded, v1 → v2 upgrade |
| `test_review_page.py` | 4 | Streamlit AppTest: queue list and summary, system (gray) vs. analyst (blue) styling and decision labels, recording a decision (stays on the same case afterwards), empty submit. Updated in Phase 1.2 for the new layout |

All tests that touch the database use a temporary SQLite file.

## Evaluation (100 synthetic labeled cases)

| Run | Accuracy | Confusion (rows = truth low/review/high) | High→low misses |
|---|---|---|---|
| `run_eval.py` (default) | 75.0% | `[[50,0,0],[15,7,8],[2,0,18]]` | 2 |
| `run_eval.py --rag` | 78.0% | `[[50,0,0],[10,8,12],[0,0,20]]` | 0 |

Both outputs are byte-identical to the Phase 0.5 baseline (`1657fbe`).

## Output regression (105 cases = 5 demo + 100 eval)

- Committed fixture: `tests/fixtures/regression_baseline.json`. It **matches**.
- Independent check: the fixture equals a snapshot taken during Phase 0.5 from the
  untouched `bfddd5b` and `1657fbe` code. **0 of 105 cases differ** on every field.
- Fields pinned: risk, action, lexical, phonetic, semantic (always null), 4 context
  facts, rationale, insight, rule notes.
- Fields excluded as volatile: LLM output, retrieval precedents, timestamps.

## Manual / UI checks
- Ran the app headless (Phase 1) and captured screenshots with headless Chrome:
  - the queue rendered;
  - recommendation and decision were separated;
  - history updated after a decision.
- A throwaway database in the Windows temp folder was used, so no `reviews.db` was
  created in the repo.
- Phase 1.2: I re-checked the polished page with headless Chrome screenshots at 1600 px,
  before and after sample decisions (throwaway database).
  - It has the two-column layout, and the risk and status badges render.
  - The history table shows every column except the end of the note, which scrolls; the
    full latest note appears in the "Latest decision" box.
  - Found and fixed: recording a decision used to reset the queue selection to the first
    case. The recording test now covers this.

## Known limitations of this testing
- LLM mode, the `--judge` evals and the embedding retrieval backend were not run (they
  need an API key or extra packages).
- UI tests run only where streamlit is installed.
- Labels are synthetic and author-assigned; eval numbers measure consistency with the
  design, not legal accuracy.
