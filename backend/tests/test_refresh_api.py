from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.database import SOURCE_ID, connect, initialize_database
from app.estat import Dataset, EXPECTED_FIELDS, _parse_result_table
from app.main import app
from app.refresh import refresh_estat


FIXTURE = Path(__file__).parent / "fixtures" / "estat_2026_08_live_fragment.html"
METADATA = {
    "100000": ("総数", "national_total", None, 10),
    "101170": ("東京出入国在留管理局管内", "bureau_jurisdiction", None, 200),
    "101180": ("東京出入国在留管理局", "office", "101170", 210),
    "101210": ("横浜支局", "office", "101170", 240),
}


def setup_database(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    target = tmp_path / "dashboard.sqlite3"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target}")
    initialize_database()
    return target


def seed_observations() -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as connection:
        snapshot_id = connection.execute(
            """
            INSERT INTO source_snapshot
                (source_id, fetched_at, publication_date, latest_period,
                 content_hash, parser_version, validation_summary, raw_response)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (SOURCE_ID, now, "2026-10-26", "2026-08", "hash", "1.0.0", "{}", b"[]"),
        ).lastrowid
        connection.execute(
            """
            UPDATE data_source
            SET last_checked = ?, last_successful_fetch = ?,
                latest_publication_date = ?, latest_period = ?, status = 'current'
            WHERE id = ?
            """,
            (now, now, "2026-10-26", "2026-08", SOURCE_ID),
        )
        for period, code, name, hierarchy_type, parent, seq, old, new, issued in (
            ("2026-08", "100000", "総数", "national_total", None, 10, 131402, 42181, 77215),
            ("2026-08", "101170", "東京出入国在留管理局管内", "bureau_jurisdiction", None, 200, 74877, 19613, 38079),
            ("2026-08", "101180", "東京出入国在留管理局", "office", "101170", 210, 69712, 18121, 35697),
            ("2026-08", "101210", "横浜支局", "office", "101170", 240, 5165, 1492, 2382),
            ("2026-07", "100000", "総数", "national_total", None, 10, 120000, 40000, 70000),
            ("2026-07", "101170", "東京出入国在留管理局管内", "bureau_jurisdiction", None, 200, 70000, 18000, 35000),
        ):
            accepted = old + new
            completed = issued + 8192 + 1311 if code == "100000" else issued + 3624 + 733
            if period == "2026-07":
                completed = issued + 7000
            raw = {
                "受理_総数": accepted,
                "受理_旧受": old,
                "受理_新受": new,
                "既済_総数": completed,
                "既済_交付": issued,
                "既済_不交付": completed - issued,
                "既済_その他": 0,
            }
            connection.execute(
                """
                INSERT INTO coe_monthly_workload_observation (
                    period, bureau_code, bureau_name, hierarchy_type, parent_code,
                    sequence_number, accepted_total, old_receipts, new_receipts,
                    completed_total, issued, not_issued, completed_other,
                    pending_official, pending_calculated, unit, raw_values,
                    source_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, '人', ?, ?)
                """,
                (
                    period, code, name, hierarchy_type, parent, seq,
                    accepted, old, new, completed, issued, completed - issued, 0,
                    accepted - completed, __import__("json").dumps(raw, ensure_ascii=False),
                    snapshot_id,
                ),
            )


def source_fixture_dataset() -> Dataset:
    metadata = {
        code: {
            "name": values[0],
            "hierarchy_type": values[1],
            "parent_code": values[2],
            "seq_no": values[3],
        }
        for code, values in METADATA.items()
    }
    observations, warnings = _parse_result_table(
        FIXTURE.read_text(encoding="utf-8"),
        "2026-08",
        metadata,
        EXPECTED_FIELDS,
        "人",
    )
    assert not warnings
    raw = FIXTURE.read_bytes()
    return Dataset(
        observations=tuple(observations),
        publication_date="2026-10-26",
        latest_period="2026-08",
        content_hash="live-source-fixture",
        raw_response=raw,
        warnings=(),
        source_title="Official e-Stat COE table",
    )


def test_refresh_imports_fixture_as_atomic_source_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    monkeypatch.setattr("app.refresh.fetch_dataset", source_fixture_dataset)

    outcome = refresh_estat()

    assert outcome["status"] == "succeeded"
    assert outcome["rows_imported"] == 4
    with connect() as connection:
        versions = {
            row[0] for row in connection.execute("SELECT version FROM schema_migration")
        }
        assert versions == {1, 2}
        assert connection.execute(
            "SELECT count(*) FROM source_snapshot"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM coe_monthly_workload_observation"
        ).fetchone()[0] == 4
        snapshot = connection.execute(
            "SELECT content_hash, raw_response FROM source_snapshot"
        ).fetchone()
        assert snapshot["content_hash"] == "live-source-fixture"
        assert bytes(snapshot["raw_response"]) == FIXTURE.read_bytes()


def test_unchanged_source_updates_check_time_without_rebuilding_observations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    monkeypatch.setattr("app.refresh.fetch_dataset", source_fixture_dataset)

    first = refresh_estat()
    second = refresh_estat()

    assert first["status"] == "succeeded"
    assert second["status"] == "unchanged"
    assert second["rows_imported"] == 0
    with connect() as connection:
        assert connection.execute("SELECT count(*) FROM source_snapshot").fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM coe_monthly_workload_observation"
        ).fetchone()[0] == 4
        assert connection.execute(
            "SELECT status FROM refresh_run ORDER BY id DESC LIMIT 1"
        ).fetchone()[0] == "unchanged"


def test_source_period_regression_does_not_replace_good_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    seed_observations()
    fixture = source_fixture_dataset()
    older = Dataset(
        observations=fixture.observations,
        publication_date=fixture.publication_date,
        latest_period="2026-07",
        content_hash="older-publication",
        raw_response=fixture.raw_response,
        warnings=(),
        source_title=fixture.source_title,
    )
    monkeypatch.setattr("app.refresh.fetch_dataset", lambda: older)

    outcome = refresh_estat()

    assert outcome["status"] == "failed"
    assert "regressed" in outcome["error_summary"]
    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM coe_monthly_workload_observation"
        ).fetchone()[0] == 6
        assert connection.execute(
            "SELECT latest_period FROM data_source"
        ).fetchone()[0] == "2026-08"


def test_failed_fetch_keeps_last_validated_observations(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    seed_observations()

    def fail_fetch() -> Dataset:
        raise OSError("e-Stat temporarily unavailable")

    monkeypatch.setattr("app.refresh.fetch_dataset", fail_fetch)
    outcome = refresh_estat()

    assert outcome["status"] == "failed"
    with connect() as connection:
        assert connection.execute(
            "SELECT count(*) FROM coe_monthly_workload_observation"
        ).fetchone()[0] == 6
        source = connection.execute(
            "SELECT status, last_successful_fetch, error_summary FROM data_source"
        ).fetchone()
        assert source["status"] == "refresh_failed"
        assert source["last_successful_fetch"] is not None
        assert "e-Stat temporarily unavailable" in source["error_summary"]


def test_refresh_lock_prevents_duplicate_source_fetches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def slow_failure() -> Dataset:
        entered.set()
        release.wait(timeout=5)
        raise OSError("test stop")

    monkeypatch.setattr("app.refresh.fetch_dataset", slow_failure)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(refresh_estat)
        assert entered.wait(timeout=5)
        second = refresh_estat()
        release.set()
        assert first.result(timeout=5)["status"] == "failed"

    assert second["status"] == "already_running"


def test_expired_refresh_lease_does_not_block_recovery(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    started = (datetime.now(timezone.utc) - timedelta(minutes=16)).isoformat()
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO refresh_run (source_id, started_at, status)
            VALUES (?, ?, 'running')
            """,
            (SOURCE_ID, started),
        )
    monkeypatch.setattr("app.refresh.fetch_dataset", source_fixture_dataset)

    outcome = refresh_estat()

    assert outcome["status"] == "succeeded"
    with connect() as connection:
        assert connection.execute(
            "SELECT status FROM refresh_run ORDER BY id LIMIT 1"
        ).fetchone()[0] == "failed"


def test_api_serves_hierarchy_without_double_counting_and_explicit_gaps(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    seed_observations()
    monkeypatch.setattr("app.main.refresh_in_background", lambda: False)
    monkeypatch.setattr("app.api.refresh_in_background", lambda: False)

    with TestClient(app) as client:
        overview = client.get("/api/overview").json()
        offices = client.get(
            "/api/application-volumes?period=2026-08&hierarchy=offices"
        ).json()
        processing = client.get("/api/processing-times").json()
        distributions = client.get("/api/distributions").json()
        source_list = client.get("/api/sources").json()

    assert overview["latest_period"] == "2026-08"
    assert overview["source"]["source_type"] == "official_government_statistics"
    assert "unit: 人" in overview["summary"]
    assert len(overview["rows"]) == 2
    assert {row["hierarchy_type"] for row in overview["rows"]} == {
        "national_total",
        "bureau_jurisdiction",
    }
    assert len(overview["observations"]) == 6
    assert len(offices["observations"]) == 2
    assert processing["available"] is False
    assert processing["source"]["id"] == "isa-processing-time-discovery"
    assert distributions["available"] is False
    assert "cannot support duration" in processing["message"]
    assert overview["rows"][0]["pending_label"] == "Calculated by the app"
    assert {source["id"] for source in source_list} == {
        SOURCE_ID,
        "isa-processing-time-discovery",
    }


def test_freshness_changes_to_stale_when_source_check_is_overdue(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    seed_observations()
    old_check = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    with connect() as connection:
        connection.execute(
            "UPDATE data_source SET last_checked = ? WHERE id = ?",
            (old_check, SOURCE_ID),
        )
    monkeypatch.setattr("app.main.refresh_in_background", lambda: False)
    monkeypatch.setattr("app.api.refresh_in_background", lambda: False)

    with TestClient(app) as client:
        overview = client.get("/api/overview").json()

    assert overview["source"]["status"] == "stale"


def test_manual_refresh_endpoint_rejects_duplicate_and_rapid_requests(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    setup_database(monkeypatch, tmp_path)
    monkeypatch.setattr("app.main.refresh_in_background", lambda: False)
    monkeypatch.setattr("app.api.refresh_in_background", lambda: False)

    with TestClient(app) as client:
        assert client.post("/api/refresh").status_code == 409
        client.app.state.last_manual_refresh = datetime.now(timezone.utc)
        too_soon = client.post("/api/refresh")

    assert too_soon.status_code == 429
