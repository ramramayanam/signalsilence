# SignalSilence test results

Latest run: Phase 2 closeout, 2026-10-18, branch `phase2/decision-engine-hardening`
(after `f1119a9`, `POLICY_VERSION = "rules-v3"`).
All runs are offline (`ANTHROPIC_API_KEY` unset). LLM behavior is tested with a faked SDK;
no live or paid API calls were made.

## Test suite (bare `pytest` from the repo root)

| Environment | Result |
|---|---|
| Windows Anaconda, Python 3.12.7, streamlit 1.37.1, no `anthropic` | **97 passed, 1 skipped** (real-SDK exception test needs `anthropic`) |
| WSL `python3`, Python 3.14.4, `anthropic` 1.2.0, no streamlit | **92 passed, 1 skipped** (`tests/test_review_page.py`: 6 UI tests need streamlit) |

| File | Tests | Covers |
|---|---|---|
| `test_policy.py` | 13 | v2 instruction-set invariants. Phase 2: the high-similarity test now requires the exact phrase "high similarity", plus a moderate-only negative test |
| `test_retrieval_and_judge.py` | 9 | BM25 retrieval, leave-one-out, judge parsing (unchanged) |
| `test_demo_cases.py` | 2 | the 5-case queue and its pinned outputs (demo_4 and demo_5 notes updated for rules-v3) |
| `test_regression_baseline.py` | 2 | all 105 default outputs vs. the fixture; fixture matches `POLICY_VERSION` |
| `test_review_store.py` | 15 | schema and re-init, snapshot, status, history kept on change, notes, append-only triggers, vocabulary, missing data, DB path, gitignored DB, `policy_version` recorded, v1 → v2 schema upgrade |
| `test_review_page.py` | 6 | Streamlit AppTest: queue and summary, system vs. analyst styling and labels, recording a decision, empty submit, **fallback shown and recorded as `llm_fallback_offline`**, offline recorded as `offline` |
| `test_filing_volume.py` | 11 | **D3:** loader reads, or omits, `recent_filing_count`; 8-case slice: counts 9 / 10 / 25, blank, 0, I3 firing, volume alone not escalating, I1 masking |
| `test_llm_fallback.py` | 26 | **D4:** `"false"`/`"true"` parsing; 8 malformed responses; auth, permission, connection, timeout, rate-limit, API and no-key failures; missing package; real SDK classes; no secret leakage; LOW/MONITOR → LOW/REVIEW; REVIEW and ESCALATE not lowered; offline unchanged; fallback mode in the decision record |
| `test_affiliation.py` | 14 | **D2:** knock-off-style applicant names not affiliated; rules-v2+ risk/action for 5 bad and 1 normal applicant; LLM-asserted affiliation still applies I4; version is current |

All tests that touch the database use a temporary SQLite file.

I checked each new Phase 2 test against the code before its fix (in a scratch copy) to
confirm it catches the defect:
- D3: 6 of 11 fail;
- D2: 11 of 14 fail;
- D1: the tightened test fails.

## Evaluation (100 synthetic labeled cases)

| Run | Accuracy | Confusion (rows = truth low/review/high) | High→low misses |
|---|---|---|---|
| `run_eval.py` (default) | 75.0% | `[[50,0,0],[15,7,8],[2,0,18]]` | 2 |
| `run_eval.py --rag` | 78.0% | `[[50,0,0],[10,8,12],[0,0,20]]` | 0 |

Both outputs are byte-identical to the Phase 0.5 baseline (`1657fbe`), including after
rules-v2 and rules-v3.

## Output regression (105 cases = 5 demo + 100 eval)

- The committed fixture `tests/fixtures/regression_baseline.json` (`rules-v3`) **matches**.
- Change history against the original `1657fbe` baseline:
  - **rules-v2 (D2):** 0 cases changed; only the fixture's version metadata.
  - **rules-v3 (D1):** 9 cases changed `invariant_notes` only (the "high similarity …
    (context override)" wording). **Risk, action and insight are identical in all 105.**
- Fields pinned: risk, action, lexical, phonetic, semantic (always null), 4 context
  facts, rationale, insight, rule notes.
- Fields excluded as volatile: LLM output, retrieval precedents, timestamps.
- Final checks:
  - `POLICY_VERSION = "rules-v3"`;
  - thresholds 0.85 / 0.85 / 0.70;
  - rule order I4 → I1 → I2 → (I3, I6, I5) → default, unchanged.

## Manual / UI checks
- Phase 1: ran the app headless and captured screenshots with headless Chrome.
  - The queue rendered.
  - Recommendation and decision were separated.
  - History updated after a decision.
- A throwaway database in the Windows temp folder was used, so no `reviews.db` was
  created in the repo.
- Phase 1.2: re-checked the polished page at 1600 px, before and after sample decisions.
  - The two-column layout and badges render.
  - The latest note appears in full in the "Latest decision" box.
  - Found and fixed: the queue selection used to reset after recording.
- Phase 2: the fallback warning and provenance are covered by AppTest. No new screenshots.

## Known limitations of this testing
- Live LLM mode, the `--judge` evals and the embedding retrieval backend were not run (they
  need an API key or extra packages). LLM failure paths are tested with fakes only.
- UI tests run only where streamlit is installed. The real-SDK exception test runs only where
  `anthropic` is installed.
- Labels are synthetic and author-assigned; eval numbers measure consistency with the
  design, not legal accuracy.
- Open follow-ups (see `CHANGELOG_SIGNALSILENCE.md`):
  - the LLM affiliation prompt still needs review;
  - fallback results are cached for the session;
  - the eval doesn't summarize fallback counts;
  - the filing-volume time window is ambiguous.
