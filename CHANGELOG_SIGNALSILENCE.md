# SignalSilence changelog: enhancement round (from 2026-10-17)

Work is on branch `phase1/analyst-review-workspace`, based on GitHub `main` `1657fbe`.
**Scoring is unchanged throughout:** no thresholds, rule order, retrieval
behavior or default outputs were modified (verified on all 105 cases at every step).

## Phase 0: read-only audit
- Audited the repo against the implementation brief. Findings are in
  `CURRENT_STATE.md` (§1–9).
- Key mismatches with the brief:
  - there's no database, API, frontend framework or auth; it's a Streamlit plus Python library app;
  - there's no overall score (risk comes from rules plus thresholds);
  - phonetic similarity already exists;
  - semantic similarity is never populated;
  - the dataset's class-overlap flag is inconsistent.

## Phase 0.5: baseline reconciliation
- The baseline moved from local `bfddd5b` to GitHub `main` `1657fbe`, which adds
  BM25 precedent retrieval (opt-in), LLM-as-judge and governance docs.
- Discarded CRLF-only working-tree changes after verifying they were identical to HEAD.
- Created the feature branch, with its upstream unset so a plain push can't reach `main`.
- Commit `f6cd375`: added `CURRENT_STATE.md`.

## Phase 1: analyst review workspace
- `0c21937` **Hygiene.** Removed the duplicate `signalsilence_rag_judge_update/`
  folder, its ZIP and the Windows `Zone.Identifier` files (16 files, all duplicates
  of canonical content). Root-level `pytest` now works. Added `*:Zone.Identifier`
  to `.gitignore`.
- `d0cee48` Moved the 5 canonical demo cases verbatim from `app.py` into
  `src/signalsilence/demo_cases.py`. Added `tests/test_demo_cases.py`.
- `1954d11` Added `src/signalsilence/review_store.py`, an append-only SQLite decision
  log (`review_events`; triggers block UPDATE and DELETE). `reviews.db` is gitignored.
- `6ace28c` Added the `pages/1_Analyst_Review.py` Streamlit page:
  - the 5-case queue;
  - the system assessment, shown separately from the analyst decision (Confirm Flag /
    Dismiss Flag / Refer for Legal Review) and an optional note;
  - per-case decision history.
  - Missing metadata shows as "Not available".

## Phase 1.1: hardening and documentation
- Added `POLICY_VERSION = "rules-v1"` in `policy.py`. It's provenance only, and no
  logic changed.
- Review store schema v2: an additive, nullable `policy_version` column, plus
  `policy_version` in each decision snapshot. Existing v1 databases are upgraded in
  place with `ALTER TABLE ... ADD COLUMN`; old rows keep NULL (not recorded). The page
  shows the rules version.
- Reviewer identity is explicitly **not supported** (there's no auth). This is documented in
  the README and on the page.
- Added `tests/test_regression_baseline.py` and `tests/fixtures/regression_baseline.json`,
  which permanently pin the default outputs of all 105 cases. `--update` refuses to
  rewrite changed outputs unless `POLICY_VERSION` is bumped.
- Added the README "Analyst Review workspace" section, this changelog and `TEST_RESULTS.md`.

## Known issues deliberately left open (see `CURRENT_STATE.md` §10)
- **D1:** the "high similarity … context override" note is unreachable.
- **D2:** offline affiliation matching is too permissive (protected word in applicant name → REVIEW cap).
- **D3:** the eval loader drops filing count (the dataset has no such column).
- **D4:** LLM/API errors other than JSON parsing aren't caught.
