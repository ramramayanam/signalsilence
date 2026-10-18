"""SignalSilence analyst review workspace.

Run: streamlit run app.py, then open "Analyst Review" in the sidebar.
Queue = the 5 canonical demo cases. Decisions are appended to a local
SQLite log (see src/signalsilence/review_store.py); nothing is
overwritten. Scoring is the unchanged triage() pipeline.

Layout: queue on the left; the selected case on the right, with the
system assessment and the analyst decision in separate panels. System
values use red/orange/green/gray badges; analyst status uses blue, so a
system "Escalate" never reads as an analyst decision.
"""
import json
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402
from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

NOT_AVAILABLE = "Not available"
RISK_BADGE = {
    "high": ":red-background[**HIGH**]",
    "review": ":orange-background[**REVIEW**]",
    "low": ":green-background[**LOW**]",
}
DECISION_HELP = {
    "confirm_flag": "Keep as a potential conflict.",
    "dismiss_flag": "Not a meaningful conflict.",
    "refer_legal_review": "Needs attorney or senior reviewer attention.",
}

st.set_page_config(page_title="SignalSilence — Analyst Review", page_icon="🔕",
                   layout="wide")
st.title("Analyst review")
st.info("**SignalSilence recommends. The analyst decides.** "
        "The system assessment is decision support for preliminary review. "
        "It is not a legal determination.")

DB_PATH = review_store.default_db_path()
review_store.init_db(DB_PATH)

CASES = {c.case_id: (label, c) for label, c in CANONICAL.items()}
# Same mode selection triage() makes on its own. What actually ran (llm,
# offline, or llm_fallback_offline) comes back on each result and is what
# the page shows and the decision record stores.
USE_LLM = bool(os.environ.get("ANTHROPIC_API_KEY"))
MODE_LABEL = {
    "offline": "offline heuristic context judgment",
    "llm": f"llm context judgment ({os.environ.get('SIGNALSILENCE_MODEL') or 'triage.py default model'})",
    "llm_fallback_offline": "llm_fallback_offline — LLM unavailable, offline context judgment used",
}


@st.cache_data(show_spinner=False)
def assess(case_id: str, use_llm: bool):
    """Cached so LLM mode does not re-call the API on every rerun."""
    return triage(CASES[case_id][1], use_llm=use_llm)


def show(value) -> str:
    return NOT_AVAILABLE if value is None or str(value).strip() == "" else str(value)


def yes_no(flag: bool) -> str:
    return "**Yes**" if flag else "No"


def status_of(case_id: str, latest: dict) -> str:
    if case_id not in latest:
        return review_store.UNREVIEWED
    return review_store.STATUS[latest[case_id]["analyst_decision"]]


def status_badge(status: str) -> str:
    if status == review_store.UNREVIEWED:
        return f":gray-background[{status}]"
    return f":blue-background[**{status}**]"


latest = review_store.latest_decisions(DB_PATH)
results = {cid: assess(cid, USE_LLM) for cid in CASES}

queue_col, case_col = st.columns([2, 3], gap="large")

# --- Queue -------------------------------------------------------------------

with queue_col:
    st.subheader("Case queue")
    risks = [r.risk.value for r in results.values()]
    st.caption(
        f"{len(CASES)} cases · {risks.count('high')} high · "
        f"{risks.count('review')} review · {risks.count('low')} low · "
        f"{len(latest)} reviewed")
    # The radio's captions change when a decision is recorded, which makes
    # Streamlit treat it as a new widget; remembering the selection here
    # keeps the analyst on the same case.
    selected = st.session_state.setdefault("selected_case", next(iter(CASES)))
    with st.container(border=True):
        case_id = st.radio(
            "Open case", list(CASES), index=list(CASES).index(selected),
            format_func=lambda cid: (f"**{CASES[cid][1].protected_mark}** vs "
                                     f"**{CASES[cid][1].candidate_mark}**"),
            captions=[
                f"{RISK_BADGE[results[cid].risk.value]} · "
                f"System: {results[cid].action.value.title()} · "
                f"{status_badge(status_of(cid, latest))}"
                + (f" · {latest[cid]['recorded_at'].replace('T', ' ').replace('+00:00', ' UTC')}"
                   if cid in latest else "")
                for cid in CASES
            ],
            label_visibility="collapsed",
        )
    st.session_state["selected_case"] = case_id

label, case = CASES[case_id]
result = results[case_id]
status = status_of(case_id, latest)

# --- Selected case -------------------------------------------------------------

with case_col:
    st.subheader(f"{case.protected_mark}  vs  {case.candidate_mark}")
    st.caption(f"Protected mark vs new filing · case {case_id}")

    s1, s2, s3 = st.columns(3)
    with s1.container(border=True):
        st.caption("System risk")
        st.markdown(RISK_BADGE[result.risk.value])
    with s2.container(border=True):
        st.caption("System recommendation")
        st.markdown(f":gray-background[{result.action.value.title()}]")
    with s3.container(border=True):
        st.caption("Analyst review status")
        st.markdown(status_badge(status))

    with st.container(border=True):
        st.markdown("##### System assessment · SignalSilence recommends")
        st.caption(f"Produced by SignalSilence ({MODE_LABEL[result.assessment_mode]}; "
                   f"rules version {review_store.POLICY_VERSION}).")
        if result.assessment_mode == "llm_fallback_offline":
            st.warning(f"**LLM unavailable ({result.fallback_reason}).** This is the offline "
                       "assessment, not an LLM judgment. Risk is unchanged; a Monitor "
                       "recommendation is raised to Review so the case gets human review.")
        m1, m2 = st.columns(2)
        m1.metric("Lexical similarity", f"{result.scores.lexical:.2f}")
        m2.metric("Phonetic similarity", f"{result.scores.phonetic:.2f}")
        f1, f2 = st.columns(2)
        f1.markdown(
            f"Goods commercially adjacent: {yes_no(result.context.goods_adjacent)}  \n"
            f"Added wording descriptive: {yes_no(result.context.added_wording_descriptive)}")
        f2.markdown(
            f"Plausible affiliation: {yes_no(result.context.plausible_affiliation)}  \n"
            f"Behavioral signal: {yes_no(result.context.behavioral_signal)}")
        st.markdown("**Rules that fired**  \n" + "  \n".join(
            f"`{note}`" for note in result.invariant_notes))
        st.markdown(f"**Insight:** {show(result.insight)}")
        with st.expander("Case inputs as provided"):
            st.markdown(
                f"- Class of new filing: {show(case.candidate_class)}\n"
                f"- Goods/services: {show(case.candidate_goods)}\n"
                f"- Applicant: {show(case.applicant_name)}\n"
                f"- Applicant entity type: {show(case.owner_entity_type)}\n"
                f"- Applicant filings (recent window): {show(case.recent_filing_count)}\n"
                f"- Same-class flag: `{case.goods_class_overlap}` — a provided input, "
                f"not computed or verified by SignalSilence\n"
                f"- Filing date, application number, protected-mark owner, source link: "
                f"{NOT_AVAILABLE}"
            )

    with st.container(border=True):
        st.markdown("##### Analyst decision · the analyst decides")
        st.caption("Your decision is recorded with a snapshot of the system "
                   "assessment above. Earlier decisions are kept.")
        with st.form(f"decision_{case_id}", clear_on_submit=True, border=False):
            decision = st.radio(
                "Your decision", list(review_store.DECISIONS), key=f"decision_{case_id}",
                format_func=review_store.DECISIONS.get, index=None,
                captions=[DECISION_HELP[d] for d in review_store.DECISIONS],
            )
            note = st.text_area("Note (optional)", max_chars=1000, height=80,
                                placeholder="e.g. Same class but unrelated goods.")
            submitted = st.form_submit_button("Record decision", type="primary")

        if submitted:
            if decision is None:
                st.warning("Choose a decision before recording.")
            else:
                review_store.record_decision(DB_PATH, case, result, decision, note,
                                             assessment_mode=result.assessment_mode)
                st.session_state["recorded"] = (
                    f"{review_store.DECISIONS[decision]} recorded for {case_id}.")
                st.rerun()

        if "recorded" in st.session_state:
            st.success(st.session_state.pop("recorded"))

    # --- Decision history ----------------------------------------------------

    st.markdown("##### Decision history")
    history = review_store.case_history(DB_PATH, case_id)
    if not history:
        st.caption("No decisions recorded for this case yet.")
    else:
        last = history[-1]
        with st.container(border=True):
            st.caption("Latest decision")
            st.markdown(
                f"{status_badge(review_store.STATUS[last['analyst_decision']])} · "
                f"{last['recorded_at'].replace('T', ' ').replace('+00:00', ' UTC')}"
                f" · system then: {last['system_risk'].upper()} / "
                f"{last['system_action'].title()}"
                + (f"  \n> {last['analyst_note']}" if last["analyst_note"] else ""))
        st.dataframe(
            [{
                "#": len(history) - i,
                "Recorded (UTC)": e["recorded_at"].replace("T", " ").replace("+00:00", ""),
                "Analyst decision": review_store.DECISIONS[e["analyst_decision"]],
                "System then": f"{e['system_risk'].upper()} / {e['system_action'].title()}",
                "Rules version": e["policy_version"] or NOT_AVAILABLE,
                "Note": e["analyst_note"] or "",
            } for i, e in enumerate(reversed(history))],
            hide_index=True, use_container_width=True,
            column_config={"#": st.column_config.NumberColumn(width="small")},
        )
        with st.expander("Stored system snapshot of the latest decision"):
            st.json(json.loads(last["system_snapshot"]))
        st.caption("Decisions are append-only: a new decision adds a row; earlier "
                   "decisions are kept. Reviewer identity is not supported: the app "
                   "has no sign-in, so no reviewer is recorded.")

st.caption("This is an AI-assisted assessment for preliminary review and "
           "does not constitute legal advice.")
