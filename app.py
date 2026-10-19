"""SignalSilence: Streamlit entrypoint and navigation.

Run: streamlit run app.py   (also the Streamlit Community Cloud main file)

Pages live in views/ and are registered explicitly with st.navigation, so
the sidebar reads Triage / Analyst Review / Decision Provenance / AI
Governance. views/ is not auto-discovered (there is no pages/ directory),
and the url_paths keep the existing public routes.
"""
import streamlit as st

PAGES = [
    st.Page("views/triage.py", title="Triage", default=True),                      # /
    st.Page("views/analyst_review.py", title="Analyst Review", url_path="Analyst_Review"),
    st.Page("views/decision_provenance.py", title="Decision Provenance",
            url_path="Decision_Provenance"),
    st.Page("views/ai_governance.py", title="AI Governance", url_path="AI_Governance"),
]

st.navigation(PAGES).run()
