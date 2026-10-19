"""SignalSilence decision provenance (read-only).

Shows, for each recorded analyst decision, the evidence and system state
stored with it at decision time (review_events + its system snapshot).
Nothing here writes to the database, re-runs an assessment, or generates
an explanation after the fact. Fields that were not captured when the
decision was recorded are shown as such, never inferred or backfilled.
"""
import json
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402

NOT_RECORDED = "Not recorded at decision time"
DEFAULT_FILTER = "Dismissals & Escalations"
ALL_FILTER = "All Decisions"
DEFAULT_DECISIONS = {"dismiss_flag", "refer_legal_review"}
DERIVED_NOTE = ("Outcome is derived when this page is viewed, from the recorded system "
                "recommendation and analyst decision. It was not captured at decision time.")
RISK_BADGE = {"high": ":red-background[**HIGH**]", "review": ":orange-background[**REVIEW**]",
              "low": ":green-background[**LOW**]"}


def outcome_badge(system_action: str, analyst_decision: str) -> str:
    """Derived comparison of recommendation vs. decision (SignalSilence's own definition)."""
    if system_action == "escalate" and analyst_decision == "dismiss_flag":
        return "Override down"
    if system_action == "ignore/monitor" and analyst_decision in ("confirm_flag", "refer_legal_review"):
        return "Override up"
    if system_action == "review":
        return "System deferred to analyst"
    return "Consistent"


def recorded(mapping: dict, key: str, absent_but_captured: str = "None"):
    """Value as stored; distinguishes 'key never captured' from 'captured as empty'."""
    if not isinstance(mapping, dict) or key not in mapping:
        return NOT_RECORDED
    value = mapping[key]
    return absent_but_captured if value is None else value


st.set_page_config(page_title="SignalSilence — Decision Provenance", page_icon="🔕",
                   layout="wide")
st.title("Decision Provenance")
st.markdown("*What the system assessed, what it recommended, and what the analyst decided.*")
st.info("Decision Provenance preserves the evidence and system state associated with a "
        "decision. It does not expose hidden model reasoning or chain-of-thought.")
st.caption("Public demo: review history is temporary and may be shared across demo "
           "visitors. Do not enter confidential or personal information.")

events = list(reversed(review_store.list_events(review_store.default_db_path())))
view = st.radio("Show", [DEFAULT_FILTER, ALL_FILTER], key="prov_filter", horizontal=True,
                help="Dismissals & Escalations shows Dismiss Flag and Refer for Legal Review "
                     "decisions. All Decisions also includes Confirm Flag.")
shown = [e for e in events if view == ALL_FILTER or e["analyst_decision"] in DEFAULT_DECISIONS]

if not events:
    st.caption("No decisions recorded yet. Record a decision on the Analyst Review page.")
    st.stop()
if not shown:
    st.caption(f"No Dismiss Flag or Refer for Legal Review decisions recorded. "
               f"Choose {ALL_FILTER} to see every decision.")
    st.stop()

st.dataframe(
    [{
        "Decision #": e["event_id"],
        "Decision recorded (UTC)": e["recorded_at"].replace("T", " ").replace("+00:00", ""),
        "Case": e["case_id"],
        "Protected mark": e["protected_mark"],
        "New filing": e["candidate_mark"],
        "System risk": e["system_risk"].title(),
        "System recommendation": e["system_action"].title(),
        "Analyst decision": review_store.DECISIONS.get(e["analyst_decision"], e["analyst_decision"]),
        "Outcome (derived)": outcome_badge(e["system_action"], e["analyst_decision"]),
    } for e in shown],
    hide_index=True, use_container_width=True,
)
st.caption(DERIVED_NOTE)

by_id = {e["event_id"]: e for e in shown}
event_id = st.selectbox(
    "Open decision", list(by_id), key="prov_event",
    format_func=lambda i: (f"#{i} · {by_id[i]['case_id']} · {by_id[i]['protected_mark']} vs "
                           f"{by_id[i]['candidate_mark']} · "
                           f"{review_store.DECISIONS.get(by_id[i]['analyst_decision'], by_id[i]['analyst_decision'])}"),
)
event = by_id[event_id]
try:
    snapshot = json.loads(event["system_snapshot"])
except (TypeError, ValueError):
    snapshot = None
system = snapshot.get("system_assessment", {}) if isinstance(snapshot, dict) else {}
inputs = snapshot.get("case_inputs", {}) if isinstance(snapshot, dict) else {}
context = system.get("context", {}) if isinstance(system, dict) else {}

st.subheader(f"Decision #{event['event_id']}: {event['protected_mark']} vs {event['candidate_mark']}")
st.markdown(f"Outcome (derived): **{outcome_badge(event['system_action'], event['analyst_decision'])}**")

c1, c2, c3 = st.columns(3, gap="medium")

with c1.container(border=True):
    st.markdown("##### System Assessment")
    st.markdown(f"Risk: {RISK_BADGE.get(event['system_risk'], event['system_risk'])}  \n"
                f"Recommendation: :gray-background[{event['system_action'].title()}]")
    lex, phon = event["lexical_similarity"], event["phonetic_similarity"]
    st.markdown(f"Lexical similarity: **{NOT_RECORDED if lex is None else f'{lex:.2f}'}**  \n"
                f"Phonetic similarity: **{NOT_RECORDED if phon is None else f'{phon:.2f}'}**")
    st.markdown("**Context facts**  \n" + "  \n".join(
        f"{label}: {recorded(context, key)}" for key, label in (
            ("goods_adjacent", "Goods commercially adjacent"),
            ("added_wording_descriptive", "Added wording descriptive"),
            ("plausible_affiliation", "Plausible affiliation"),
            ("behavioral_signal", "Behavioral signal"))))
    notes = recorded(system, "invariant_notes")
    st.markdown("**Rules that fired**  \n" + (
        "  \n".join(f"`{n}`" for n in notes) if isinstance(notes, list) and notes else str(notes)))
    st.markdown(f"**Insight:** {recorded(system, 'insight')}")
    with st.expander("Recorded case inputs"):
        st.markdown("\n".join(f"- {label}: {recorded(inputs, key)}" for key, label in (
            ("protected_mark", "Protected mark"), ("candidate_mark", "New filing"),
            ("candidate_class", "Class of new filing"), ("candidate_goods", "Goods/services"),
            ("applicant_name", "Applicant"), ("owner_entity_type", "Applicant entity type"),
            ("goods_class_overlap", "Same-class flag (provided input)"),
            ("recent_filing_count", "Applicant filings (recent window)"))))

with c2.container(border=True):
    st.markdown("##### Analyst Decision")
    st.markdown(f"Decision: :blue-background[**"
                f"{review_store.DECISIONS.get(event['analyst_decision'], event['analyst_decision'])}**]")
    st.markdown(f"Note: {event['analyst_note'] or 'No note entered'}")
    st.markdown(f"Decision recorded (UTC): "
                f"{event['recorded_at'].replace('T', ' ').replace('+00:00', '')}")
    st.caption("Reviewer identity: not recorded (the app has no sign-in).")

with c3.container(border=True):
    st.markdown("##### Assessment Provenance")
    mode = event.get("assessment_mode") or recorded(system, "assessment_mode")
    offline = mode == "offline"
    fallback = recorded(system, "fallback_reason", "No fallback")
    if mode == "llm_fallback_offline" and fallback not in (NOT_RECORDED, "No fallback"):
        fallback = f"Yes: LLM unavailable ({fallback}); offline assessment used"
    st.markdown("  \n".join([
        f"Assessment mode: `{mode or NOT_RECORDED}`",
        f"Rules version: {event.get('policy_version') or NOT_RECORDED}",
        f"Prompt version: {recorded(system, 'prompt_version', 'None (offline assessment, no LLM used)' if offline else 'None')}",
        f"Model id: {recorded(system, 'llm_model', 'None (offline assessment, no LLM used)' if offline else 'None')}",
        f"Fallback: {fallback}",
        f"Data source: {recorded(snapshot or {}, 'data_source')}",
        f"Assessment produced: {recorded(snapshot or {}, 'assessed_at')}",
    ]))
    st.caption("Values are shown exactly as stored with the decision.")

with st.expander("Full stored snapshot (audit view)"):
    if snapshot is None:
        st.code(str(event["system_snapshot"]))
    else:
        st.json(snapshot)
