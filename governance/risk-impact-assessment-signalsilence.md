# AI Risk & Impact Assessment — SignalSilence

**Artifact type:** AI System Risk & Impact Assessment (pre-deployment)
**System:** SignalSilence — AI-assisted trademark infringement detection
**Assessment owner:** Ram Ramayanam, AI Governance Lead
**Date:** Aug 23, 2026 | **Version:** 1.0 | **Status:** Draft for governance review
**Frameworks referenced:** NIST AI RMF 1.0 (Map / Measure / Manage / Govern), EU AI Act, ISO/IEC 42001

Scope note: This assessment covers the full production design. The public repo implements the triage core (deterministic similarity → LLM context judgment → policy invariants); the collection, vision-similarity, and drafting components are the production design documented in legacy/.

---

## 1. System Description (NIST AI RMF: MAP)

| Field | Description |
|---|---|
| **Business purpose** | Monitors marketplaces, domains, and social channels to flag potential trademark infringement against a client's registered marks. |
| **What the AI does** | Multi-agent pipeline: (1) collection agent scrapes/ingests candidate listings; (2) matching model scores visual + textual similarity to protected marks; (3) triage agent ranks candidates by likely infringement; (4) drafting agent prepares evidence summary for human reviewer. |
| **Decision influenced** | Whether a candidate listing is escalated to a human (attorney/brand owner) for potential enforcement action (takedown notice, C&D letter). |
| **Autonomy level** | **Recommend (level b of the intake autonomy ladder).** The system flags and ranks; it does NOT send notices or contact third parties. A human makes every enforcement decision. |
| **Model components** | LLM (hosted API) for text analysis and evidence drafting; vision embedding model for logo/mark similarity; rules layer for jurisdiction filters. |
| **Data touched** | Public listing data (product images, titles, seller names), client trademark registrations, client brand assets. No consumer PII intentionally collected; seller business names may identify sole proprietors (incidental personal data). |
| **Users** | Brand-protection analysts, IP attorneys, brand owners (SMB to enterprise). |

---

## 2. Regulatory Classification (EU AI Act — if serving EU clients/data)

| Question | Analysis |
|---|---|
| Prohibited practice? | No. Not social scoring, biometric surveillance, or manipulation. |
| High-risk (Annex III)? | Not squarely listed. Closest analogy is "administration of justice," but the system informs *private* enforcement decisions, with a human decision-maker. Assessed as **not high-risk**, with rationale documented and revisited if autonomy increases. |
| Limited-risk transparency duties? | Yes, if outputs (e.g., drafted notices) are AI-generated content shared externally → disclose AI assistance. |
| **Classification** | **Limited risk**, with transparency obligations. **Trigger for reclassification:** any move to act-autonomously (level d) (auto-sending notices) forces reassessment — automated adverse action against sellers materially changes the risk profile. |

---

## 3. Stakeholders & Potential Harms

| Stakeholder | Potential harm | Severity | Likelihood (pre-mitigation) |
|---|---|---|---|
| Innocent seller flagged (false positive) | Wrongful takedown/C&D → lost income, legal costs, reputational harm. Highest-severity harm in the system. | **High** | Medium |
| Brand owner (false negative) | Infringement missed → brand dilution, lost revenue. | Medium | Medium |
| Brand owner (over-reliance) | Treats ranked list as legal conclusion; skips diligence. | High | Medium |
| Sole-proprietor sellers | Incidental personal data processed without notice. | Medium | Low–Medium |
| SignalSilence operator | Liability/reputation if flags are used recklessly; LLM hallucinated "evidence" in drafted summaries. | High | Low–Medium |

---

## 4. Risk Analysis & Mitigations (NIST AI RMF: MEASURE / MANAGE)

### R1 — False positives leading to wrongful enforcement
- **Description:** Similarity model flags lawful listings (parody, resale, generic terms, coincidental similarity).
- **Mitigations:** Confidence threshold with "review-only" band; mandatory human review before ANY external action; UI displays *why* flagged (matched features), never a legal conclusion; disclaimer that output is not legal advice; feedback loop — reviewer overturns retrain the ranker.
- **Residual risk:** **Medium → acceptable** with human-in-the-loop enforced. **Owner:** Product. **Review:** quarterly false-positive rate report; alert if overturn rate > 25%.

### R2 — Hallucinated or inaccurate evidence in drafted summaries
- **Description:** LLM drafting agent invents details (dates, quantities, quotes) not present in source data.
- **Mitigations:** Drafts constrained to retrieved evidence (RAG with citation-required prompting); every claim in draft hyperlinks to source artifact; reviewer attestation checkbox ("I verified cited evidence") before export.
- **Residual risk:** **Low–Medium.** **Owner:** Engineering. **Review:** monthly sample audit of 20 drafts.

### R3 — Bias in flagging (systematic over-flagging of certain seller categories)
- **Description:** Training/threshold choices may over-flag non-English listings, small sellers, or specific regions.
- **Mitigations:** Quarterly disaggregated evaluation of flag rates and overturn rates by region/language/seller size; documented threshold-change log; escalation to governance review if disparity exceeds defined bound.
- **Residual risk:** **Medium.** **Owner:** Data/ML. **Review:** quarterly fairness report.

### R4 — Incidental personal data of sole proprietors
- **Description:** Seller names/handles may constitute personal data (GDPR scope if EU sellers).
- **Mitigations:** Data minimization (collect only fields needed for match evidence); retention limit (e.g., 12 months for non-escalated candidates); lawful-basis analysis documented (legitimate interest assessment); DSAR process defined.
- **Residual risk:** **Low.** **Owner:** Privacy/Legal.

### R5 — Scope creep to autonomous enforcement (agentic risk)
- **Description:** Commercial pressure to "auto-send takedowns" would move the system to act-autonomously (level d).
- **Mitigations:** Autonomy tier written into system registry; any tier change requires new risk assessment + governance sign-off (gate defined in intake process); runtime control — drafting agent has no send/API-post capability (capability isolation, not just policy).
- **Residual risk:** **Low** while gate holds. **Owner:** AI Governance.

---

## 5. Decision Record (NIST AI RMF: GOVERN)

| Field | Entry |
|---|---|
| **Decision** | Approved for deployment at autonomy level Recommend (b of the intake autonomy ladder), limited-risk classification, subject to mitigations R1–R5 and monitoring cadence below. |
| **Conditions** | Human review mandatory before external action; quarterly fairness + false-positive reporting; reclassification gate on any autonomy change. |
| **Approvers** | Product owner, Engineering lead, Privacy/Legal, AI Governance lead. |
| **Next review** | 6 months from deployment or upon material change (new model, new data source, autonomy change), whichever first. |

---
---

# Companion Artifact: Agent Registry Entry — SignalSilence Drafting Agent

*(One row of the enterprise agent registry, expanded. In practice this is a record in a system; shown here as a schema example.)*

| Field | Value |
|---|---|
| **Agent ID** | AGT-0007 |
| **Name / purpose** | Evidence Drafting Agent — assembles infringement evidence summaries for human reviewers |
| **Owner (accountable human)** | Ram Ramayanam, Product Lead, Brand Protection |
| **Autonomy tier** | Recommend (level b) — cannot execute external actions |
| **Model / version** | Anthropic Claude API, model pinned in config; prompt/config version-controlled in repo `prompts/` |
| **Tools it can call** | Internal evidence store (read-only), template renderer. **Explicitly denied:** email, external APIs, payment, file deletion |
| **Data access** | Candidate listing data, client mark registry. No consumer PII stores |
| **Guardrails** | Citation-required generation; output schema validation; token/spend limit per run; kill switch (feature flag) |
| **Logging & evidence** | All runs logged with input hash, output, model version, reviewer action — retained 24 months |
| **Risk tier / last assessment** | Intake Tier 3 (full assessment required) · Residual risk: Medium (post-mitigation) / Aug 23, 2026 — see RA-SignalSilence-v1.0 |
| **Human-in-the-loop point** | Reviewer attestation before any draft leaves the system |
| **Review cadence** | Quarterly, or on model/prompt version change |
| **Status** | Prototype (public demo) |

*Solo project: all roles held by the author; separation of duties shown for template fidelity.*

---

*Template notes for reuse: the risk assessment maps to NIST AI RMF functions (Map → §1, Measure/Manage → §3–4, Govern → §5) and doubles as EU AI Act documentation for limited-risk systems. Sized to be completable by a product team in one working session for Tier 1–2 systems; Tier 3 systems require the extended version with red-team evidence.*
