from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .config import database_path


INITIAL_SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS data_source (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    source_url TEXT NOT NULL,
    measure TEXT NOT NULL,
    unit TEXT,
    frequency TEXT,
    parser_version TEXT NOT NULL,
    last_checked TEXT,
    last_successful_fetch TEXT,
    latest_publication_date TEXT,
    latest_period TEXT,
    status TEXT NOT NULL DEFAULT 'not_yet_configured',
    error_summary TEXT
);
CREATE TABLE IF NOT EXISTS source_snapshot (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES data_source(id),
    fetched_at TEXT NOT NULL,
    publication_date TEXT,
    latest_period TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    parser_version TEXT NOT NULL,
    validation_summary TEXT NOT NULL,
    raw_response BLOB NOT NULL
);
CREATE TABLE IF NOT EXISTS coe_monthly_workload_observation (
    period TEXT NOT NULL,
    bureau_code TEXT NOT NULL,
    bureau_name TEXT NOT NULL,
    hierarchy_type TEXT NOT NULL,
    parent_code TEXT,
    sequence_number INTEGER NOT NULL,
    accepted_total INTEGER,
    old_receipts INTEGER,
    new_receipts INTEGER,
    completed_total INTEGER,
    issued INTEGER,
    not_issued INTEGER,
    completed_other INTEGER,
    pending_official INTEGER,
    pending_calculated INTEGER,
    unit TEXT NOT NULL,
    raw_values TEXT NOT NULL,
    source_snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(id),
    PRIMARY KEY (period, bureau_code)
);
CREATE TABLE IF NOT EXISTS refresh_run (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL REFERENCES data_source(id),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    rows_imported INTEGER NOT NULL DEFAULT 0,
    validation_summary TEXT,
    error_summary TEXT
);
CREATE INDEX IF NOT EXISTS ix_workload_period
    ON coe_monthly_workload_observation(period);
CREATE INDEX IF NOT EXISTS ix_snapshot_source
    ON source_snapshot(source_id, fetched_at);
CREATE TABLE IF NOT EXISTS schema_migration (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""

SOURCE_ID = "estat-monthly-coe-workload"
SOURCE_ROWS = (
    (
        SOURCE_ID,
        "Monthly COE applications received and processed by bureau",
        "Immigration Services Agency of Japan / e-Stat",
        "https://www.e-stat.go.jp/dbview?sid=0004049310",
        "Monthly aggregate workload and outcomes; not case-level duration data",
        "人",
        "Monthly",
        "1.0.0",
        "official_government_statistics",
        "Daily source check; refresh on dashboard open when due",
    ),
    (
        "isa-processing-time-discovery",
        "ISA COE processing-time publications",
        "Immigration Services Agency of Japan",
        "https://www.moj.go.jp/isa/applications/status/gijinkoku.html",
        "Processing-time reports; no compatible duration series imported",
        "Not confirmed",
        "Not confirmed",
        "not_configured",
        "official_government_website",
        "Manual verification required before automated import",
    ),
)


def initialize_database(path: Path | None = None) -> None:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as connection:
        connection.executescript(INITIAL_SCHEMA)
        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migration")
        }
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if 1 not in applied:
            connection.execute(
                "INSERT INTO schema_migration (version, applied_at) VALUES (1, ?)",
                (now,),
            )
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(data_source)")
        }
        if "source_type" not in columns:
            connection.execute(
                "ALTER TABLE data_source ADD COLUMN source_type TEXT NOT NULL DEFAULT 'official_government_statistics'"
            )
        if "update_policy" not in columns:
            connection.execute(
                "ALTER TABLE data_source ADD COLUMN update_policy TEXT NOT NULL DEFAULT 'Daily source check; refresh on dashboard open when due'"
            )
        if 2 not in applied:
            connection.execute(
                "INSERT INTO schema_migration (version, applied_at) VALUES (2, ?)",
                (now,),
            )
        for source_row in SOURCE_ROWS:
            connection.execute(
                """
                INSERT INTO data_source
                    (id, name, owner, source_url, measure, unit, frequency,
                     parser_version, source_type, update_policy)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    owner = excluded.owner,
                    source_url = excluded.source_url,
                    measure = excluded.measure,
                    unit = excluded.unit,
                    frequency = excluded.frequency,
                    parser_version = excluded.parser_version,
                    source_type = excluded.source_type,
                    update_policy = excluded.update_policy
                """,
                source_row,
            )


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = path or database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
