# Frontend

The frontend is a Vue 3, TypeScript, and Vite application. It presents the
monthly COE workload and outcomes dashboard and proxies API requests to the
FastAPI service.

## Run with npm

Requires Node.js 20+ and npm. From the repository root:

```sh
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite development server proxies `/api`
requests to `http://127.0.0.1:8000` by default, so start the backend as
described in the [backend guide](../backend/README.md). To point at a different
API during development, set `VITE_API_PROXY` before starting Vite:

```sh
VITE_API_PROXY=http://localhost:8000 npm run dev
```

To run the complete local stack instead, use `docker compose up` from the
repository root; see the [root guide](../README.md).

## Commands

```sh
npm run dev        # Start Vite development server
npm run typecheck  # Check Vue and TypeScript types
npm run build      # Type-check and create production assets in dist/
npm run preview    # Preview the production build
```

## Dashboard behavior

The overview uses the backend's validated official e-Stat observations. The
charts have equivalent data tables, bureau aggregates and office details are
separate modes, and pending counts are labelled as calculated. The processing
time view does not infer a duration from monthly volume counts.

See the [backend guide](../backend/README.md) for API details and data source
behavior.
