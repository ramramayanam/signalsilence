"""SignalSilence Triage page (the default page of the app.py navigation).

Run: streamlit run app.py
Works fully offline; set ANTHROPIC_API_KEY for LLM context judgment.
"""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.schema import Case  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

st.set_page_config(page_title="SignalSilence", page_icon="🔕")
st.title("SignalSilence")
st.caption("AI trademark triage that learns when to stay silent. "
           "Similarity generates alerts; context and behavior decide.")

tab_demo, tab_custom = st.tabs(["Canonical cases", "Try your own"])

with tab_demo:
    choice = st.selectbox("Case", list(CANONICAL))
    case = CANONICAL[choice]

with tab_custom:
    col1, col2 = st.columns(2)
    with col1:
        pm = st.text_input("Protected mark", "LULULEMON")
        cm = st.text_input("New filing", "LULULEMOON")
        goods = st.text_input("Goods description", "yoga pants")
    with col2:
        cls = st.text_input("NICE class", "025")
        applicant = st.text_input("Applicant", "Acme Brands Ltd")
        filings = st.number_input("Applicant filings, last 12 months", 0, 100, 0)
    overlap = st.checkbox("Same class as protected mark", True)
    if st.button("Triage this case"):
        case = Case("custom", pm, cm, cls, goods, applicant,
                    "corporation", overlap, recent_filing_count=int(filings))

result = triage(case)

st.divider()
risk_color = {"high": "red", "review": "orange", "low": "green"}[result.risk.value]
st.markdown(
    f"**{case.protected_mark}** vs **{case.candidate_mark}** — "
    f":{risk_color}[**RISK: {result.risk.value.upper()}**]"
)
c1, c2, c3 = st.columns(3)
c1.metric("Lexical", f"{result.scores.lexical:.2f}")
c2.metric("Phonetic", f"{result.scores.phonetic:.2f}")
c3.metric("Action", result.action.value.title())

st.markdown(f"**Context:** adjacent goods: `{result.context.goods_adjacent}` · "
            f"descriptive wording: `{result.context.added_wording_descriptive}` · "
            f"affiliation: `{result.context.plausible_affiliation}` · "
            f"behavioral signal: `{result.context.behavioral_signal}`")

with st.expander("Audit trail — invariants that fired"):
    for note in result.invariant_notes:
        st.write(f"• {note}")

st.caption("This is an AI-assisted assessment for preliminary review and "
           "does not constitute legal advice.")
