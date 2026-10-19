"""Phase 3, Iteration 5: explicit st.navigation with app.py as the entrypoint.

Streamlit 1.37's AppTest runs the router but does not render pages under
st.navigation, so the navigation definition is checked structurally here,
each view is exercised directly, and page switching / routes are verified
in a real browser (see TEST_RESULTS.md).
"""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

EXPECTED = [
    ("views/triage.py", "Triage", None, True),
    ("views/analyst_review.py", "Analyst Review", "Analyst_Review", False),
    ("views/decision_provenance.py", "Decision Provenance", "Decision_Provenance", False),
    ("views/ai_governance.py", "AI Governance", "AI_Governance", False),
]


def _pages():
    """(path, title, url_path, default) for each st.Page(...) in app.py, in order."""
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    pages = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "Page":
            kw = {k.arg: ast.literal_eval(k.value) for k in node.keywords}
            pages.append((ast.literal_eval(node.args[0]), kw.get("title"),
                          kw.get("url_path"), kw.get("default", False)))
    return sorted(pages, key=lambda p: node_order(p[0]))


def node_order(path):
    return (ROOT / "app.py").read_text(encoding="utf-8").index(path)


def test_app_py_is_the_entrypoint_router():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "st.navigation(PAGES).run()" in source
    assert "Streamlit Community Cloud main file" in source


def test_navigation_exposes_exactly_the_four_pages_in_order():
    assert [p[1] for p in _pages()] == ["Triage", "Analyst Review", "Decision Provenance",
                                        "AI Governance"]


def test_triage_is_the_default_root_page_and_routes_are_preserved():
    assert _pages() == EXPECTED
    defaults = [p for p in _pages() if p[3]]
    assert defaults == [EXPECTED[0]] and defaults[0][2] is None   # root "/"
    for path, *_ in EXPECTED:
        assert (ROOT / path).is_file(), path


def test_no_automatic_page_discovery_remains():
    assert not (ROOT / "pages").exists()                          # nothing auto-discovered
    views = sorted(p.name for p in (ROOT / "views").glob("*.py"))
    assert views == ["ai_governance.py", "analyst_review.py", "decision_provenance.py", "triage.py"]


# --- Runtime (needs streamlit) ------------------------------------------------------------

@pytest.fixture
def apptest(tmp_path, monkeypatch):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(tmp_path / "reviews.db"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return AppTest


def test_router_runs_without_error(apptest):
    at = apptest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception


def test_triage_page_renders_and_scores_each_canonical_case_unchanged(apptest):
    at = apptest.from_file(str(ROOT / "views" / "triage.py"), default_timeout=30).run()
    assert not at.exception
    assert [t.value for t in at.title] == ["SignalSilence"]
    assert [t.label for t in at.tabs] == ["Canonical cases", "Try your own"]
    select = at.selectbox[0]
    assert select.options == list(CANONICAL)
    for label, case in CANONICAL.items():
        select.set_value(label).run()
        expected = triage(case, use_llm=False)
        risk_line = next(str(m.value) for m in at.markdown if "RISK:" in str(m.value))
        assert f"RISK: {expected.risk.value.upper()}" in risk_line, label
        metrics = {m.label: m.value for m in at.metric}
        assert metrics == {"Lexical": f"{expected.scores.lexical:.2f}",
                           "Phonetic": f"{expected.scores.phonetic:.2f}",
                           "Action": expected.action.value.title()}, label


def test_triage_custom_case_button_still_works(apptest):
    at = apptest.from_file(str(ROOT / "views" / "triage.py"), default_timeout=30).run()
    next(b for b in at.button if b.label == "Triage this case").click().run()
    assert not at.exception
    assert any("LULULEMON** vs **LULULEMOON" in str(m.value) for m in at.markdown)
