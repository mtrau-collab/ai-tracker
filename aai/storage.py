"""SQLite persistence for cases and index snapshots.

Two tables:
  - cases: one row per discovered AttributionCase (deduplicated by case_id)
  - snapshots: one row per run_update call, holding computed index values

Using stdlib sqlite3 keeps the project dependency-light. JSON columns
hold lists (source_urls) and the full case payload for easy round-tripping.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from .schema import AttributionCase, CaseType, IndexSnapshot, Resolution, HybridizationKind


DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "cases.db"


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS cases (
    case_id              TEXT PRIMARY KEY,
    case_type            TEXT NOT NULL,
    artwork_title        TEXT NOT NULL,
    claimed_artist       TEXT NOT NULL,
    estimated_value_usd  REAL,
    ai_tool              TEXT,
    institution          TEXT,
    resolution           TEXT,
    hybridization_kind   TEXT,
    source_urls_json     TEXT NOT NULL DEFAULT '[]',
    reasoning            TEXT NOT NULL DEFAULT '',
    confidence           REAL NOT NULL DEFAULT 0.0,
    event_date           TEXT,
    discovered_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cases_type       ON cases(case_type);
CREATE INDEX IF NOT EXISTS idx_cases_resolution ON cases(resolution);
CREATE INDEX IF NOT EXISTS idx_cases_event_date ON cases(event_date);

CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_at              TEXT PRIMARY KEY,
    money_weighted_dri       REAL,
    hybridization_index      REAL,
    instability_share        REAL,
    divergence_cases_total   INTEGER NOT NULL DEFAULT 0,
    hybridization_cases_total INTEGER NOT NULL DEFAULT 0,
    window_days              INTEGER NOT NULL DEFAULT 365
);
"""


def init_db(db_path: Path = DEFAULT_DB_PATH) -> Path:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA_SQL)
    return db_path


@contextmanager
def connect(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
    init_db(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert_case(case: AttributionCase, db_path: Path = DEFAULT_DB_PATH) -> bool:
    """Insert or replace a case. Returns True if this was a new case_id."""
    with connect(db_path) as con:
        existed = con.execute(
            "SELECT 1 FROM cases WHERE case_id = ?", (case.case_id,)
        ).fetchone() is not None

        con.execute(
            """
            INSERT INTO cases (
                case_id, case_type, artwork_title, claimed_artist,
                estimated_value_usd, ai_tool, institution,
                resolution, hybridization_kind,
                source_urls_json, reasoning, confidence,
                event_date, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                estimated_value_usd = excluded.estimated_value_usd,
                ai_tool             = excluded.ai_tool,
                institution         = excluded.institution,
                resolution          = excluded.resolution,
                hybridization_kind  = excluded.hybridization_kind,
                source_urls_json    = excluded.source_urls_json,
                reasoning           = excluded.reasoning,
                confidence          = excluded.confidence,
                event_date          = excluded.event_date
            """,
            (
                case.case_id,
                case.case_type.value,
                case.artwork_title,
                case.claimed_artist,
                case.estimated_value_usd,
                case.ai_tool,
                case.institution,
                case.resolution.value if case.resolution else None,
                case.hybridization_kind.value if case.hybridization_kind else None,
                json.dumps(case.source_urls),
                case.reasoning,
                case.confidence,
                case.event_date,
                case.discovered_at,
            ),
        )
        return not existed


def list_cases(
    db_path: Path = DEFAULT_DB_PATH,
    case_type: Optional[CaseType] = None,
    min_confidence: float = 0.0,
) -> list[AttributionCase]:
    query = "SELECT * FROM cases WHERE confidence >= ?"
    args: list = [min_confidence]
    if case_type is not None:
        query += " AND case_type = ?"
        args.append(case_type.value)
    query += " ORDER BY COALESCE(event_date, discovered_at) DESC"

    with connect(db_path) as con:
        rows = con.execute(query, args).fetchall()

    out: list[AttributionCase] = []
    for r in rows:
        out.append(AttributionCase(
            case_id=r["case_id"],
            case_type=CaseType(r["case_type"]),
            artwork_title=r["artwork_title"],
            claimed_artist=r["claimed_artist"],
            estimated_value_usd=r["estimated_value_usd"],
            ai_tool=r["ai_tool"],
            institution=r["institution"],
            resolution=Resolution(r["resolution"]) if r["resolution"] else None,
            hybridization_kind=HybridizationKind(r["hybridization_kind"]) if r["hybridization_kind"] else None,
            source_urls=json.loads(r["source_urls_json"] or "[]"),
            reasoning=r["reasoning"] or "",
            confidence=r["confidence"] or 0.0,
            event_date=r["event_date"],
            discovered_at=r["discovered_at"],
        ))
    return out


def write_snapshot(snap: IndexSnapshot, db_path: Path = DEFAULT_DB_PATH) -> None:
    with connect(db_path) as con:
        con.execute(
            """
            INSERT OR REPLACE INTO snapshots (
                snapshot_at, money_weighted_dri, hybridization_index,
                instability_share, divergence_cases_total,
                hybridization_cases_total, window_days
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snap.snapshot_at,
                snap.money_weighted_dri,
                snap.hybridization_index,
                snap.instability_share,
                snap.divergence_cases_total,
                snap.hybridization_cases_total,
                snap.window_days,
            ),
        )


def list_snapshots(db_path: Path = DEFAULT_DB_PATH) -> list[IndexSnapshot]:
    with connect(db_path) as con:
        rows = con.execute(
            "SELECT * FROM snapshots ORDER BY snapshot_at ASC"
        ).fetchall()
    return [IndexSnapshot(**dict(r)) for r in rows]
