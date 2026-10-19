"""SignalSilence AI governance overview (read-only, static).

Which controls exist, what evidence supports them, what data the system
uses, and what the limits are. Content lives in signalsilence.governance
so it can be tested; this page only lays it out. It claims no legal
compliance or certification and makes no runtime or model calls.
"""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import governance as g  # noqa: E402

STATUS_BADGE = {g.ACTIVE: ":blue-background[ACTIVE]", g.PROPOSED: ":violet-background[PROPOSED]",
                g.FUTURE: ":gray-background[FUTURE]"}


def bullets(items):
    return "\n".join(f"- {item}" for item in items)


def evidence_text(refs):
    return "; ".join(r.replace("::", " :: ") for r in refs)


st.set_page_config(page_title="SignalSilence — AI Governance", page_icon="🔕", layout="wide")
st.title("AI Governance")
st.markdown("*Controls, evidence, data use, and regulatory alignment for this AI system.*")
st.info("This page shows governance controls and design alignment. It does not claim legal "
        "compliance or certification.")

tabs = st.tabs(["System & Purpose", "Data & Lineage", "Risk & Controls", "Regulatory Lens",
                "Monitoring & Change"])

with tabs[0]:
    st.markdown("\n".join(f"**{label}:** {value}  " for label, value in g.SYSTEM))
    st.markdown("**This app does not provide:**\n" + bullets(g.NOT_PROVIDED))
    st.caption("It is not suitable for those purposes.")

with tabs[1]:
    st.warning("Public demo: do not enter confidential or personal information.")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("**Current demo source:** Synthetic demo cases (hand-authored in "
                    "`demo_cases.py`). Live USPTO ingestion is not implemented.")
        st.markdown("**Fields used by the assessment**\n" + bullets(g.FIELDS_USED))
        st.markdown("**Transformations**\n" + bullets(g.TRANSFORMATIONS))
        st.markdown("**Per-decision provenance now captured**\n" + bullets(g.PROVENANCE_CAPTURED))
    with right:
        st.markdown("**External AI processing**")
        st.markdown(
            "- **Offline mode:** no external AI provider.\n"
            "- **LLM mode:** selected case fields are sent to the configured Anthropic Messages "
            "API. The applicant name is currently among those fields.\n"
            "- **Retrieval:** when precedent retrieval is explicitly enabled, precedent fields "
            "(mark, class, goods, outcome label) may be included in the LLM context.\n"
            "- Provider retention and training behavior is governed by the provider's terms and "
            "is not verified by this app.")
        st.markdown("**Purpose:** trademark-conflict triage only.  \n"
                    f"**Secondary use:** no unrelated secondary-use workflow exists in the "
                    f"application. Restriction status: {STATUS_BADGE[g.PROPOSED]} "
                    f"(policy, not technically enforced).")
        st.markdown("**Retention / deletion**\n" + bullets([
            "Local review history is stored in SQLite.",
            "There is currently no defined retention or deletion policy.",
            "Public Streamlit Cloud storage is ephemeral and may be lost on reboot or redeploy.",
            "Public demo history may be shared across visitors.",
        ]))

with tabs[2]:
    for status, heading in ((g.ACTIVE, "Implemented controls"),
                            (g.PROPOSED, "Proposed (not yet in place)"),
                            (g.FUTURE, "Future capabilities")):
        rows = [c for c in g.CONTROLS if c["status"] == status]
        st.markdown(f"**{heading}** {STATUS_BADGE[status]} · {len(rows)}")
        # st.table (not st.dataframe): shows every row and wraps long text, so no
        # control, evidence or qualification is hidden behind scrolling.
        st.table(pd.DataFrame(
            [{"Control": c["control"], "Status": c["status"], "What it does": c["what"],
              **({"Evidence": evidence_text(c["evidence"]),
                  "Qualification": c.get("qualification", "")} if status == g.ACTIVE else {})}
             for c in rows]).set_index("Control"))
    st.caption("Evidence entries are files and tests in this repository. Statuses describe what "
               "is implemented; they are not a score or a compliance rating.")

with tabs[3]:
    st.info(g.REGULATORY_DISCLAIMER)
    st.caption(f"Status as of {g.STATUS_AS_OF}. A design/reference map, not a compliance "
               f"determination.")
    st.table(pd.DataFrame(
        [{"Framework / law": r["framework"], "Instrument type": r["instrument"],
          "Applicability / status": r["applicability"]} for r in g.REGULATORY_LENS]
    ).set_index("Framework / law"))
    with st.expander("Details: concepts, SignalSilence connection and notes"):
        for r in g.REGULATORY_LENS:
            st.markdown(f"**{r['framework']}** · {r['instrument']} · *{r['applicability']}*  \n"
                        f"Relevant concepts: {r['concepts']}  \n"
                        f"SignalSilence connection: {r['connection']}  \n"
                        f"Note: {r['note']}")

with tabs[4]:
    st.markdown(f"**In place** {STATUS_BADGE[g.ACTIVE]}\n" + bullets(
        f"**{name}:** {detail}" for name, detail in g.MONITORING_ACTIVE))
    st.markdown("**Not in place yet**\n" + bullets(
        f"{name} {STATUS_BADGE[status]}" for name, status in g.MONITORING_NOT_YET))
    st.caption("There is no live monitoring today.")
