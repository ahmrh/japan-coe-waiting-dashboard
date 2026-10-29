from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from .config import refresh_interval_seconds
from .database import SOURCE_ID, connect
from .refresh import is_refresh_running, refresh_in_background

router = APIRouter(prefix="/api")
FIELD_LABELS = {
    "accepted_total": "Total workload available",
    "old_receipts": "Carried-over cases",
    "new_receipts": "New receipts",
    "completed_total": "Total completed",
    "issued": "Issued",
    "not_issued": "Not issued",
    "completed_other": "Other closures / transfers",
    "pending_official": "Official pending balance",
    "pending_calculated": "Calculated pending balance",
}


def _source_record() -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT * FROM data_source WHERE id = ?", (SOURCE_ID,)
        ).fetchone()
    return dict(row) if row else None


def _observations(
    period: str | None = None,
    bureau_code: str | None = None,
    hierarchy: str = "jurisdictions",
) -> list[dict[str, Any]]:
    clauses: list[str] = []
    params: list[str] = []
    if period:
        clauses.append("period = ?")
        params.append(period)
    if bureau_code:
        clauses.append("bureau_code = ?")
        params.append(bureau_code)
    elif hierarchy == "jurisdictions":
        clauses.append("hierarchy_type IN ('national_total', 'bureau_jurisdiction')")
    elif hierarchy == "offices":
        clauses.append("hierarchy_type = 'office'")
    elif hierarchy == "all":
        clauses.append("1 = 1")
    else:
        raise HTTPException(status_code=422, detail="Unknown hierarchy mode.")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT period, bureau_code, bureau_name, hierarchy_type, parent_code,
                   sequence_number, accepted_total, old_receipts, new_receipts,
                   completed_total, issued, not_issued, completed_other,
                   pending_official, pending_calculated, unit, raw_values
            FROM coe_monthly_workload_observation
            {where}
            ORDER BY period DESC, sequence_number
            """,
            params,
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["raw_values"] = json.loads(item["raw_values"])
        receipt_values = (
            item["accepted_total"],
            item["old_receipts"],
            item["new_receipts"],
        )
        completion_values = (
            item["completed_total"],
            item["issued"],
            item["not_issued"],
            item["completed_other"],
        )
        item["receipt_total_reconciles"] = (
            all(value is not None for value in receipt_values)
            and item["accepted_total"] == item["old_receipts"] + item["new_receipts"]
        )
        item["completion_total_reconciles"] = (
            all(value is not None for value in completion_values)
            and item["completed_total"]
            == item["issued"] + item["not_issued"] + item["completed_other"]
        )
        item["pending_value"] = (
            item["pending_official"]
            if item["pending_official"] is not None
            else item["pending_calculated"]
        )
        item["pending_label"] = (
            "Officially published"
            if item["pending_official"] is not None
            else "Calculated by the app"
            if item["pending_calculated"] is not None
            else None
        )
        item["throughput_ratio"] = (
            item["completed_total"] / item["accepted_total"]
            if item["accepted_total"] not in (None, 0)
            and item["completed_total"] is not None
            and item["receipt_total_reconciles"]
            and item["completion_total_reconciles"]
            else None
        )
        result.append(item)
    return result


def _freshness() -> dict[str, Any]:
    source = _source_record()
    if not source:
        return {
            "id": SOURCE_ID,
            "status": "not_yet_configured",
            "error_summary": "No e-Stat source record is available.",
        }
    status = source["status"]
    if source["last_checked"] and status in {"current", "parser_needs_attention"}:
        try:
            checked = datetime.fromisoformat(source["last_checked"])
            if (
                (datetime.now(timezone.utc) - checked.astimezone(timezone.utc)).total_seconds()
                >= refresh_interval_seconds()
            ):
                status = "stale"
        except ValueError:
            status = "stale"
    return {
        "id": source["id"],
        "name": source["name"],
        "owner": source["owner"],
        "url": source["source_url"],
        "source_type": source["source_type"],
        "update_policy": source["update_policy"],
        "measure": source["measure"],
        "unit": source["unit"],
        "frequency": source["frequency"],
        "last_checked": source["last_checked"],
        "last_successful_fetch": source["last_successful_fetch"],
        "latest_publication_date": source["latest_publication_date"],
        "latest_period": source["latest_period"],
        "status": status,
        "error_summary": source["error_summary"],
        "limitations": [
            "These are monthly aggregate workload counts, not individual case durations.",
            "The table reports statistical processing outcomes; it cannot predict an individual COE decision or completion date.",
            "The app calculates month-end pending balance when both totals reconcile; this is not a separately published e-Stat measure.",
        ],
    }


@router.get("/health")
def health() -> dict[str, str]:
    with connect() as connection:
        connection.execute("SELECT 1").fetchone()
    return {"status": "ok"}


@router.get("/overview")
def overview(request: Request) -> dict[str, Any]:
    source = _freshness()
    _queue_refresh_if_due(request, source)
    records = _observations(hierarchy="all")
    periods = sorted({row["period"] for row in records}, reverse=True)
    latest_period = periods[0] if periods else None
    latest = _observations(period=latest_period) if latest_period else []
    previous_period = periods[1] if len(periods) > 1 else None
    previous = (
        {row["bureau_code"]: row for row in _observations(period=previous_period)}
        if previous_period
        else {}
    )
    for item in latest:
        old = previous.get(item["bureau_code"])
        item["pending_change"] = (
            item["pending_value"] - old["pending_value"]
            if old
            and item["pending_value"] is not None
            and old["pending_value"] is not None
            else None
        )
    return {
        "title": "COE Processing — Monthly Workload and Outcomes",
        "latest_period": latest_period,
        "previous_period": previous_period,
        "available_periods": periods,
        "field_labels": FIELD_LABELS,
        "source": source,
        "rows": latest,
        "observations": records,
        "summary": _summary(latest, latest_period, previous_period),
        "refresh_queued": bool(request.app.state.refresh_queued),
    }


def _summary(
    rows: list[dict[str, Any]], latest: str | None, previous: str | None
) -> str:
    national = next((row for row in rows if row["hierarchy_type"] == "national_total"), None)
    if not national or not latest:
        return "Official monthly workload data is not yet available."
    period_label = f"{latest[:4]}-{latest[5:]}"
    pending = national["pending_value"]
    new_receipts = (
        f"{national['new_receipts']:,}" if national["new_receipts"] is not None else "unavailable"
    )
    completed = (
        f"{national['completed_total']:,}" if national["completed_total"] is not None else "unavailable"
    )
    pending_label = (
        f"{pending:,} cases in the {national['pending_label'].lower()} pending balance"
        if pending is not None
        else "no validated pending balance"
    )
    parts = [
        f"The latest available e-Stat period is {period_label}.",
        f"Japan reported {new_receipts} people under 受理_新受 and {completed} "
        "under 既済_総数 (unit: 人).",
        f"The total available workload was {national['accepted_total']:,}. "
        + (
            f"{pending:,} people remain in the month-end pending balance "
            f"({national['pending_label'].lower()})."
            if pending is not None
            else f"There is {pending_label}."
        )
        if national["accepted_total"] is not None
        else f"There is {pending_label}.",
    ]
    if previous:
        old = {
            row["bureau_code"]: row
            for row in _observations(period=previous)
        }.get(national["bureau_code"])
        if old and pending is not None and old["pending_value"] is not None:
            change = pending - old["pending_value"]
            verb = "increased" if change > 0 else "decreased" if change < 0 else "was unchanged"
            parts.append(
                f"Compared with {previous[:4]}-{previous[5:]}, this balance {verb}"
                + (f" by {abs(change):,}." if change else ".")
            )
    parts.append(
        "These counts describe office workload; they are not processing-time estimates "
        "or predictions for any individual case."
    )
    return " ".join(parts)


def _queue_refresh_if_due(request: Request, source: dict[str, Any]) -> None:
    request.app.state.refresh_queued = False
    checked = source.get("last_checked")
    if not checked:
        refresh_in_background()
        request.app.state.refresh_queued = True
        return
    try:
        last_checked = datetime.fromisoformat(checked)
    except ValueError:
        request.app.state.refresh_queued = refresh_in_background()
        return
    age = datetime.now(timezone.utc) - last_checked.astimezone(timezone.utc)
    if age.total_seconds() >= request.app.state.refresh_interval_seconds:
        started = refresh_in_background()
        request.app.state.refresh_queued = started or is_refresh_running()


@router.get("/application-volumes")
def application_volumes(
    period: str | None = None,
    bureau_code: str | None = None,
    hierarchy: str = "jurisdictions",
) -> dict[str, Any]:
    return {
        "unit": "人",
        "period": period,
        "hierarchy": hierarchy,
        "fields": FIELD_LABELS,
        "observations": _observations(period, bureau_code, hierarchy),
        "source": _freshness(),
    }


@router.get("/sources")
def sources() -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM data_source WHERE id != ? ORDER BY name",
            (SOURCE_ID,),
        ).fetchall()
    discovered = [
        {
            "id": row["id"],
            "name": row["name"],
            "owner": row["owner"],
            "url": row["source_url"],
            "source_type": row["source_type"],
            "update_policy": row["update_policy"],
            "measure": row["measure"],
            "unit": row["unit"],
            "frequency": row["frequency"],
            "last_checked": row["last_checked"],
            "last_successful_fetch": row["last_successful_fetch"],
            "latest_publication_date": row["latest_publication_date"],
            "latest_period": row["latest_period"],
            "status": row["status"],
            "error_summary": row["error_summary"],
            "limitations": [
                "This ISA status guide describes application requirements; it is not a verified monthly processing-time dataset.",
                "No duration values or reporting period are imported from this page.",
            ],
        }
        for row in rows
    ]
    return [_freshness(), *discovered]


@router.get("/processing-times")
def processing_times() -> dict[str, Any]:
    return {
        "available": False,
        "observations": [],
        "message": (
            "No official processing-time series is configured. The e-Stat monthly "
            "workload table contains counts only and cannot support duration statistics."
        ),
        "source": next(
            (source for source in sources() if source["id"] == "isa-processing-time-discovery"),
            None,
        ),
    }


@router.get("/distributions")
def distributions() -> dict[str, Any]:
    return {
        "available": False,
        "observations": [],
        "message": (
            "No representative case-level duration data is available. Aggregate "
            "monthly counts do not support medians, percentiles, or waiting-time distributions."
        ),
    }


@router.get("/refresh/status")
def refresh_status() -> dict[str, Any]:
    with connect() as connection:
        runs = connection.execute(
            """
            SELECT id, source_id, started_at, finished_at, status, rows_imported,
                   validation_summary, error_summary
            FROM refresh_run ORDER BY id DESC LIMIT 10
            """
        ).fetchall()
    return {
        "running": any(row["status"] == "running" for row in runs),
        "runs": [dict(row) for row in runs],
        "source": _freshness(),
    }


@router.post("/refresh", status_code=202)
def request_refresh(request: Request) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    last = request.app.state.last_manual_refresh
    if last and (now - last).total_seconds() < 60:
        raise HTTPException(
            status_code=429,
            detail="Refresh was requested recently. Please wait at least 60 seconds.",
        )
    if not refresh_in_background():
        raise HTTPException(status_code=409, detail="A refresh is already running.")
    request.app.state.last_manual_refresh = now
    request.app.state.refresh_queued = True
    return {"status": "queued", "message": "The official e-Stat source check has started."}
