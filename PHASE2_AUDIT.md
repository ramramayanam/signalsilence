# Phase 2 audit: decision-engine known issues D1–D4

Audit date: 2026-10-18 · Branch `phase2/decision-engine-hardening` at `f4e272b` (= `main`).
Read-only: no code, tests, fixture or `POLICY_VERSION` changed.

**Method.** I read the code paths, then **simulated each candidate fix in memory** from a
scratch script (monkeypatching, no repo writes) and compared the results against the
committed 105-case fixture. LLM failure modes were simulated with a fake `anthropic` client.
No network calls were made.

## Summary

| | Root cause (one line) | Smallest fix | 105 fixture outputs changed | Risk/action can change | POLICY_VERSION |
|---|---|---|---|---|---|
| **D1** | Strong ⇒ moderate, so the moderate branch always returns first | Pick the I5 note text inside the moderate branch | **9 cases, note text only** | **No** | Bump needed (fixture changes) |
| **D2** | Substring match of the protected word (and 3 keywords) in the applicant name | Offline mode stops inferring affiliation | **0** | **Yes**, for real inputs (REVIEW → HIGH) | Bump recommended (deliberate; the guard won't force it) |
| **D3** | Eval loader never reads filing counts, and the CSV has no such column | Loader reads an optional `recent_filing_count` column; add tests | **0** | No | No |
| **D4** | Only JSON parsing is guarded; import/API errors propagate | Guard import + API call, fall back offline, label the fallback | **0** (fixture is offline) | LLM mode only, on failure | No |

---

## D1: the high-similarity explanation is unreachable

**Root cause.** `policy.py:69-81`. `strong_similarity` means lexical ≥ 0.85 **or** phonetic
≥ 0.85, and every strong case also satisfies the moderate test (`>= MODERATE`, 0.70) at line 69.
So any strong case that isn't caught by I4/I1/I2 enters the moderate block and returns at line 76/77
with `"I5: similarity present but goods unrelated, no signal -> LOW"`. The branch at lines 79-81
(`"I5: high similarity but unrelated goods -> LOW (context override)"`) is dead code. The v2
enforcement rule ("if similarity is high but risk is low → explicitly say 'high similarity'") is
therefore never met. `test_high_similarity_unrelated_goods_is_low` passes only because it
asserts the substring `"similarity"`.

**Smallest fix.** Inside the moderate block, at line 76, emit the "high similarity … context
override" note when `strong_similarity(s)` is true, and keep the existing note otherwise. Then
remove the dead branch at 79-81. Risk and action stay `LOW / MONITOR` in both cases.
*Not recommended:* moving the dead branch above line 69. That gives the same result, but it's
a rule-order change, which this round forbids.

**Tests first.**
- `classify(lex 0.90, phon 0.85, not adjacent, no signals)` → notes contain `"high similarity"`,
  risk LOW, action MONITOR.
- A moderate-only case (for example lex 0.78, phon 0.60) → keeps the "similarity present" note.
- Strengthen `test_high_similarity_unrelated_goods_is_low` to assert `"high similarity"`.
  This changes an existing test's assertion, so it needs your approval.

**Impact (simulated).** 9 of 105 fixture cases change **`invariant_notes` only**: `demo_4`,
`demo_5`, `case_015`, `case_019`, `case_021`, `case_027`, `case_032`, `case_038`, `case_043`.
**0 risk/action changes.** Offline `insight` is unchanged (it uses the non-empty rationale). In LLM
mode `insight` would change only when the model returns an empty rationale.

**POLICY_VERSION.** The fixture must be regenerated, and `--update` refuses to do that without a
bump. So **D1 requires a bump** under the mechanism we adopted, even though classification is
unchanged.

**Ambiguity.** Whether audit-text-only changes deserve a version bump is a convention choice.
The current guard treats any pinned-field change as versioned, which I recommend keeping for
auditability.

---

## D2: affiliation matching is too permissive

**Root cause.** `triage.py:72` and `78-81` (offline mode only):
```python
core = re.sub(r"[^A-Z]", "", case.protected_mark.upper())
affiliated = any(w in (case.applicant_name or "").lower()
                 for w in (core.lower(), "subsidiary", "franchise", "official"))
```
Two problems:
- It's a plain **substring** test.
- **Containing the brand name is treated as evidence of affiliation**, when it's equally typical
  of knock-offs.

Policy then applies **I4 first** (`policy.py:52-55`). Unless there's a behavioral signal, this
**caps risk at REVIEW and forces action REVIEW**, so I1/I2 never run.

**Simulated examples (current → with offline affiliation disabled):**

| Applicant | Case | Now | Fixed |
|---|---|---|---|
| Lululemon Knockoffs LLC | LULULEMMON, 025 | review / review (I4) | **high / escalate (I1)** |
| Nikesh Patel (*nike* ⊂ *nikesh*) | NIKKE, 025 | review / review (I4) | **high / escalate (I1)** |
| Batavia Shoe Supply (*bata* ⊂ *batavia*) | BAATA LACES, 026 | review / review (I4) | **high / escalate (I2)** |
| Official Athletic Wear LLC | LULULEMMON, 025 | review / review (I4) | **high / escalate (I1)** |
| Lululemon Fan Club | LULUBLOOM, 041 | low / **review** (I4) | low / monitor (I5) |

I4 can also *raise* the action on low-risk cases, as in the last row.

**Smallest fix (recommended).** Offline mode doesn't infer affiliation: `plausible_affiliation=False`.
Affiliation then comes only from LLM judgment, or in future from an explicit data field such as a
known owner/affiliate list, which the schema doesn't have today. This fails toward human review
of the potential conflict, which matches "precision first" and "don't invent facts".

*Alternatives considered:* whole-word matching (still flags "Lululemon Knockoffs LLC"), or
dropping only the brand-name test and keeping the keywords ("Official …" is equally adversarial).
Neither fixes the core problem.

**Tests first.**
- A unit test on `_offline_context` showing affiliation is False for the five applicants above.
- An end-to-end `triage(use_llm=False)` test showing "Lululemon Knockoffs LLC" + LULULEMMON/025 →
  HIGH/ESCALATE with I1.
- The existing policy I4 tests stay unchanged (the policy rule is fine; the input heuristic is the
  defect).

**Impact.** **0 of 105** fixture outputs change: no dataset or demo applicant matches the heuristic.
**Risk and action do change for real-world inputs** (above). LLM mode is unaffected by the code
fix, but the LLM prompt asks the same affiliation question from the applicant name alone and could
make a similar judgment. That's a separate, prompt-level item, not included here.

**POLICY_VERSION.** The fixture won't force a bump, because nothing pinned changes. I still
**recommend a deliberate bump**, since classification for some inputs changes. Ambiguity:
`POLICY_VERSION` is documented as covering `policy.py` rules, and D2 is in `triage.py`. I recommend
redefining it as the version of the **deterministic decision path** (policy plus offline context
heuristics), and adding the five D2 examples as pinned regression tests so the change is visible.

**Product decision needed.** Should offline mode ever claim affiliation without explicit owner
data? My recommendation is no. Encoding "contains the brand ⇒ affiliated" is close to a legal
judgment and isn't supported by evidence.

---

## D3: the filing-volume rule isn't exercised by evaluation

**Root cause.**
- `evals/run_eval.py:29-44` (`load_cases`) never sets `recent_filing_count`, and
  `data/synthetic_cases.csv` has **no such column**. Offline `behavioral = (count or 0) >= 10`
  (`triage.py:82`) is therefore always False for all 100 eval cases.
- In the demos, only `demo_2` (NIKKE, 18 filings) has `behavioral_signal=True`, but **I1 fires
  first**, so its notes never mention behavior. Its demo label "behavioral signal" overstates what
  the trail shows.
- Result: **I3 fires in 0 of 105 outputs.** The only coverage is the policy-level unit test
  `test_behavioral_signal_escalates_moderate_similarity`. The offline threshold (`>= 10`) has
  **no test at all**.

**Smallest fix.**
1. `load_cases` reads `recent_filing_count` as an optional int when the column exists and is
   non-empty, else `None`. This changes no output on today's CSV.
2. Add tests:
   - offline threshold boundary (9 → False, 10 → True, None → False);
   - an end-to-end `triage(use_llm=False)` case that reaches I3, for example LULULEMON vs
     LULUFLOW / class 009 / not same class / 15 filings → HIGH/ESCALATE with I3;
   - a loader test using a temporary CSV with and without the column.

**Impact.** **0** fixture changes, no risk/action change, **no version bump.**

**Product decision (separate).** Making the *eval* measure I3 needs labeled cases with filing
counts. Adding counts to the 100-row CSV, or a small separate behavioral slice, means authoring new
**synthetic** labels, which must be marked synthetic and approved. The demo label wording for
NIKKE is a doc-only follow-up.

---

## D4: LLM/API failures crash instead of degrading

**Root cause.** `triage.py:97-130`. Lines 98-117 (`import anthropic`, `Anthropic()`,
`messages.create`) are **outside** any `try`. Only `json.JSONDecodeError`, `KeyError` and
`TypeError` from parsing (lines 119-130) are caught.

**Simulated results (fake client, `demo_4`):**

| Failure | Current behavior |
|---|---|
| Rate limit (`AnthropicError` subclass) | **Crash** |
| Connection error | **Crash** |
| `anthropic` package not installed (true of the Windows Anaconda env) with `ANTHROPIC_API_KEY` set | **Crash** (`ImportError`) |
| Non-JSON reply | Falls back to offline; rationale reads `"offline heuristic judgment"`, **indistinguishable from normal offline** |
| JSON with string booleans (`"false"`) | `bool("false") == True`: **every fact flips to True**. demo_4 goes from LOW/MONITOR to **HIGH/ESCALATE** (D4b) |

**Related provenance gap (D4c).** On a silent fallback, the Analyst Review page still records
`assessment_mode = "llm context judgment (...)"`, because it derives the mode from the env var
rather than from what actually ran. The decision record would misstate provenance.

**Smallest fix.**
1. Guard `import anthropic` (catch `ImportError`) and the client/`create` call (catch
   `anthropic.AnthropicError`, the SDK base class that covers connection, timeout, rate-limit,
   auth and status errors). On failure, return `_offline_context(...)` with the rationale
   **prefixed** `"LLM unavailable (<ErrorType>); offline heuristic fallback"`.
2. D4b: accept only real JSON booleans (`isinstance(v, bool)`). Anything else is treated as a
   parse failure, which takes the same labeled fallback.
3. Label the existing parse-failure fallback the same way, and correct the "fail toward caution"
   comment.
4. D4c (needs approval, because it touches the UI file): the page should take `assessment_mode`
   from the result (detect the fallback prefix) instead of the env var. There's no schema change.

**Tests first** (no network: monkeypatch `anthropic.Anthropic` to a fake that raises real SDK
exception classes; `anthropic` 1.2.0 is installed in WSL Python):
- connection, rate-limit and auth errors → no exception, offline facts, labeled rationale;
- `ImportError` → same;
- string booleans → fallback, not all-True;
- valid JSON → unchanged behavior.

The tests must also run where `anthropic` isn't installed (skip or fake accordingly).

**Impact.** **0** fixture changes (the fixture is offline). LLM mode: risk/action change **only on
failure or malformed paths**, from crash or all-True to offline-equivalent. **No version bump.**

**Ambiguity / product decision.** "Fail toward caution": the offline fallback can be *less*
cautious than the LLM. For example, the two dangerous misses (`case_015`, `case_019`) are LOW
offline. A fallback **risk floor** (for example, minimum REVIEW when the LLM fails) would be a
policy change and needs your decision. I recommend the labeled fallback now and a decision on the
floor later. One open detail to verify against the SDK during implementation: whether
`Anthropic()` with a missing key raises an `AnthropicError` subclass.

---

## Recommended implementation order

1. **D3**: loader plus tests. Zero output change, no version change, lowest risk, and it adds the
   I3 and threshold coverage the other fixes benefit from.
2. **D4**: failure guard, strict booleans, labeled fallback. Zero offline change, no version change.
   D4c (page provenance) only if you approve the small UI change.
3. **D2**: disable offline affiliation inference, after your product decision. 0 fixture changes,
   but real-input risk/action changes.
4. **D1**: note fix, which regenerates the fixture (9 note-only changes).

Ship **D2 + D1 together under one bump to `rules-v2`**, with `POLICY_VERSION` redefined to cover
the deterministic decision path. The fixture regeneration happens once, with a reviewed diff
limited to those 9 notes. Each step: write tests first, then the change, then full suite, default
and `--rag` evals, and the fixture check.

## Decisions needed before implementing

1. **D2:** OK for offline mode to never infer affiliation?
2. **D1/D2:** bump to `rules-v2` and redefine `POLICY_VERSION` as the decision-path version?
3. **D1:** approve strengthening the existing `test_high_similarity_unrelated_goods_is_low` assertion?
4. **D4c:** approve the small Analyst Review change so recorded `assessment_mode` reflects an actual
   fallback?
5. **D4:** labeled offline fallback only, or also a minimum-REVIEW risk floor on LLM failure (a
   policy change)?
6. **D3:** author a small labeled synthetic behavioral eval slice now, or defer it?
