"""Analyst review persistence: an append-only decision log in SQLite.

Design decision: SignalSilence recommends, the analyst decides. Each
analyst decision is stored as a new event row together with a snapshot
of the system assessment the analyst was looking at. Rows are never
updated or deleted (enforced by triggers), so a changed decision adds a
new event and the full history stays reconstructable. Current review
status is derived from the latest event for a case.

Only review state lives here. The synthetic dataset, the scoring
pipeline and its outputs are untouched by this module.

No reviewer identity is stored: the app has no authentication, and an
unverified name would be a fabricated audit field.

Schema history (additive only):
  v1  review_events table, append-only triggers.
  v2  + policy_version column (rules version at decision time). Rows
      written under v1 keep NULL: their rules version was not recorded.
"""
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .policy import POLICY_VERSION
from .schema import Case, TriageResult

SCHEMA_VERSION = 2

# Analyst decision vocabulary. Deliberately distinct from the system's
# Action.ESCALATE recommendation: the analyst never "escalates", they
# confirm, dismiss, or refer.
DECISIONS = {
    "confirm_flag": "Confirm Flag",
    "dismiss_flag": "Dismiss Flag",
    "refer_legal_review": "Refer for Legal Review",
}
STATUS = {
    "confirm_flag": "Confirmed",
    "dismiss_flag": "Dismissed",
    "refer_legal_review": "Referred for Legal Review",
}
UNREVIEWED = "Unreviewed"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS review_events (
    event_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id             TEXT NOT NULL,
    protected_mark      TEXT NOT NULL,
    candidate_mark      TEXT NOT NULL,
    system_risk         TEXT NOT NULL,
    system_action       TEXT NOT NULL,
    lexical_similarity  REAL,
    phonetic_similarity REAL,
    assessment_mode     TEXT,
    policy_version      TEXT,
    system_snapshot     TEXT NOT NULL,
    analyst_decision    TEXT NOT NULL CHECK (analyst_decision IN
                            ('confirm_flag', 'dismiss_flag', 'refer_legal_review')),
    analyst_note        TEXT,
    recorded_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_review_events_case
    ON review_events (case_id, event_id);
CREATE TRIGGER IF NOT EXISTS review_events_no_update
    BEFORE UPDATE ON review_events
    BEGIN SELECT RAISE(ABORT, 'review_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS review_events_no_delete
    BEFORE DELETE ON review_events
    BEGIN SELECT RAISE(ABORT, 'review_events is append-only'); END;
"""


def default_db_path() -> Path:
    """SIGNALSILENCE_REVIEW_DB if set, else reviews.db at the repo root (gitignored)."""
    env = os.environ.get("SIGNALSILENCE_REVIEW_DB")
    return Path(env) if env else Path(__file__).resolve().parents[2] / "reviews.db"


def _connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path) -> None:
    """Create or upgrade the schema. Safe to run repeatedly; never drops or alters data."""
    with closing(_connect(db_path)) as conn, conn:
        conn.executescript(_SCHEMA)
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(review_events)")}
        if "policy_version" not in columns:  # v1 database: additive upgrade
            conn.execute("ALTER TABLE review_events ADD COLUMN policy_version TEXT")
        if conn.execute("PRAGMA user_version").fetchone()[0] < SCHEMA_VERSION:
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def record_decision(db_path, case: Case, result: TriageResult, decision: str,
                    note: str | None = None,
                    assessment_mode: str | None = None, *,
                    data_source: dict | None = None,
                    assessed_at: str | None = None) -> int:
    """Append one analyst decision with a snapshot of the system assessment.

    Returns the new event_id. A blank note is stored as NULL. The rules
    version is policy.POLICY_VERSION: the assessment being reviewed was
    produced by the policy module loaded in this process.

    Optional capture-time provenance, supplied by the caller and stored in
    the snapshot only when given (older callers simply omit it):
      data_source  where the reviewed case came from, e.g.
                   {"type": "synthetic_demo_case", "reference": "demo_cases:demo_1"}
      assessed_at  UTC ISO-8601 time the reviewed assessment was produced
                   (not the decision time, which is recorded_at)
    """
    if decision not in DECISIONS:
        raise ValueError(f"unknown analyst decision: {decision!r}")
    note = (note or "").strip() or None
    snapshot = {"case_inputs": asdict(case), "system_assessment": asdict(result),
                "policy_version": POLICY_VERSION}
    if data_source is not None:
        snapshot["data_source"] = data_source
    if assessed_at is not None:
        snapshot["assessed_at"] = assessed_at
    init_db(db_path)
    with closing(_connect(db_path)) as conn, conn:
        cur = conn.execute(
            """INSERT INTO review_events (
                   case_id, protected_mark, candidate_mark, system_risk,
                   system_action, lexical_similarity, phonetic_similarity,
                   assessment_mode, policy_version, system_snapshot,
                   analyst_decision, analyst_note, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (case.case_id, case.protected_mark, case.candidate_mark,
             result.risk.value, result.action.value,
             result.scores.lexical, result.scores.phonetic,
             assessment_mode, POLICY_VERSION, json.dumps(snapshot, sort_keys=True),
             decision, note,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        return cur.lastrowid


def case_history(db_path, case_id: str) -> list:
    """All decision events for a case, oldest first."""
    init_db(db_path)
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM review_events WHERE case_id = ? ORDER BY event_id",
            (case_id,)).fetchall()
    return [dict(r) for r in rows]


def list_events(db_path) -> list:
    """All decision events across cases in recording (event) order. Strictly read-only.

    Opens the database read-only and never creates or upgrades it (unlike
    the other helpers, which call init_db): a missing database means no
    decisions yet, and old rows are returned exactly as stored.
    """
    path = Path(db_path)
    if not path.exists():
        return []
    uri = f"{path.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "review_events" not in tables:
            return []
        rows = conn.execute("SELECT * FROM review_events ORDER BY event_id").fetchall()
    return [dict(r) for r in rows]


def latest_decisions(db_path) -> dict:
    """Latest decision event per case_id, for the queue view."""
    init_db(db_path)
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            """SELECT * FROM review_events WHERE event_id IN (
                   SELECT MAX(event_id) FROM review_events GROUP BY case_id)"""
        ).fetchall()
    return {r["case_id"]: dict(r) for r in rows}


def review_status(db_path, case_id: str) -> str:
    """Current review status: derived from the latest event, else Unreviewed."""
    history = case_history(db_path, case_id)
    return STATUS[history[-1]["analyst_decision"]] if history else UNREVIEWED
