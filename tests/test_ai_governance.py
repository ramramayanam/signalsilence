"""Phase 3, Iteration 4: AI Governance page and its register.

The register (signalsilence.governance) is checked directly: every ACTIVE
control must cite evidence that exists in this repo, and regulatory rows
must use fixed vocabularies with no compliance or certification claims.
The page is checked through Streamlit AppTest.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from signalsilence import governance as g  # noqa: E402

PAGE = str(ROOT / "pages" / "3_AI_Governance.py")
LENS = {r["framework"]: r for r in g.REGULATORY_LENS}


# --- Register (no streamlit) -----------------------------------------------------------

def test_active_controls_have_existing_evidence():
    active = [c for c in g.CONTROLS if c["status"] == g.ACTIVE]
    assert len(active) == 13
    for c in active:
        assert c.get("evidence"), f"ACTIVE control without evidence: {c['control']}"
        for ref in c["evidence"]:
            path, _, test_name = ref.partition("::")
            file = ROOT / path
            assert file.exists(), f"{c['control']}: missing {path}"
            if test_name:
                assert re.search(rf"^def {re.escape(test_name)}\(", file.read_text(encoding="utf-8"),
                                 re.M), f"{c['control']}: no test {test_name} in {path}"


def test_statuses_are_only_active_proposed_future():
    assert {c["status"] for c in g.CONTROLS} == {g.ACTIVE, g.PROPOSED, g.FUTURE}


def test_append_only_is_qualified_as_not_tamper_proof():
    c = next(c for c in g.CONTROLS if c["control"].startswith("Append-only"))
    assert "Application-level append-only, not cryptographic tamper-proof" in c["qualification"]


def test_capture_time_provenance_is_scoped_to_new_decisions():
    c = next(c for c in g.CONTROLS if c["control"].startswith("Assessment-produced time"))
    assert c["control"] == "Assessment-produced time and source captured for new decisions"
    assert c["status"] == g.ACTIVE
    assert c["qualification"] == "Historical decisions may show \u2018Not recorded at decision time\u2019."


def test_regression_baseline_is_manual_not_ci():
    c = next(c for c in g.CONTROLS if c["control"] == "Deterministic regression baseline")
    assert c["qualification"] == "Manually run, not CI-enforced."
    ci = next(c for c in g.CONTROLS if c["control"] == "CI-enforced regression testing")
    assert ci["status"] == g.FUTURE


def test_proposed_and_future_items_are_not_active():
    expected = {
        g.PROPOSED: {"Purpose-limitation / secondary-use policy", "Retention and deletion policy",
                     "Formal data-minimization policy"},
        g.FUTURE: {"Authenticated reviewer identity", "Role / access control",
                   "CI-enforced regression testing", "Operational fallback-rate / drift monitoring",
                   "Explicit affiliation-evidence source",
                   "Stronger tamper-evident audit storage, if needed"},
    }
    for status, names in expected.items():
        assert {c["control"] for c in g.CONTROLS if c["status"] == status} == names
    for c in g.CONTROLS:
        if c["status"] != g.ACTIVE:
            assert "evidence" not in c


def test_regulatory_vocabularies_and_types():
    for r in g.REGULATORY_LENS:
        assert r["instrument"] in g.INSTRUMENT_TYPES, r["framework"]
        assert r["applicability"] in g.APPLICABILITY, r["framework"]
    types = {r["instrument"] for r in g.REGULATORY_LENS}
    assert {"Binding law", "Proposed / developing law", "International standard",
            "Voluntary framework"} <= types


def test_eu_ai_act_articles_are_design_references_not_compliance():
    eu = LENS["EU AI Act"]
    assert all(f"Article {n}" in eu["concepts"] for n in (12, 13, 14))
    assert "requirements for high-risk AI systems" in eu["note"]
    assert "not described here as high-risk" in eu["note"]
    assert "no claim is made that it satisfies the EU AI Act" in eu["note"]
    assert "design concepts demonstrated" in eu["connection"]
    assert eu["applicability"] == "Context-dependent"


def test_iso_rows_are_design_alignment_only_without_certification():
    for name in ("ISO/IEC 42001:2023", "ISO/IEC 42005:2025", "ISO/IEC 23894:2023"):
        assert LENS[name]["applicability"] == "Design alignment only"
        assert LENS[name]["note"] == "No ISO certification is claimed."
    assert LENS["NIST AI RMF 1.0"]["instrument"] == "Voluntary framework"
    assert "not certification" in LENS["NIST AI RMF 1.0"]["note"]


def test_state_law_rows():
    ca = LENS["California CCPA / ADMT regulations"]
    assert "effective 2026-01-01" in ca["note"] and ca["applicability"] == "Context-dependent"
    co = LENS["Colorado SB26-189"]
    assert co["instrument"] == "Binding law" and "Became law in 2026" in co["note"]
    assert "consequential decisions concerning individuals" in co["concepts"]
    assert not any("Colorado AI Act" in v for v in co.values())
    il = LENS["Illinois Artificial Intelligence Video Interview Act"]
    assert il["applicability"] == "Not applicable to current use" and "employment" in il["concepts"]
    nj = LENS["New Jersey S4075"]
    assert nj["instrument"] == "Proposed / developing law" and nj["applicability"] == "Monitor"
    assert "not enacted" in nj["note"]


def test_readme_no_longer_claims_an_implemented_uspto_feed():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "load_from_feed" not in readme
    assert "swaps in the USPTO bulk-data loader" not in readme
    assert "Live USPTO ingestion is design intent / future production\nintegration and is not implemented" in readme
    assert "Production design concept — not implemented in the current SignalSilence demo." in readme


def test_future_architecture_documents_are_labelled():
    doc = (ROOT / "governance" / "risk-impact-assessment-signalsilence.md").read_text(encoding="utf-8")
    label = "Production design concept — not implemented in the current SignalSilence demo."
    assert label in "\n".join(doc.splitlines()[:5])                     # at the top
    registry = doc.index("# Companion Artifact: Agent Registry Entry")
    assert label in doc[registry:registry + 300]                          # and on the agent entry
    assert "Multi-agent pipeline" in doc                                  # design material kept


# --- Page (needs streamlit) -------------------------------------------------------------

@pytest.fixture
def page():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(PAGE, default_timeout=30).run()
    assert not at.exception
    return at


def page_text(at):
    parts = [str(e.value) for e in list(at.title) + list(at.markdown) + list(at.caption)
             + list(at.info) + list(at.warning)]
    parts += [tbl.value.reset_index().to_string() for tbl in at.table]
    return "\n".join(parts)


def test_five_tabs_render(page):
    assert [t.label for t in page.tabs] == ["System & Purpose", "Data & Lineage", "Risk & Controls",
                                            "Regulatory Lens", "Monitoring & Change"]


def test_header_and_no_compliance_claim(page):
    t = page_text(page)
    assert "Controls, evidence, data use, and regulatory alignment for this AI system." in t
    assert ("This page shows governance controls and design alignment. It does not claim legal "
            "compliance or certification.") in t
    assert "compliant" not in t.lower()


def test_demo_source_synthetic_and_uspto_not_implemented(page):
    t = page_text(page)
    assert "**Current demo data:** Synthetic demonstration cases" in t
    assert "**Live USPTO ingestion:** Not implemented in this demo." in t
    for line in (ln for ln in t.splitlines() if "USPTO" in ln):
        assert ("not implemented" in line.lower() or "Intended production" in line), line


def test_public_demo_warning_and_applicant_name_fact(page):
    t = page_text(page)
    assert "Public demo: do not enter confidential or personal information." in t
    assert "The applicant name is currently among those fields." in t
    assert "not verified by this app" in t
    assert "There is currently no defined retention or deletion policy." in t


def test_controls_tables_separate_active_from_proposed_and_future(page):
    """Static tables: every row and the full qualification text are shown."""
    active, proposed, future = (tbl.value.reset_index() for tbl in page.table[:3])
    assert set(active["Status"]) == {"ACTIVE"} and len(active) == 13
    assert all(active["Evidence"].str.len() > 0)
    assert set(proposed["Status"]) == {"PROPOSED"} and set(future["Status"]) == {"FUTURE"}
    assert "Evidence" not in proposed.columns and "Evidence" not in future.columns
    t = page_text(page)
    assert "not cryptographic tamper-proof" in t and "Manually run, not CI-enforced." in t


def test_no_score_percentage_or_certification_claim(page):
    t = page_text(page)
    assert not re.search(r"\d\s*%", t)
    for banned in ("governance score", "maturity", "tamper-proof storage.", "certified"):
        assert banned not in t.lower(), banned
    for sentence in re.split(r"(?<=[.!?])\s+|\n", t):
        if "certif" in sentence.lower():
            assert re.search(r"\b(no|not|does not)\b", sentence.lower()), sentence


def test_regulatory_tab_status_date_and_disclaimer(page):
    t = page_text(page)
    assert "Status as of 2026-10-18" in t
    assert g.REGULATORY_DISCLAIMER in t
    lens = page.table[3].value.reset_index()
    assert list(lens.columns) == ["Framework / law", "Instrument type", "Applicability / status"]
    assert len(lens) == len(g.REGULATORY_LENS)
    assert "Proposed / developing law" in set(lens["Instrument type"])


def test_monitoring_tab_does_not_claim_live_monitoring(page):
    t = page_text(page)
    assert "There is no live monitoring today." in t
    assert "Fallback-rate monitoring :gray-background[FUTURE]" in t


@pytest.mark.parametrize("script", ["app.py", "pages/1_Analyst_Review.py",
                                    "pages/2_Decision_Provenance.py", "pages/3_AI_Governance.py"])
def test_all_pages_run(script, tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(tmp_path / "reviews.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(str(ROOT / script), default_timeout=30).run()
    assert not at.exception
