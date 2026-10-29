# Japan COE Workload Dashboard

See the monthly flow of Certificate of Eligibility (COE) applications through
Japan's immigration offices. This dashboard turns the Immigration Services
Agency's monthly e-Stat workload counts into a clear view of cases carried
over, new receipts, completed outcomes, and the calculated month-end balance.

**Understand the workload. Follow the outcomes. See the source behind every
figure.**

## What you can explore

- **A national and bureau-by-bureau view** of workload and monthly outcomes,
  using the official jurisdiction classifications.
- **Monthly workload and outcomes together:** carried-over cases and new
  receipts compared with completions split into issued, not issued, and other
  closures or transfers.
- **Historical context** with monthly trends and a bureau-by-month heatmap.
- **Bureau totals or office details**, shown separately so parent jurisdiction
  counts are not added to their own offices.
- **Definitions and source freshness** alongside the figures, including the
  publication date, reporting period, last successful check, and official
  source link.
- **An evidence-first pending balance:** calculated from published totals only
  when the source's receipt and completion categories reconcile. It is labelled
  as app-calculated, not as an official e-Stat figure.

The primary source is the [official monthly e-Stat COE table](https://www.e-stat.go.jp/dbview?sid=0004049310).
It reports workload counts in people (`人`), not individual case durations.
This dashboard does not estimate how long a particular application will take,
predict decisions, or provide legal advice. Contact the relevant immigration
office or employer for case-specific questions.

## Start the application

You need Docker with the Docker Compose plugin. From the repository root:

```sh
docker compose up
```

Open the dashboard at <http://localhost:5173>. The API documentation is at
<http://localhost:8000/docs>. Compose starts the frontend and backend, creates
the SQLite database, and checks e-Stat automatically. No separate database,
Java runtime, or e-Stat API key is required.

Stop with `Ctrl+C` or `docker compose down`. Stored statistics remain in the
Docker volume. Run `docker compose down --volumes` only if you also want to
remove that stored data.

## Refresh and verify data

The service checks the official source at startup, when a dashboard session
opens and a check is due, and once daily. To request a manual refresh:

```sh
docker compose exec backend python -m app.cli
```

A failed download or changed source layout does not erase the last validated
data. Check the source status in the dashboard or at
<http://localhost:8000/api/refresh/status>.

Run the tests and frontend checks in Compose:

```sh
docker compose exec backend pytest
docker compose exec frontend npm run typecheck
docker compose exec frontend npm run build
```

## Project guides

- [Frontend guide](frontend/README.md) — run the Vue app with npm, frontend
  scripts, and API proxy setup.
- [Backend guide](backend/README.md) — run FastAPI with Python, refresh data,
  inspect API routes, and run tests.

## Data limits

The bureau in the source is the statistical jurisdiction handling the case; it
does not identify the applicant's home prefecture. Transfers may affect receipt
and completion categories, and `既済_その他` is broader than withdrawals.
Monthly aggregate workload counts cannot support means, medians, percentiles,
or personal waiting-time predictions. Where the source does not support a
measure, the dashboard leaves it unavailable rather than inferring a value.
