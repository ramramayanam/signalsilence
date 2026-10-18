# SignalSilence changelog: enhancement round (from 2026-10-17)

Phases 0–1.2 were on branch `phase1/analyst-review-workspace` (based on `main` `1657fbe`,
merged as `f4e272b`). Phase 2 is on `phase2/decision-engine-hardening`.
**Thresholds (0.85 / 0.85 / 0.70), rule order and retrieval behavior are unchanged
throughout.** Phases 0–1.2 changed no decision output. Phase 2 made deliberate,
versioned decision-path fixes (`rules-v2`, `rules-v3`). Across the 105 baseline cases the
only changes are 9 rule-note strings; risk and action are identical. Verified at every step.

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

## Phase 1.2: Analyst Review UI polish (presentation only)
- `pages/1_Analyst_Review.py`: the page uses a wide layout with two columns.
  - **Left:** the case queue as a selectable list. Each entry shows the marks, a risk badge,
    the system recommendation, review status and last-reviewed time, under a summary line.
  - **Right:** the selected case.
    - A header shows system risk, system recommendation and analyst review status.
    - **System assessment** and **Analyst decision** sit in separate panels.
    - System values use red/orange/green/gray badges, and analyst status uses blue, so a
      system "Escalate" never looks like an analyst decision.
    - Each of the three unchanged decisions has a one-line explanation.
    - The history shows the latest decision first; all decisions and the stored snapshot
      stay accessible.
- Fixed a UI-only bug introduced by the new list: recording a decision changed the list's
  captions, which made Streamlit reset the selection to the first case. The selection is now
  kept in session state.
- `tests/test_review_page.py`: updated for the new layout. It now also checks that the page
  stays on the reviewed case after recording.
- No changes to scoring, policy, retrieval, review-store semantics, decision choices or the
  105 regression outputs.

## Phase 2: decision-engine hardening (`phase2/decision-engine-hardening`)
Each fix was done in order D3 → D4 → D2 → D1, with tests written first. Rationale and the
simulated impact of each are in `PHASE2_AUDIT.md`.

- `2a05dba` **Audit.** `PHASE2_AUDIT.md` gives root causes, smallest fixes and the
  simulated 105-case impact for D1–D4.
- `6a2dfd6` **D3: filing-volume evaluation plumbing.**
  - `evals/run_eval.py` `load_cases` now reads an optional `recent_filing_count` column
    (blank or missing → `None`) instead of dropping it. The current CSV has no such column,
    so the outputs are unchanged.
  - `tests/test_filing_volume.py` runs an 8-case synthetic slice through a CSV and the real
    loader:
    - counts 9 / 10 / 25, blank and 0;
    - I3 actually firing (strong and moderate similarity);
    - volume alone not escalating a dissimilar mark;
    - I1 masking the signal.
- `1b044f6` **D4: LLM failure handling and provenance.**
  - **Failures no longer crash.** Missing package, auth, rate limit, timeout, connection,
    other API errors and malformed responses fall back to the offline judgment, labelled
    `assessment_mode = "llm_fallback_offline"` with a type-based `fallback_reason`.
    Exception text is never stored.
  - **Risk and action on fallback:** risk is kept, MONITOR is raised to REVIEW, and REVIEW
    and ESCALATE are never lowered.
  - **Strict booleans:** facts must be JSON booleans or the strings `"true"` / `"false"`.
    `"false"` used to become True.
  - **Provenance:** `TriageResult` gains `assessment_mode` and `fallback_reason`. The
    Analyst Review page shows and records the mode that actually ran. Offline mode is
    unchanged and labelled `offline`.
- `f74af97` **D2: offline affiliation fix, `rules-v2`.**
  - **The change:** offline mode no longer infers affiliation from applicant-name text.
    `Case` has no explicit affiliation field, so offline affiliation is not established.
    Rule I4 still applies when LLM mode asserts affiliation.
  - **Effect on real inputs:**
    - "Lululemon Knockoffs LLC", "Nikesh Patel", "Batavia Shoe Supply" and "Official
      Athletic Wear LLC" go from REVIEW/REVIEW to HIGH/ESCALATE.
    - "Lululemon Fan Club" no longer has its action raised to REVIEW.
    - No baseline case is affected.
  - **Version:** `POLICY_VERSION` becomes `rules-v2`, now defined as covering the full
    deterministic decision path (offline heuristics plus policy rules).
- `f1119a9` **D1: high-similarity provenance fix, `rules-v3`.**
  - **The bug:** strong similarity always passed the moderate test first, so the
    "high similarity … (context override)" note was unreachable.
  - **The fix:** the I5 path now chooses its note by `strong_similarity`, and the dead branch
    is removed.
  - **Effect:** only rule-note text changes, in 9 baseline cases (`demo_4`, `demo_5`,
    `case_015`, `case_019`, `case_021`, `case_027`, `case_032`, `case_038`, `case_043`).
    Risk, action and insight are unchanged.
  - **Version:** bumped to `rules-v3` because rule notes are stored in decision provenance.
    The fixture and demo baseline were updated for the 9 notes. The test now requires the
    exact phrase "high similarity".

## Known follow-ups (recorded, not implemented)
- **LLM affiliation prompt:** the LLM prompt still asks the model to judge
  `plausible_affiliation` from the applicant name alone. It needs a separate review so LLM
  mode doesn't repeat the D2 error.
- **Fallback caching:** fallback results stay cached for the session. The Analyst Review page
  caches assessments per process, so a transient LLM failure stays a fallback until the
  cache clears or the app restarts.
- **Eval fallback counts:** in LLM mode, eval reporting doesn't summarize how many cases fell
  back, or why, so fallback cases (with raised actions) are mixed into the metrics.
- **Filing-volume window:** the time window is ambiguous. The threshold is
  `recent_filing_count >= 10`, but the UI says "last 12 months" and the NIKKE demo label says
  "30 days". A labelled filing-volume eval slice is also still deferred.
