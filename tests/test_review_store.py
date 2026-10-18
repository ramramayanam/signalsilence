"""Analyst review persistence: append-only SQLite decision log.

Every test uses a temporary database (pytest tmp_path); the real
reviews.db is never touched.
"""
import json
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from signalsilence import review_store  # noqa: E402
from signalsilence.demo_cases import CANONICAL  # noqa: E402
from signalsilence.schema import Case  # noqa: E402
from signalsilence.triage import triage  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEMO = {c.case_id: c for c in CANONICAL.values()}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "reviews.db"
    review_store.init_db(path)
    return path


def _record(db, case_id="demo_1", decision="confirm_flag", note=None):
    case = DEMO[case_id]
    return review_store.record_decision(
        db, case, triage(case, use_llm=False), decision, note,
        assessment_mode="offline heuristic context judgment")


def test_init_creates_schema(db):
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert "review_events" in tables
        assert conn.execute("PRAGMA user_version").fetchone()[0] == review_store.SCHEMA_VERSION


def test_repeated_init_is_safe_and_keeps_data(db):
    _record(db)
    review_store.init_db(db)
    review_store.init_db(db)
    assert len(review_store.case_history(db, "demo_1")) == 1


def test_unreviewed_case_has_unreviewed_status(db):
    assert review_store.review_status(db, "demo_1") == review_store.UNREVIEWED
    assert review_store.case_history(db, "demo_1") == []
    assert review_store.latest_decisions(db) == {}


def test_saving_a_decision_records_system_snapshot(db):
    case = DEMO["demo_3"]
    result = triage(case, use_llm=False)
    _record(db, "demo_3", "refer_legal_review")
    [event] = review_store.case_history(db, "demo_3")
    assert event["protected_mark"] == "BATA"
    assert event["candidate_mark"] == "BAATA LACES"
    assert event["system_risk"] == result.risk.value
    assert event["system_action"] == result.action.value
    assert event["lexical_similarity"] == result.scores.lexical
    assert event["phonetic_similarity"] == result.scores.phonetic
    assert event["assessment_mode"] == "offline heuristic context judgment"
    assert event["recorded_at"].endswith("+00:00")
    snap = json.loads(event["system_snapshot"])
    assert snap["system_assessment"]["invariant_notes"] == result.invariant_notes
    assert snap["system_assessment"]["context"]["goods_adjacent"] == result.context.goods_adjacent
    assert snap["case_inputs"]["candidate_goods"] == "shoelaces"
    assert review_store.review_status(db, "demo_3") == "Referred for Legal Review"


def test_changed_decision_keeps_prior_history(db):
    _record(db, "demo_1", "confirm_flag", "Strong phonetic similarity.")
    _record(db, "demo_1", "dismiss_flag", "Applicant later shown to be licensee.")
    history = review_store.case_history(db, "demo_1")
    assert [e["analyst_decision"] for e in history] == ["confirm_flag", "dismiss_flag"]
    assert history[0]["analyst_note"] == "Strong phonetic similarity."
    assert review_store.review_status(db, "demo_1") == "Dismissed"
    assert review_store.latest_decisions(db)["demo_1"]["analyst_decision"] == "dismiss_flag"


def test_latest_decisions_is_per_case(db):
    _record(db, "demo_1", "confirm_flag")
    _record(db, "demo_4", "dismiss_flag")
    latest = review_store.latest_decisions(db)
    assert set(latest) == {"demo_1", "demo_4"}
    assert review_store.review_status(db, "demo_2") == review_store.UNREVIEWED


def test_notes_are_kept_and_blank_notes_stored_as_null(db):
    _record(db, "demo_1", note="  Same class but unrelated goods.  ")
    _record(db, "demo_1", note="   ")
    _record(db, "demo_1", note=None)
    notes = [e["analyst_note"] for e in review_store.case_history(db, "demo_1")]
    assert notes == ["Same class but unrelated goods.", None, None]


def test_history_is_append_only(db):
    _record(db)
    with sqlite3.connect(db) as conn:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("UPDATE review_events SET analyst_decision='dismiss_flag'")
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM review_events")
    assert len(review_store.case_history(db, "demo_1")) == 1


def test_unknown_decision_rejected(db):
    with pytest.raises(ValueError):
        _record(db, decision="escalate")  # system vocabulary, not an analyst decision
    assert review_store.case_history(db, "demo_1") == []


def test_decision_vocabulary_is_distinct_from_system_action():
    assert list(review_store.DECISIONS.values()) == [
        "Confirm Flag", "Dismiss Flag", "Refer for Legal Review"]
    assert not any("escalate" in d.lower() for d in review_store.DECISIONS.values())


def test_missing_optional_data_is_stored_without_fabrication(db):
    case = Case("custom_1", "ACME", "AKME", candidate_class=None,
                candidate_goods=None, applicant_name=None,
                owner_entity_type=None, goods_class_overlap=False)
    review_store.record_decision(db, case, triage(case, use_llm=False), "dismiss_flag")
    [event] = review_store.case_history(db, "custom_1")
    inputs = json.loads(event["system_snapshot"])["case_inputs"]
    assert inputs["candidate_goods"] is None and inputs["applicant_name"] is None
    assert inputs["recent_filing_count"] is None
    assert event["analyst_note"] is None and event["assessment_mode"] is None


def test_default_db_path_honours_env(monkeypatch, tmp_path):
    monkeypatch.setenv("SIGNALSILENCE_REVIEW_DB", str(tmp_path / "x.db"))
    assert review_store.default_db_path() == tmp_path / "x.db"
    monkeypatch.delenv("SIGNALSILENCE_REVIEW_DB")
    assert review_store.default_db_path() == REPO / "reviews.db"


@pytest.mark.skipif(shutil.which("git") is None or not (REPO / ".git").exists(),
                    reason="needs a git checkout")
def test_review_database_is_gitignored_and_untracked():
    for name in ("reviews.db", "reviews.db-journal", "reviews.db-wal"):
        assert subprocess.run(["git", "check-ignore", "-q", name], cwd=REPO).returncode == 0, name
    tracked = subprocess.run(["git", "ls-files", "reviews.db*", "*.db"], cwd=REPO,
                             capture_output=True, text=True, check=True).stdout
    assert tracked == ""


# --- Rules version provenance (schema v2) ---

def test_policy_version_is_recorded_on_each_event(db):
    from signalsilence.policy import POLICY_VERSION
    assert POLICY_VERSION == "rules-v3"
    _record(db)
    [event] = review_store.case_history(db, "demo_1")
    assert event["policy_version"] == POLICY_VERSION
    assert json.loads(event["system_snapshot"])["policy_version"] == POLICY_VERSION


# Exact DDL shipped in commit 1954d11 (schema v1), to prove upgrades are safe.
_V1_SCHEMA = """
CREATE TABLE review_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL,
    protected_mark TEXT NOT NULL, candidate_mark TEXT NOT NULL,
    system_risk TEXT NOT NULL, system_action TEXT NOT NULL,
    lexical_similarity REAL, phonetic_similarity REAL, assessment_mode TEXT,
    system_snapshot TEXT NOT NULL,
    analyst_decision TEXT NOT NULL CHECK (analyst_decision IN
        ('confirm_flag', 'dismiss_flag', 'refer_legal_review')),
    analyst_note TEXT, recorded_at TEXT NOT NULL);
CREATE TRIGGER review_events_no_update BEFORE UPDATE ON review_events
    BEGIN SELECT RAISE(ABORT, 'review_events is append-only'); END;
CREATE TRIGGER review_events_no_delete BEFORE DELETE ON review_events
    BEGIN SELECT RAISE(ABORT, 'review_events is append-only'); END;
PRAGMA user_version = 1;
INSERT INTO review_events (case_id, protected_mark, candidate_mark, system_risk,
    system_action, lexical_similarity, phonetic_similarity, assessment_mode,
    system_snapshot, analyst_decision, analyst_note, recorded_at)
VALUES ('demo_1', 'LULULEMON', 'LULULEMMON', 'high', 'escalate', 0.98, 1.0,
    'offline heuristic context judgment', '{}', 'confirm_flag', 'v1 note',
    '2026-10-17T00:00:00+00:00');
"""


def test_v1_database_upgrades_additively(tmp_path):
    path = tmp_path / "v1.db"
    with closing(sqlite3.connect(path)) as conn:
        conn.executescript(_V1_SCHEMA)
    review_store.init_db(path)
    review_store.init_db(path)  # repeated upgrade is a no-op
    _record(path, "demo_1", "dismiss_flag")
    old, new = review_store.case_history(path, "demo_1")
    assert old["analyst_note"] == "v1 note" and old["policy_version"] is None
    assert new["policy_version"] == "rules-v3"
    assert review_store.review_status(path, "demo_1") == "Dismissed"
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM review_events")
