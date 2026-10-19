"""Governance register for the AI Governance page (static, descriptive data).

Kept as data so it can be tested: every ACTIVE control must cite evidence
that exists in this repository (a file, optionally a test function), and
regulatory rows must use the fixed instrument-type and applicability
vocabularies below. This is an engineering/governance aid, not a legal
determination: nothing here claims compliance or certification.
"""

STATUS_AS_OF = "2026-10-18"

ACTIVE, PROPOSED, FUTURE = "ACTIVE", "PROPOSED", "FUTURE"

INSTRUMENT_TYPES = ("Binding law", "Proposed / developing law", "International standard",
                    "Voluntary framework", "Internal policy")
APPLICABILITY = ("Design alignment", "Design alignment only", "Context-dependent",
                 "Potentially applicable", "Not applicable to current use", "Monitor")

# --- System & Purpose ------------------------------------------------------------

SYSTEM = [
    ("Purpose", "Preliminary trademark-conflict triage and prioritization for human review."),
    ("Decision role", "Decision support."),
    ("Final authority", "Human analyst."),
    ("System behavior", "The system recommends. It does not take enforcement or legal action."),
    ("Intended users", "Brand-protection / trademark-review analysts."),
    ("Current demo data", "Synthetic demonstration cases (hand-authored; not real filings)."),
    ("Intended production data source", "USPTO trademark records."),
    ("Live USPTO ingestion", "Not implemented in this demo."),
]

NOT_PROVIDED = ["Legal conclusions", "Enforcement decisions", "Employment decisions",
                "Healthcare decisions", "Credit, housing or insurance decisions"]

# --- Data & Lineage ----------------------------------------------------------------

FIELDS_USED = ["Protected mark", "Candidate mark", "Candidate class", "Goods/services text",
               "Applicant name", "Applicant entity type", "Same-class indicator",
               "Recent filing count (where provided)"]

TRANSFORMATIONS = ["Normalization", "Lexical similarity (Jaro-Winkler)",
                   "Phonetic similarity (Metaphone + Soundex)",
                   "Contextual assessment (offline heuristics, or LLM facts in LLM mode)",
                   "Deterministic policy rules (rules-v4)",
                   "Optional precedent retrieval, only where explicitly enabled"]

PROVENANCE_CAPTURED = ["Data source", "Source reference", "Assessment produced (UTC)",
                       "Decision recorded (UTC)"]

# --- Risk & Controls -----------------------------------------------------------------
# evidence: list of "path" or "path::test_name" references that must exist in the repo.

CONTROLS = [
    {"control": "No automated downstream action", "status": ACTIVE,
     "what": "The system only recommends; no code path sends notices, files actions or acts "
             "on a decision.",
     "evidence": ["pages/1_Analyst_Review.py", "src/signalsilence/triage.py"]},
    {"control": "System recommendation separated from analyst decision", "status": ACTIVE,
     "what": "Separate system and analyst panels and fields; the analyst vocabulary (Confirm "
             "Flag / Dismiss Flag / Refer for Legal Review) is distinct from the system's "
             "Escalate / Review / Monitor.",
     "evidence": ["src/signalsilence/review_store.py",
                  "tests/test_review_store.py::test_decision_vocabulary_is_distinct_from_system_action",
                  "tests/test_review_page.py::test_page_separates_recommendation_from_decision"]},
    {"control": "Append-only application-level decision history", "status": ACTIVE,
     "what": "SQLite triggers reject UPDATE and DELETE on decision events; a changed decision "
             "adds a new event.",
     "qualification": "Application-level append-only, not cryptographic tamper-proof storage: "
                      "anyone with access to the database file can alter it.",
     "evidence": ["src/signalsilence/review_store.py",
                  "tests/test_review_store.py::test_history_is_append_only"]},
    {"control": "Decision provenance captured with the decision", "status": ACTIVE,
     "what": "Each decision stores a snapshot of the system assessment and inputs; the Decision "
             "Provenance page shows it read-only.",
     "evidence": ["pages/2_Decision_Provenance.py",
                  "tests/test_decision_provenance.py::test_full_snapshot_available"]},
    {"control": "Assessment-produced time and source captured for new decisions", "status": ACTIVE,
     "what": "assessed_at and data_source are stored with each new decision.",
     "qualification": "Historical decisions may show \u2018Not recorded at decision time\u2019.",
     "evidence": ["tests/test_capture_provenance.py::test_new_offline_decision_stores_source_and_utc_assessed_at"]},
    {"control": "Policy versioning", "status": ACTIVE,
     "what": "The rules version (rules-v4) is stored with every decision.",
     "evidence": ["src/signalsilence/policy.py",
                  "tests/test_review_store.py::test_policy_version_is_recorded_on_each_event"]},
    {"control": "Prompt provenance", "status": ACTIVE,
     "what": "The context prompt version (context-prompt-v2) is stored for LLM assessments.",
     "evidence": ["tests/test_llm_affiliation.py::test_prompt_version_and_reported_model_recorded"]},
    {"control": "Model provenance", "status": ACTIVE,
     "what": "The model id reported by the API is stored for LLM assessments.",
     "evidence": ["tests/test_llm_affiliation.py::test_decision_snapshot_preserves_prompt_version_and_model"]},
    {"control": "Labelled LLM fallback", "status": ACTIVE,
     "what": "If the LLM is unavailable, the offline assessment is labelled llm_fallback_offline "
             "with a fallback reason, never presented as an LLM judgment.",
     "evidence": ["tests/test_llm_fallback.py::test_fallback_from_low_monitor_raises_action_to_review_only",
                  "tests/test_review_page.py::test_llm_fallback_is_shown_and_recorded_as_fallback"]},
    {"control": "Explicit retry rather than silent automatic retry", "status": ACTIVE,
     "what": "A fallback is retried only when the analyst clicks Retry LLM assessment.",
     "evidence": ["tests/test_review_retry.py::test_no_automatic_retry_after_recovery"]},
    {"control": "Stale-assessment protection and mandatory re-review", "status": ACTIVE,
     "what": "A decision is recorded only if the assessment is unchanged since the analyst "
             "viewed it; otherwise nothing is written and re-review is required.",
     "evidence": ["tests/test_review_consistency.py::test_race_blocks_submit_after_other_session_retry"]},
    {"control": "Deterministic regression baseline", "status": ACTIVE,
     "what": "105 cases pin the offline outputs; changes require a version bump and a reviewed "
             "fixture update.",
     "qualification": "Manually run, not CI-enforced.",
     "evidence": ["tests/fixtures/regression_baseline.json",
                  "tests/test_regression_baseline.py::test_default_outputs_match_baseline"]},
    {"control": "Known limitations documented", "status": ACTIVE,
     "what": "Limitations are stated in the README and test results.",
     "evidence": ["README.md", "TEST_RESULTS.md"]},
    {"control": "Purpose-limitation / secondary-use policy", "status": PROPOSED,
     "what": "Restrict use to trademark-conflict triage. Not technically enforced today."},
    {"control": "Retention and deletion policy", "status": PROPOSED,
     "what": "Define how long review history is kept and how it is deleted. None defined today."},
    {"control": "Formal data-minimization policy", "status": PROPOSED,
     "what": "Review whether every field (e.g. applicant name) is necessary, especially in LLM mode."},
    {"control": "Authenticated reviewer identity", "status": FUTURE,
     "what": "Record who made each decision. The app has no sign-in."},
    {"control": "Role / access control", "status": FUTURE, "what": "Restrict who can review and view history."},
    {"control": "CI-enforced regression testing", "status": FUTURE,
     "what": "Run the regression baseline automatically on every change."},
    {"control": "Operational fallback-rate / drift monitoring", "status": FUTURE,
     "what": "Track LLM fallback rates and output drift over time."},
    {"control": "Explicit affiliation-evidence source", "status": FUTURE,
     "what": "A reliable owner/affiliate source would allow rule I4 to be used again."},
    {"control": "Stronger tamper-evident audit storage, if needed", "status": FUTURE,
     "what": "E.g. external or signed audit records, if the use case requires it."},
]

# --- Regulatory Lens -----------------------------------------------------------------

REGULATORY_LENS = [
    {"framework": "NIST AI RMF 1.0", "instrument": "Voluntary framework",
     "concepts": "Govern / Map / Measure / Manage; human oversight; documentation; risk treatment",
     "connection": "Control register, intended-use description, evaluation/regression, fallback "
                   "and review controls",
     "applicability": "Design alignment",
     "note": "AI RMF 1.0 is being revised; alignment is not certification."},
    {"framework": "ISO/IEC 42001:2023", "instrument": "International standard",
     "concepts": "AI management system",
     "connection": "Governance controls, documented intended use, change/version control, "
                   "risk-treatment evidence",
     "applicability": "Design alignment only", "note": "No ISO certification is claimed."},
    {"framework": "ISO/IEC 42005:2025", "instrument": "International standard",
     "concepts": "AI system impact assessment guidance",
     "connection": "Purpose and context, impacts, limitations, human role, data use",
     "applicability": "Design alignment only", "note": "No ISO certification is claimed."},
    {"framework": "ISO/IEC 23894:2023", "instrument": "International standard",
     "concepts": "AI risk-management guidance",
     "connection": "Identified risks, controls, failure handling, monitoring/change concepts",
     "applicability": "Design alignment only", "note": "No ISO certification is claimed."},
    {"framework": "EU AI Act", "instrument": "Binding law",
     "concepts": "Article 12 (record-keeping), Article 13 (transparency to deployers), "
                 "Article 14 (human oversight)",
     "connection": "Decision history, provenance, visible recommendations, human override/review: "
                   "design concepts demonstrated",
     "applicability": "Context-dependent",
     "note": "Articles 12-14 are requirements for high-risk AI systems. SignalSilence is not "
             "described here as high-risk, and no claim is made that it satisfies the EU AI Act."},
    {"framework": "GDPR", "instrument": "Binding law",
     "concepts": "Purpose limitation, data minimization, storage limitation, transparency about "
                 "purposes, sources and recipients",
     "connection": "The Data & Lineage tab makes these questions visible.",
     "applicability": "Potentially applicable",
     "note": "Depends on territorial scope and processing of personal data (e.g. individual "
             "applicants' names). No compliance claim."},
    {"framework": "India DPDP Act 2023 + DPDP Rules 2025", "instrument": "Binding law",
     "concepts": "Specified purpose, necessary personal data, notice, processing controls",
     "connection": "Purpose statement, fields-used list, data-flow description",
     "applicability": "Context-dependent",
     "note": "Depends on deployment and covered processing. No compliance claim."},
    {"framework": "California CCPA / ADMT regulations", "instrument": "Binding law",
     "concepts": "Risk assessment; consumer access, opt-out and pre-use notice for covered ADMT uses",
     "connection": "Human decision authority, documented purpose, decision records",
     "applicability": "Context-dependent",
     "note": "Regulations final; effective 2026-01-01. The current trademark-triage demo is not "
             "assumed to be a covered ADMT use."},
    {"framework": "Colorado SB26-189", "instrument": "Binding law",
     "concepts": "Automated decision-making technology used to make, guide or assist "
                 "consequential decisions concerning individuals",
     "connection": "Applicability would change if this architecture were reused for "
                   "consequential decisions about individuals.",
     "applicability": "Not applicable to current use",
     "note": "Became law in 2026. Monitor if the system is reused for consequential "
             "individual decisions."},
    {"framework": "Illinois Artificial Intelligence Video Interview Act", "instrument": "Binding law",
     "concepts": "AI analysis of applicant-submitted video interviews in employment",
     "connection": "Included to show that applicability changes when technology moves into a "
                   "different use context.",
     "applicability": "Not applicable to current use",
     "note": "Employment-specific; SignalSilence does trademark triage."},
    {"framework": "New Jersey S4075", "instrument": "Proposed / developing law",
     "concepts": "Pending legislation (2026-2027 session)",
     "connection": "Tracked for future relevance.",
     "applicability": "Monitor",
     "note": "Bill still in the legislative process as of the status date; not enacted law."},
]

REGULATORY_DISCLAIMER = ("Regulatory status and applicability can change. This page is an "
                         "engineering/governance aid, not legal advice. Verify current "
                         "requirements before deployment.")

# --- Monitoring & Change ---------------------------------------------------------------

MONITORING_ACTIVE = [
    ("Change traceability", "Policy versions, prompt version and model id are stored with "
                            "decisions; Git/PR history records changes outside the runtime record."),
    ("Regression protection", "105 deterministic cases with a manual regression guard."),
    ("Known limitations", "Documented in the README and test results."),
]
MONITORING_NOT_YET = [
    ("Fallback-rate monitoring", FUTURE), ("Drift monitoring", FUTURE),
    ("CI automation", FUTURE), ("Periodic regulatory review", PROPOSED),
    ("Formal retention review", PROPOSED), ("Formal impact-assessment cadence", PROPOSED),
]
