"""SignalSilence analyst review workspace.

Run: streamlit run app.py, then open "Analyst Review" in the sidebar.
Queue = the 5 canonical demo cases. Decisions are appended to a local
SQLite log (see src/signalsilence/review_store.py); nothing is
overwritten. Scoring is the unchanged triage() pipeline.
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
RISK_COLOR = {"high": "red", "review": "orange", "low": "green"}

st.set_page_config(page_title="SignalSilence — Analyst Review", page_icon="🔕")
st.title("Analyst review")
st.info("**SignalSilence recommends. The analyst decides.** "
        "The system assessment below is decision support for preliminary "
        "review. It is not a legal determination.")

DB_PATH = review_store.default_db_path()
review_store.init_db(DB_PATH)

CASES = {c.case_id: (label, c) for label, c in CANONICAL.items()}
# Same mode selection triage() makes on its own, made explicit so the
# decision record can say which context judgment produced the assessment.
USE_LLM = bool(os.environ.get("ANTHROPIC_API_KEY"))
ASSESSMENT_MODE = (
    f"llm context judgment ({os.environ.get('SIGNALSILENCE_MODEL') or 'triage.py default model'})"
    if USE_LLM else "offline heuristic context judgment"
)


@st.cache_data(show_spinner=False)
def assess(case_id: str, use_llm: bool):
    """Cached so LLM mode does not re-call the API on every rerun."""
    return triage(CASES[case_id][1], use_llm=use_llm)


def show(value) -> str:
    return NOT_AVAILABLE if value is None or str(value).strip() == "" else str(value)


# --- Queue -----------------------------------------------------------------

latest = review_store.latest_decisions(DB_PATH)
st.subheader("Case queue")
st.dataframe(
    [{
        "Case": case_id,
        "Protected mark": case.protected_mark,
        "New filing": case.candidate_mark,
        "System risk": assess(case_id, USE_LLM).risk.value.title(),
        "System recommendation": assess(case_id, USE_LLM).action.value.title(),
        "Review status": (review_store.STATUS[latest[case_id]["analyst_decision"]]
                          if case_id in latest else review_store.UNREVIEWED),
        "Last reviewed (UTC)": latest[case_id]["recorded_at"] if case_id in latest else "—",
    } for case_id, (_, case) in CASES.items()],
    hide_index=True, use_container_width=True,
)

case_id = st.selectbox(
    "Open case", list(CASES),
    format_func=lambda cid: f"{cid} · {CASES[cid][1].protected_mark} vs {CASES[cid][1].candidate_mark}",
)
label, case = CASES[case_id]
result = assess(case_id, USE_LLM)

# --- System assessment -------------------------------------------------------

st.divider()
st.subheader("System assessment")
st.caption(f"Produced by SignalSilence ({ASSESSMENT_MODE}; rules version "
           f"{review_store.POLICY_VERSION}).")
st.markdown(
    f"**{case.protected_mark}** (protected) vs **{case.candidate_mark}** (new filing) — "
    f":{RISK_COLOR[result.risk.value]}[**RISK: {result.risk.value.upper()}**]"
)
c1, c2, c3 = st.columns(3)
c1.metric("Lexical similarity", f"{result.scores.lexical:.2f}")
c2.metric("Phonetic similarity", f"{result.scores.phonetic:.2f}")
c3.metric("System recommendation", result.action.value.title())

st.markdown("**Context facts used by the policy**")
st.markdown(
    f"- Goods commercially adjacent: `{result.context.goods_adjacent}`\n"
    f"- Added wording descriptive: `{result.context.added_wording_descriptive}`\n"
    f"- Plausible affiliation: `{result.context.plausible_affiliation}`\n"
    f"- Behavioral signal: `{result.context.behavioral_signal}`"
)
st.markdown(f"**Insight:** {show(result.insight)}")
st.markdown("**Rules that fired**")
for note in result.invariant_notes:
    st.markdown(f"- {note}")

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

# --- Analyst decision ------------------------------------------------------

st.divider()
st.subheader("Analyst decision")
st.markdown(f"Current review status: **{review_store.review_status(DB_PATH, case_id)}**")

with st.form(f"decision_{case_id}", clear_on_submit=True):
    decision = st.radio(
        "Your decision", list(review_store.DECISIONS),
        format_func=review_store.DECISIONS.get, index=None,
    )
    note = st.text_area("Note (optional)", max_chars=1000,
                        placeholder="e.g. Same class but unrelated goods.")
    submitted = st.form_submit_button("Record decision")

if submitted:
    if decision is None:
        st.warning("Choose a decision before recording.")
    else:
        review_store.record_decision(DB_PATH, case, result, decision, note,
                                     assessment_mode=ASSESSMENT_MODE)
        st.session_state["recorded"] = f"{review_store.DECISIONS[decision]} recorded for {case_id}."
        st.rerun()

if "recorded" in st.session_state:
    st.success(st.session_state.pop("recorded"))

# --- Decision history ------------------------------------------------------

st.subheader("Decision history")
history = review_store.case_history(DB_PATH, case_id)
if not history:
    st.caption("No decisions recorded for this case yet.")
else:
    st.dataframe(
        [{
            "Recorded (UTC)": e["recorded_at"],
            "Analyst decision": review_store.DECISIONS[e["analyst_decision"]],
            "Note": e["analyst_note"] or "",
            "System risk then": e["system_risk"].title(),
            "System recommendation then": e["system_action"].title(),
            "Rules version": e["policy_version"] or NOT_AVAILABLE,
        } for e in reversed(history)],
        hide_index=True, use_container_width=True,
    )
    with st.expander("Full stored snapshot of the latest decision"):
        st.json(json.loads(history[-1]["system_snapshot"]))
    st.caption("Decisions are append-only: a new decision adds a row; earlier "
               "decisions are kept. Reviewer identity is not supported: the app "
               "has no sign-in, so no reviewer is recorded.")

st.caption("This is an AI-assisted assessment for preliminary review and "
           "does not constitute legal advice.")
