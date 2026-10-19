"""The five canonical demo cases.

Shared by the demo page (app.py) and the analyst review queue
(pages/1_Analyst_Review.py) so both always show the same cases.
Values are exactly those originally defined inline in app.py.
"""
from .schema import Case

DATA_SOURCE_TYPE = "synthetic_demo_case"


def data_source(case_id: str) -> dict:
    """Truthful source descriptor for a canonical demo case.

    These cases are hand-authored in this module; they are not USPTO
    records and carry no serial number, registration or retrieval time.
    """
    return {"type": DATA_SOURCE_TYPE, "reference": f"demo_cases:{case_id}"}

CANONICAL = {
    "LULULEMMON — near-identical, same class": Case(
        "demo_1", "LULULEMON", "LULULEMMON", "025", "clothing",
        "Global Brand Holdings Ltd", "corporation", True, recent_filing_count=2),
    "NIKKE — behavioral signal (18 filings / 30 days)": Case(
        "demo_2", "NIKE", "NIKKE", "025", "clothing",
        "Global Brand Holdings Ltd", "corporation", True, recent_filing_count=18),
    "BAATA LACES — adjacency across classes": Case(
        "demo_3", "BATA", "BAATA LACES", "026", "shoelaces",
        "Standard", "corporation", False, recent_filing_count=0),
    "LULULIME juice bar — high similarity, unrelated goods": Case(
        "demo_4", "LULULEMON", "LULULIME", "043", "juice bar / food service",
        "Local small business", "individual", False, recent_filing_count=0),
    "PHISH vs FISH — phonetic edge case": Case(
        "demo_5", "PHISH", "FISH", "043", "juice bar / food service",
        "Local small business", "individual", False, recent_filing_count=0),
}
