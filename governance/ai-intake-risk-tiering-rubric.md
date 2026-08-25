# AI Intake & Risk-Tiering Rubric

**Artifact type:** Intake process + risk-tiering rubric (the "front door" of the AI governance program)
**Owner:** AI Governance Lead | **Version:** 1.0 | **Status:** Draft for adoption
**Frameworks referenced:** NIST AI RMF 1.0 (Govern / Map), EU AI Act risk tiers, ISO/IEC 42001 §6 (planning)

**Design principle:** Governance effort must be proportionate to risk. Most AI use is low-risk and should clear intake in minutes, not weeks. Heavy review is reserved for systems that can genuinely hurt people, the business, or compliance posture. If teams route around the process, the process has failed — not the teams.

---

## 1. When intake is required (triggers)

A team must submit an intake record when any of the following happens:

1. **New AI system or agent** is proposed for build or purchase (including pilots that touch real data or real users).
2. **Material change** to an existing system: new model or provider, new data source, expanded user population, or **any increase in autonomy tier**.
3. **New use of an approved tool** in a way that changes its risk profile (e.g., an approved LLM chat tool now being fed customer contracts).

**Not required for:** individual use of already-approved tools within the approved use policy (that's covered by the AI Use Policy, not intake), or experiments on synthetic/public data with no user exposure.

---

## 2. The intake form (deliberately short — 10 questions, ~10 minutes)

| # | Question | Why it's asked |
|---|---|---|
| 1 | What does the system do, in one paragraph? | Registry description |
| 2 | Who is the accountable owner (a person, not a team)? | NIST GOVERN — accountability |
| 3 | What decision or action does it influence or take? | Core of risk tiering |
| 4 | **Autonomy tier:** Does it (a) inform, (b) recommend, (c) act with human approval, or (d) act autonomously? | Agentic risk driver |
| 5 | Who is affected if it's wrong — customers, employees, third parties, the public? | Harm surface |
| 6 | What data does it touch? (PII / PHI / financial / confidential / public only) | Privacy & security exposure |
| 7 | Is any output shown to or acting on people *outside* the company? | External-impact multiplier |
| 8 | Model source: in-house, fine-tuned, hosted API, or embedded in a vendor product? | Third-party risk path |
| 9 | Could this use fall under a regulated domain (hiring, credit, health, legal, safety, minors)? | EU AI Act / sectoral law flag |
| 10 | Target launch date and sprint cadence? | So governance schedules itself into delivery, not after it |

Submitted via ticket/form; auto-creates a draft **registry entry** (single source of truth — no duplicate paperwork later).

---

## 3. Risk-tiering rubric

Score the system on five factors. Each factor is rated 0–2. **The tier is set by the highest-scoring factor, not the average** — one severe factor is enough to raise the tier (a system that's benign on four axes but decides who gets a loan is still high-risk).

| Factor | 0 — Low | 1 — Medium | 2 — High |
|---|---|---|---|
| **A. Consequence of error** | Inconvenience; easily reversed | Meaningful cost, reversible with effort | Legal, financial, safety, or rights impact on a person; hard to reverse |
| **B. Autonomy** | Informs / drafts for a human | Recommends or ranks; human decides | Acts externally (sends, pays, files, publishes) with or without approval loop |
| **C. Data sensitivity** | Public or synthetic data | Internal/confidential business data; incidental personal data | PII at scale, PHI, financial, biometric, or minors' data |
| **D. Exposure** | Internal, small user group | Internal, broad; or external read-only | External parties affected by outputs or actions |
| **E. Regulatory surface** | None identified | Adjacent to regulated domain; transparency duties likely | Squarely in a regulated/high-risk category (hiring, credit, health, legal enforcement, safety) |

### Tier outcomes

| Tier | Trigger | Governance path | Target SLA |
|---|---|---|---|
| **Tier 1 — Low** | All factors 0, or single 1 | **Self-assessment.** Owner completes the 1-page checklist, registry entry auto-approved, spot-audited quarterly. | Same day |
| **Tier 2 — Medium** | Any factor at 1 (multiple), none at 2 | **Light review.** Governance lead reviews intake + a focused risk discussion (30 min) in the team's existing sprint ritual. Conditions logged in registry. | ≤ 5 business days |
| **Tier 3 — High** | Any factor at 2 | **Full assessment.** Complete Risk & Impact Assessment (see companion artifact), privacy/legal consult, named approvers, decision record, monitoring plan. | ≤ 3 weeks, scheduled against the team's release plan at intake |

**Standing rule for agents:** any system at Autonomy = 2 (acts externally) is automatically Tier 3, regardless of other scores, and requires capability isolation evidence (what the agent *cannot* call) — not just policy statements.

---

## 4. Worked examples

**Example 1 — Internal meeting-notes summarizer (approved LLM, internal docs)**
A=0 (bad summary is annoying), B=0 (drafts for humans), C=1 (internal docs), D=0, E=0 → highest score 1, single factor → **Tier 1.** Self-assessment, done same day. *This is the majority of intake volume, and it should feel nearly frictionless.*

**Example 2 — SignalSilence (trademark infringement flagging, recommend-only)**
A=2 (wrongful enforcement harms an innocent seller), B=1 (recommends; human decides), C=1 (incidental seller personal data), D=2 (external third parties affected), E=1 (adjacent to legal enforcement) → highest score 2 → **Tier 3.** Full risk assessment — which is exactly what the companion artifact is.

**Example 3 — Same SignalSilence, but product wants auto-send takedowns**
B moves to 2 (acts externally). Already Tier 3, but the standing agent rule now also demands capability-isolation evidence and a fresh assessment — the reclassification gate defined in the original decision record fires. *This is how the rubric and the risk assessment interlock.*

**Example 4 — Resume-screening assistant for recruiting**
E=2 (hiring is a named high-risk category under the EU AI Act and NYC LL144-type laws) → **Tier 3 immediately**, whatever the other scores. No debate needed; the rubric answers in one row.

---

## 5. Integration with delivery (the anti-shelfware section)

- **Intake lives where work lives.** The form is a ticket type in the team's existing tracker; Tier 2 reviews happen inside an existing sprint ceremony, not a separate governance meeting.
- **Gates are backlog items.** For Tier 3 systems, the assessment and its conditions are entered as tracked work items with owners and sprint assignments — governance work is planned like engineering work.
- **The registry is the only artifact of record.** Intake, tiering score, review outcome, conditions, and review dates all live on the registry entry. No parallel spreadsheets.
- **Measured like a product.** Program KPIs: median intake-to-decision time per tier, % of systems in registry vs. discovered (shadow-AI rate), % of Tier 3 conditions verified on schedule, and reviewer-overturn/incident rates feeding back into rubric calibration.
- **Escape valve.** Any team that believes a tiering result is wrong can request a re-score with rationale; disagreements go to the governance forum with a 1-week decision SLA. Documented disagreement beats silent workaround.

---

## 6. Roles (RACI, kept minimal)

| Activity | System owner | AI Governance lead | Privacy/Legal | Security |
|---|---|---|---|---|
| Submit intake | **R/A** | C | — | — |
| Tier scoring | R | **A** | C (Tier 3) | C (Tier 3) |
| Tier 1 self-assessment | **R/A** | I (spot audit) | — | — |
| Tier 3 full assessment | R | **A** | C | C |
| Approval & conditions | C | **A** | C | C |
| Ongoing monitoring | **R** | A (cadence) | I | I |

---

*Template notes for reuse: the five factors deliberately mirror the axes regulators use (consequence, autonomy, data, exposure, regulated domain), so a completed tiering score doubles as the first page of EU AI Act classification evidence. Calibrate the 0/1/2 anchors to your organization's risk appetite in the first governance forum, then leave them stable — a rubric that moves every month is a rubric nobody trusts.*
