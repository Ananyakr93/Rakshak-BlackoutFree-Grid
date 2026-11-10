# Phase 4 — Verification

## Result

The local application flow, production frontend build, backend suite, and browser smoke test passed. Docker Compose syntax is valid, but Compose startup and the README-only fresh-clone check are blocked because the Docker Desktop Linux engine is not running. Those checks are not reported as passes.

## UI-to-backend flows

The browser test starts the backend on `127.0.0.1:8001`, builds and serves the production frontend on `127.0.0.1:3001`, and uses file-backed SQLite to exercise the asynchronous simulation and concurrent reads.

| Flow | UI action → API/handler → rendered result | Result |
|---|---|---|
| Startup | Load dashboard → `GET /health` (`health`) and `GET /api/v1/scenarios/templates` (`list_scenario_templates`) → API connected indicator and populated scenario selector | PASS |
| Fault scenario and run | Select Severe Generation Loss → `POST /api/v1/scenarios` (`create_scenario`, 201), then `POST /api/v1/runs` (`start_run`, 202) → active run shown | PASS |
| Live telemetry and decisions | Active run → `WS /api/v1/runs/{run_id}/stream` (`stream_run`) and `GET /api/v1/runs/{run_id}/events` (`get_events`, 200) → frequency value updates and event timeline displays a non-empty decision reason | PASS |
| Pause and resume | Click Pause/Resume → respective `POST /api/v1/runs/{run_id}/pause` (`pause_run`) and `/resume` (`resume_run`), both 200 → run status chip updates | PASS |
| Playback speed | Select 120× → `POST /api/v1/runs/{run_id}/speed` (`set_run_speed`, 200; response reports 120) | PASS |
| Stop | Confirm Stop → `POST /api/v1/runs/{run_id}/stop` (`stop_run`, 200) → run reaches completed state | PASS |

The browser flow observed the WebSocket connect and close. It reported no page exceptions, console errors, or failed API network requests. Cross-origin browser requests from the frontend to the test API succeeded. Code inspection confirms the clock, health, and run-polling intervals are cleared on effect cleanup; polling also stops when a run becomes terminal, and the WebSocket retry timeout is cancelled during cleanup.

## Automated checks

| Check | Evidence | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` — 110 passed | PASS |
| Backend lint | `ruff check .` — all checks passed | PASS |
| Frontend production build | `npm run build` — TypeScript and Vite build succeeded; production preview served by Playwright | PASS |
| Frontend unit tests | Vitest — 20 passed, 0 failed | PASS |
| Browser end-to-end | `npm run test:e2e` — one production-preview flow passed, including BlackoutFree identity, scenario creation, reasoned events, telemetry, run controls, and run stop | PASS |
| Compose configuration | `docker compose config --quiet` | PASS |
| Compose service startup | `docker info` could not connect to `npipe:////./pipe/dockerDesktopLinuxEngine` | BLOCKED |
| README-only fresh-clone run | Requires Compose services; Docker engine unavailable | BLOCKED |

The first E2E attempt used in-memory SQLite and exposed a cursor/commit collision during concurrent simulation writes and dashboard polling. The test harness now uses an isolated file-backed SQLite database, matching the supported local database mode; the complete browser flow then passed.

## Remaining verification limits and warnings

- The browser smoke test does not exercise the comparison, saved-results/history, or advanced diagnostics screens. Existing backend tests cover API behavior, but these screens are not claimed as browser-verified here.
- Backend-unavailable presentation was visually checked in Phase 3; this Phase 4 browser run did not automate a backend outage.
- The production build succeeds but Vite reports its CJS Node API deprecation, a module-type warning for `postcss.config.js`, and a bundle chunk larger than 500 kB. No build error resulted; code splitting remains a separate optimization.
- Dependency installation reported six npm advisories (2 moderate, 2 high, 2 critical); they were not triaged as part of these verification changes.
- No physical HIL controller, independent meter data, or live grid was available; these checks establish simulation behavior only.
