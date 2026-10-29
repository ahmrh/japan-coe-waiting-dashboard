# Backend

The backend is a Python FastAPI service with SQLite storage. It discovers and
imports the public e-Stat table for monthly COE applications received and
processed, then exposes validated monthly observations through the API.

## Run with Python

Requires Python 3.11+. From the repository root:

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m app.cli
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The CLI command manually refreshes e-Stat. The API initializes the SQLite
database and checks the source on startup. The database is stored at
`data/coe_dashboard.sqlite3` in the repository root by default. Configure a
different local path or refresh interval through the root `.env` file; see
[`../.env.example`](../.env.example).

Open <http://localhost:8000/docs> for interactive API documentation. The
dashboard and manual source refresh are also available through
`docker compose up` and `docker compose exec backend python -m app.cli`; see
the [root guide](../README.md).

## API routes

- `GET /api/overview` — latest validated figures, history, source freshness,
  and evidence-based summary.
- `GET /api/application-volumes` — count observations by reporting period and
  hierarchy mode.
- `GET /api/sources` — source definitions and health/freshness information.
- `GET /api/processing-times` and `GET /api/distributions` — explicit
  unavailable responses unless compatible duration data is configured.
- `GET /api/refresh/status` — current and recent refresh runs.
- `POST /api/refresh` — rate-limited manual refresh request.
- `GET /api/health` — API and database health check.

## Data and refresh

The e-Stat source is discovered from table `0004049310`. The importer checks
the Japanese field names, unit, period labels, row counts, duplicates, bureau
labels, and receipt/completion identities before persisting a snapshot.
Hierarchical bureau totals and subordinate office rows remain distinct.
The month-end pending balance is calculated only when both published totals
reconcile and the result is non-negative.

Refreshes run at startup, when a dashboard request is due, and daily. Only one
refresh can run at a time; successful unchanged source responses update the
check timestamp without rebuilding observations. Failures are recorded and
leave prior validated observations available.

## Tests

```sh
pytest
```

Tests use saved e-Stat-shaped fixtures and do not need a live government
connection.

## Local configuration

The example configuration is in [`../.env.example`](../.env.example):

- `DATABASE_URL` — SQLite database path (default:
  `sqlite:///./data/coe_dashboard.sqlite3`).
- `ESTAT_REFRESH_INTERVAL_HOURS` — minimum interval between source checks
  (default: 24).
- `ESTAT_REQUEST_TIMEOUT_SECONDS` — per-request timeout (default: 20).

This local release is intended for one backend process with SQLite. Use a
shared database and a distributed scheduler/lock before deploying multiple
backend instances.
