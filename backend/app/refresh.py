from __future__ import annotations

import json
import logging
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any

from .database import SOURCE_ID, connect, initialize_database
from .estat import PARSER_VERSION, Dataset, fetch_dataset

logger = logging.getLogger(__name__)
_refresh_lock = threading.Lock()
STALE_RUN_SECONDS = 15 * 60


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def is_refresh_running() -> bool:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT 1 FROM refresh_run
            WHERE status = 'running'
              AND julianday(started_at) >= julianday('now', ?)
            LIMIT 1
            """,
            (f"-{STALE_RUN_SECONDS} seconds",),
        ).fetchone()
        return row is not None


def refresh_estat() -> dict[str, Any]:
    if not _refresh_lock.acquire(blocking=False):
        return {"status": "already_running", "rows_imported": 0}
    started = utc_now()
    run_id: int | None = None
    try:
        initialize_database()
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired_before = (
                datetime.now(timezone.utc) - timedelta(seconds=STALE_RUN_SECONDS)
            ).isoformat(timespec="seconds")
            connection.execute(
                """
                UPDATE refresh_run
                SET finished_at = ?, status = 'failed',
                    error_summary = 'Refresh worker exceeded its 15-minute lock lease.'
                WHERE status = 'running'
                  AND julianday(started_at) < julianday(?)
                """,
                (started, expired_before),
            )
            running = connection.execute(
                "SELECT id FROM refresh_run WHERE status = 'running' LIMIT 1"
            ).fetchone()
            if running:
                connection.rollback()
                return {"status": "already_running", "rows_imported": 0}
            cursor = connection.execute(
                """
                INSERT INTO refresh_run (source_id, started_at, status)
                VALUES (?, ?, 'running')
                """,
                (SOURCE_ID, started),
            )
            run_id = int(cursor.lastrowid)
            connection.commit()

        dataset = fetch_dataset()
        result = _save_dataset(run_id, started, dataset)
        return result
    except Exception as error:
        summary = f"{type(error).__name__}: {error}"[:500]
        logger.exception("e-Stat refresh failed: %s", summary)
        if run_id is not None:
            _save_failure(run_id, started, summary)
        return {
            "status": "failed",
            "rows_imported": 0,
            "error_summary": summary,
        }
    finally:
        _refresh_lock.release()


def _save_dataset(run_id: int, started: str, dataset: Dataset) -> dict[str, Any]:
    fetched_at = utc_now()
    if not dataset.observations:
        raise ValueError("e-Stat response contained no observations.")
    warnings = list(dataset.warnings)
    validation_summary = json.dumps(
        {
            "observation_count": len(dataset.observations),
            "periods": sorted({row.period for row in dataset.observations}),
            "warnings": warnings,
        },
        ensure_ascii=False,
    )
    status = "current" if not warnings else "parser_needs_attention"
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            """
            SELECT s.content_hash, s.parser_version, d.latest_period
            FROM data_source AS d
            LEFT JOIN source_snapshot AS s ON s.id = (
                SELECT id FROM source_snapshot
                WHERE source_id = d.id ORDER BY id DESC LIMIT 1
            )
            WHERE d.id = ?
            """,
            (SOURCE_ID,),
        ).fetchone()
        if (
            previous
            and previous["latest_period"]
            and dataset.latest_period < previous["latest_period"]
        ):
            raise ValueError(
                f"Latest source period regressed from {previous['latest_period']} "
                f"to {dataset.latest_period}; preserving the last validated data."
            )
        if (
            previous
            and previous["content_hash"] == dataset.content_hash
            and previous["parser_version"] == PARSER_VERSION
        ):
            connection.execute(
                """
                UPDATE data_source
                SET last_checked = ?, last_successful_fetch = ?,
                    latest_publication_date = ?, latest_period = ?, status = ?,
                    error_summary = ?
                WHERE id = ?
                """,
                (
                    fetched_at,
                    fetched_at,
                    dataset.publication_date,
                    dataset.latest_period,
                    status,
                    "; ".join(warnings[:5])[:500] if warnings else None,
                    SOURCE_ID,
                ),
            )
            connection.execute(
                """
                UPDATE refresh_run
                SET finished_at = ?, status = 'unchanged', rows_imported = 0,
                    validation_summary = ?, error_summary = ?
                WHERE id = ?
                """,
                (
                    fetched_at,
                    validation_summary,
                    "; ".join(warnings[:5])[:500] if warnings else None,
                    run_id,
                ),
            )
            connection.commit()
            return {
                "status": "unchanged",
                "rows_imported": 0,
                "latest_period": dataset.latest_period,
                "warnings": warnings,
            }
        cursor = connection.execute(
            """
            INSERT INTO source_snapshot
                (source_id, fetched_at, publication_date, latest_period,
                 content_hash, parser_version, validation_summary, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                SOURCE_ID,
                fetched_at,
                dataset.publication_date,
                dataset.latest_period,
                dataset.content_hash,
                PARSER_VERSION,
                validation_summary,
                dataset.raw_response,
            ),
        )
        snapshot_id = int(cursor.lastrowid)
        for observation in dataset.observations:
            values = observation.values
            connection.execute(
                """
                INSERT INTO coe_monthly_workload_observation (
                    period, bureau_code, bureau_name, hierarchy_type, parent_code,
                    sequence_number, accepted_total, old_receipts, new_receipts,
                    completed_total, issued, not_issued, completed_other,
                    pending_official, pending_calculated, unit, raw_values,
                    source_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(period, bureau_code) DO UPDATE SET
                    bureau_name = excluded.bureau_name,
                    hierarchy_type = excluded.hierarchy_type,
                    parent_code = excluded.parent_code,
                    sequence_number = excluded.sequence_number,
                    accepted_total = excluded.accepted_total,
                    old_receipts = excluded.old_receipts,
                    new_receipts = excluded.new_receipts,
                    completed_total = excluded.completed_total,
                    issued = excluded.issued,
                    not_issued = excluded.not_issued,
                    completed_other = excluded.completed_other,
                    pending_official = excluded.pending_official,
                    pending_calculated = excluded.pending_calculated,
                    unit = excluded.unit,
                    raw_values = excluded.raw_values,
                    source_snapshot_id = excluded.source_snapshot_id
                """,
                (
                    observation.period,
                    observation.bureau.code,
                    observation.bureau.name,
                    observation.bureau.hierarchy_type,
                    observation.bureau.parent_code,
                    observation.bureau.sequence_number,
                    values.get("accepted_total"),
                    values.get("old_receipts"),
                    values.get("new_receipts"),
                    values.get("completed_total"),
                    values.get("issued"),
                    values.get("not_issued"),
                    values.get("completed_other"),
                    values.get("pending_official"),
                    values.get("pending_calculated"),
                    observation.unit,
                    json.dumps(observation.raw_values, ensure_ascii=False),
                    snapshot_id,
                ),
            )
        connection.execute(
            """
            UPDATE data_source
            SET last_checked = ?, last_successful_fetch = ?,
                latest_publication_date = ?, latest_period = ?, status = ?,
                error_summary = ?
            WHERE id = ?
            """,
            (
                fetched_at,
                fetched_at,
                dataset.publication_date,
                dataset.latest_period,
                status,
                "; ".join(warnings[:5])[:500] if warnings else None,
                SOURCE_ID,
            ),
        )
        connection.execute(
            """
            UPDATE refresh_run
            SET finished_at = ?, status = ?, rows_imported = ?,
                validation_summary = ?, error_summary = ?
            WHERE id = ?
            """,
            (
                fetched_at,
                "succeeded" if not warnings else "succeeded_with_warnings",
                len(dataset.observations),
                validation_summary,
                "; ".join(warnings[:5])[:500] if warnings else None,
                run_id,
            ),
        )
        connection.commit()
    logger.info(
        "Imported %s e-Stat observations through %s",
        len(dataset.observations),
        dataset.latest_period,
    )
    return {
        "status": "succeeded" if not warnings else "succeeded_with_warnings",
        "rows_imported": len(dataset.observations),
        "latest_period": dataset.latest_period,
        "warnings": warnings,
    }


def _save_failure(run_id: int, started: str, summary: str) -> None:
    finished = utc_now()
    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                UPDATE data_source
                SET last_checked = ?, status = 'refresh_failed', error_summary = ?
                WHERE id = ?
                """,
                (finished, summary, SOURCE_ID),
            )
            connection.execute(
                """
                UPDATE refresh_run
                SET finished_at = ?, status = 'failed', error_summary = ?
                WHERE id = ?
                """,
                (finished, summary, run_id),
            )
            connection.commit()
    except sqlite3.Error:
        logger.exception("Could not save refresh failure state.")


def refresh_in_background() -> bool:
    if _refresh_lock.locked():
        return False
    thread = threading.Thread(target=refresh_estat, name="estat-refresh", daemon=True)
    thread.start()
    return True
