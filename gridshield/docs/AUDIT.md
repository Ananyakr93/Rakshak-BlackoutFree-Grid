# Phase 1 — BlackoutFree / GridShield Audit

## Scope and evidence

The user confirmed that `gridshield/` is the base project. Its application, README, and existing documentation identify the product as **GridShield**; the workspace has no `BlackoutFree/` directory. This audit therefore treats `gridshield/` as BlackoutFree's selected base and records the public-name discrepancy for the next phase.

Rakshak was inspected directly from `Rakshak-main.zip` without extracting or changing it. Rakshak findings below are static code/documentation review only; Rakshak was not run. BlackoutFree was built and run locally, and the flows and checks below distinguish observed results from static findings.

## Executive summary

- The selected base is a substantial, modular simulation product, not a blank starter. Its priority-based control, restoration, 3D city, diagnostics, history, comparative experiments, and optional HIL are already more complete than the corresponding Rakshak implementations.
- Existing backend and frontend tests pass (105 pytest tests and 20 Vitest tests). The frontend production build succeeds. A real P2 scenario completed through both the API and dashboard; it produced telemetry, decision events, and metrics.
- The most important correctness issue found is that restoration delays depend on a randomly generated run UUID. Repeating the same recovered scenario with the same seed changed the restoration sequence, so results and paired policy comparisons are not fully reproducible.
- The clearest integration/configuration issues are divergent duplicate scenario directories, an unused Compose data mount, localhost-only CORS, and a Vite proxy configuration bypassed by the client's absolute API URL.
- No net-new Rakshak feature is recommended for adoption. BlackoutFree already implements the shared core features; the distinctive Rakshak-only ideas are either uncalibrated or decorative.
- Phase 1 made no application-code changes. The only intended workspace additions from this phase are this audit and [PLAN.md](./PLAN.md).

## BlackoutFree base map (`gridshield/`)

### Folder structure

```text
gridshield/
  backend/
    app/
      api/          scenarios, runs, metrics, WebSocket
      control/      edge agent, shedding, restoration policies
      core/         settings, logging, in-memory run manager
      db/           SQLModel tables, async session, repository
      evaluation/   metrics, experiments, participation frontier
      hil/          serial adapter and protocol
      messaging/    in-process fault-injection bus
      nilm/         aggregate-load event detector and evaluation
      schemas/      scenario, telemetry, event Pydantic models
      twin/         appliance/building/grid models, clock, disturbances,
                    feeder estimates, synthetic Indian load profiles
    data/scenarios/ four YAML scenarios loaded by the backend
    tests/          unit, integration, and scenario test areas
    Dockerfile, pyproject.toml
  data/scenarios/   a second, divergent copy of the four YAML scenarios
  docs/             architecture, assumptions, data, experiment, HIL, NILM
  experiments/
    baseline/       E1–E4 runner and saved results
    sensitivity_analysis/
  firmware/esp32/   optional PlatformIO HIL firmware
  frontend/
    src/api/        typed fetch client
    src/components/ city twin, charts, diagnostics
    src/scene/      Three.js city, buildings, layout, environment, feeders
    App.tsx, index.css, scenario tuning, types
    package.json, package-lock.json, Vite/TypeScript/Tailwind config
  docker-compose.yml, .env.example, README.md
```

The workspace also contains historical/research material at its root (`framework.md`, `Project_Rakshak_Knowledge_Transfer.md`, and `GridShield_Phase1_Implementation_Prompts.md`) and the Rakshak ZIP. These are outside the selected app directory; no runtime import from the Rakshak ZIP was found. Generated/local items in the base include a SQLite database, egg-info, test/lint caches, frontend build output, and TypeScript validation state.

### Stack, dependencies, and entry points

| Area | Observed implementation |
|---|---|
| Backend | Python >=3.10; Docker image Python 3.12; FastAPI 0.115.0, Uvicorn 0.30.6, Pydantic 2.9.2 / pydantic-settings 2.5.2, SQLModel 0.0.21, NumPy 1.26.4, SciPy 1.13.1, pandas 2.2.3, aiosqlite 0.20.0, asyncpg 0.29.0, PyYAML 6.0.2. |
| Backend checks | pytest 8.3.3, pytest-asyncio 0.24.0, httpx 0.27.2, Ruff 0.6.9. Dependencies are pinned in `backend/pyproject.toml`; PySerial is an optional pinned HIL extra. |
| Frontend | React 18.3.1, TypeScript 5.6.3, Vite 5.4.8, Three.js 0.160.1, Chart.js 4.4.4 / react-chartjs-2 5.2.0, Vitest 2.1.4; direct dependencies are exact-versioned in `frontend/package.json` and locked. |
| Frontend checks | `npm run build`, `npm test`, `npm run dev`, `npm run preview`, `npm run lint`. The lint script calls ESLint, but ESLint is not declared or installed. |
| Backend entry | `backend/app/main.py`; Uvicorn imports `app.main:app`. Lifespan creates DB tables and disposes the engine. |
| Frontend entry | `frontend/src/main.tsx` mounts `App.tsx`; Vite serves port 3000. |
| Combined entry | `docker compose up --build` starts PostgreSQL, backend, and Vite frontend. Direct README instructions require separate backend and frontend terminals. There is no root package script or local process orchestrator. |

`npm ls --depth=0` showed the declared frontend dependencies installed; inspected frontend runtime imports use the declared charting, Three.js, and font packages. The backend manifest's main dependencies serve the API, models, simulation, or optional database/HIL paths. No unused direct frontend runtime dependency was identified by import inspection.

### API surface and frontend wiring

The API prefix is `/api/v1` (except `/health`). The browser client calls the corresponding routes in `frontend/src/api/client.ts`.

| Surface | Routes |
|---|---|
| Health | `GET /health` |
| Scenarios | `POST /scenarios`, `GET /scenarios`, `GET /scenarios/templates`, `GET /scenarios/{scenario_id}` |
| Runs | `POST /runs`, `GET /runs`, `GET /runs/{run_id}`, `POST /runs/{run_id}/pause`, `/resume`, `/speed`, `/stop` |
| Live run detail | `GET /runs/{run_id}/integrations`, `/agents`, `/restoration`, `/feeder`, `/buildings` |
| Run telemetry/results | `GET /runs/{run_id}/metrics`, `/events`, `/telemetry`, `/nilm`, `/nilm/signal`, `/nilm/evaluation` |
| Experiments | `POST /experiments/compare`, `GET /experiments/baseline` |
| Live stream | `WS /runs/{run_id}/stream` |

Route handlers live in `backend/app/api/{scenarios,runs,metrics,websocket}.py`. The frontend starts a run by creating a scenario and posting a run request; it consumes telemetry over WebSocket and polls the run snapshot and diagnostics. It also exposes pause/resume, speed, stop, four-policy comparison, and history/results views. The API client paths match the registered routes in the inspected implementation, and the default scenario/run/results path was exercised end to end.

### Data model and simulation

- Pydantic request/value models: `ScenarioConfig`, `GridParams`, `DisturbanceConfig`, `FaultConfig`, `BuildingConfig`, and `ApplianceConfig`; telemetry and control-event schemas live in `backend/app/schemas/`.
- SQLModel tables: `Scenario`, `SimulationRun`, `Building`, `ApplianceRecord`, `TelemetryRecord`, `ControlEventRecord`, and `RunMetric`. SQLite is the local default; Compose configures PostgreSQL.
- The core is a reduced-order, single-area frequency model with an RK4 clock, generation/demand/solar disturbances, configurable protection thresholds and hold times, synthetic building/appliance load, appliance startup/inrush/lockout behavior, and seeded packet loss.
- Policies include unmanaged P0, feeder-stage P1, priority-aware staged P2, synchronized P2 restoration, and P3 without restoration. Critical appliances are protected by P2; actions emit event reasons. Restoration has stability/frequency/projection gates and deterministic hash delays, but the hash currently includes a non-deterministic run ID (finding A1).
- Metrics include frequency nadir, RoCoF, recovery time, critical energy not served, medical interruption, feeder trips, rebound, curtailed energy, over-frequency duration, and Jain fairness. Multi-seed paired experiments are implemented.
- NILM estimates are generated from simulated aggregate-load transitions and compared with state from that same synthetic twin. They are not independent meter validation. HIL is optional and serial-based; the application reports heartbeat state and fallback.
- The city is a procedural 3D streetscape, not a geographic or solved electrical network model. It renders up to 12 representative buildings and labels feeder current as an estimate.

### Frontend, state, and design

The UI is a bespoke dark control-room dashboard: persistent status/navigation, a largest-area Three.js city scene, floating operator panels, a frequency readout, event log, and Operations / Resilience systems / Results & history views. React hooks own state; there is no external state-management library. The control panel includes scenario templates/tuning, edge mode, policy, seed, playback controls, comparison controls, and optional HIL settings.

DM Sans and JetBrains Mono are self-hosted. The CSS has semantic colors, keyboard focus treatment, mobile breakpoints, a keyboard-selectable building list, ARIA labels/statuses, and a `prefers-reduced-motion` rule. The renderer caps pixel ratio at 1.5 and has a disposal path. These are good foundations to retain rather than replace with a generic dashboard.

Current UX observations: the top-level product identity is GridShield; many scenario sliders are visible together, while a few advanced sections are collapsed. `index.css` defines `:root` tokens twice, with the second palette overriding part of the first. The production JS chunk is ~882 kB minified and triggers Vite's >500 kB warning.

### Configuration and run behavior

- Local backend defaults to SQLite at `./gridshield.db`; environment settings include `DATABASE_URL`, `EXPERIMENT_RESULTS_PATH`, API prefix, simulation/agent/WebSocket intervals, log level, and `CORS_ORIGINS`.
- Backend CORS defaults to only `http://localhost:3000`. Access via `http://127.0.0.1:3000` was blocked; using the documented `localhost` origin worked. LAN or alternate frontend origins need configuration.
- Frontend API base defaults to the current hostname on port 8000, or `VITE_API_BASE_URL`. Vite also declares `/api` and `/ws` proxies, but the client always constructs an absolute backend URL, so those proxy entries are bypassed.
- Root and backend `.env.example` files exist. Compose's backend `env_file` is explicitly `./.env.example`, not the copied `.env` described in the README; Compose interpolation reads `.env`, but backend non-overridden settings such as custom CORS/log level do not come from it.
- Compose mounts root `./data` at `/data`, but `scenarios.py` reads `backend/data/scenarios` packaged in the backend image. The two directories contain same-named YAML files with different contents and sizes; edits to the root copy do not change the templates served by the API.
- Important assumptions remain hard-coded or defaulted: nominal 400 V / 0.95 PF feeder estimates, 49.90 Hz restoration projection floor, default protection/timing parameters, and simulation intervals. These are model assumptions, not live grid measurements; several are documented as such.
- The backend uses generic `dict` / `list[dict]` response models for most routes rather than named response schemas. Requests use Pydantic validation, but frontend response shapes are compile-time TypeScript only.

## Rakshak reference map (read-only)

```text
Rakshak-main.zip
  backend/
    main.py                 singleton FastAPI controller and WebSocket loop
    config.py               Pydantic settings and appliance catalog
    grid_engine.py          grid swing/governor model
    fleet_simulator.py      12 micro buildings and 500-home macro fleet
    nilm_engine.py          NILM demo
    hil_bridge.py           serial bridge
    requirements.txt        broad, unpinned version ranges
  frontend/
    index.html              monolithic Three.js/HTML/CSS/JS control room
    dashboard.html          separate analytical benchmark page
    three.min.js            vendored Three.js r128
  benchmarks/benchmark_modes.py
  firmware/esp32_rakshak_edge/{esp32_rakshak_edge.ino,config.h,nilm_edge.h}
  docs/{architecture.md,presentation_guide.md,research_insights.md}
  run_sim.py                starts Uvicorn and opens the browser
```

Rakshak uses Python/FastAPI/Pydantic/NumPy, a process-global controller, in-memory simulation state, static HTML and a WebSocket. Its routes are `GET /api/status`, `POST /api/scenario`, `POST /api/reset`, and `WS /ws/telemetry`; it mounts the frontend at `/`. It has no database, frontend package manifest, or test suite in the archive. `run_sim.py` is the launcher. `main.py` permits all CORS origins with credentials, streams at a hardcoded cadence, and swallows all WebSocket-loop exceptions.

The Rakshak dashboard also performs its own simulation in browser JavaScript. It sends `SET_PARAMS` and `SET_MODE` to the backend but contains no WebSocket message handler; its play/pause button only toggles the local browser loop, while the backend loop continues. The page labels the connection “LIVE CO-SIM” on socket open without consuming backend telemetry and contains a static “HIL: ESP32 READY” badge. This is not a reliable implementation to port.

## Feature matrix

Quality scale: 1 = absent/placeholder, 2 = prototype or materially incomplete, 3 = usable with notable limits, 4 = strong with bounded gaps, 5 = strong and supported by code plus observed behavior. Scores are qualitative audit judgments, not benchmark outputs. Rakshak scores are static-review only.

| Feature | In BlackoutFree? | In Rakshak? | Quality BlackoutFree / Rakshak | Verdict |
|---|---:|---:|---:|---|
| Reduced-order frequency/grid response and governor | Yes | Yes | 4 / 3 | keep |
| Generation loss, demand and solar disturbance scenarios | Yes | Partial | 5 / 2 | keep |
| Feeder UFLS baseline and multiple control policies | Yes | Yes | 5 / 3 | keep |
| Priority-aware, staged appliance shedding | Yes | Yes | 5 / 3 | keep |
| Critical/medical load protection and interruption metrics | Yes | Yes | 5 / 3 | keep |
| Per-building edge control and degraded communications | Yes | Partial | 4 / 2 | keep |
| Compressor lockout and inrush/startup transients | Yes | Yes | 5 / 3 | keep |
| Staggered/synchronized restoration with stability gates | Yes | Yes | 4 / 2 | keep |
| Deterministic restoration delay based on physical MAC identity | No | Yes | 1 / 2 | drop |
| 12 representative assets and 500-home-equivalent modeling | Yes | Yes | 4 / 4 | keep |
| Interactive Three.js city and asset inspection | Yes | Yes | 4 / 3 | keep |
| Explainable event/decision log | Yes | Partial | 4 / 2 | keep |
| WebSocket telemetry consumed by the dashboard | Yes | Partial | 4 / 2 | keep |
| Pause/resume, stop, speed, and scenario controls | Yes | Partial | 4 / 2 | keep |
| Run history and persisted telemetry/metrics | Yes | No | 5 / 1 | keep |
| Multi-mode, multi-seed experiments and comparisons | Yes | Partial | 5 / 2 | keep |
| Equity/fairness and energy-service metrics | Yes | Partial | 4 / 1 | keep |
| NILM estimate and evaluation | Yes | Yes | 4 / 2 | keep |
| Optional serial HIL adapter and ESP32 firmware | Yes | Yes | 4 / 2 | keep |
| Fault injection beyond packet loss (delay/duplication/reordering) in live runs | No (schema/bus exist but are unwired) | No | 2 / 1 | drop/defer |
| Sensor-offset modeling | No | Yes | 1 / 2 | drop |
| Medical ECG overlay / dedicated analytics page | No | Yes | 1 / 2 | drop |
| Typed modular REST API with persistence | Yes | No | 4 / 1 | keep |
| Responsive, keyboard-selectable, reduced-motion UI | Yes | Partial | 4 / 2 | keep |
| Single-command startup | Partial (Compose only) | Partial (launcher) | 3 / 2 | keep and improve |

## Findings and run evidence

### Correctness, integration, and maintainability findings

| ID | Finding | Evidence / impact |
|---|---|---|
| A1 | **Same-seed restoration is not reproducible.** `SimulationClock` sets `incident_id = str(run_id)`; restoration delay hashes that identifier along with building/appliance and seed. | Reproduced through the API: two completed P2 runs with the same scenario and seed (42), with enough recovery time, each produced 76 events but different restoration sequences. This also undermines paired policy comparisons. |
| A2 | **Completed run state is retained without bounds.** `RunManager` keeps every run, telemetry sample, and event in process memory; no eviction/cleanup is present. `RunEntry.task` is never assigned or read. | Long-lived process memory grows with total runs and run duration despite database persistence. WebSocket subscribers are bounded individually, but per-run history is not. |
| A3 | **Several persisted model tables are unused.** `Building` and `ApplianceRecord` SQLModel tables are created but have no repository insert/read path. `app/nilm/evaluation.py` is only used by its tests; the live API performs event-transition matching instead. | Potential dead schema/helper complexity. Removing persisted table definitions or the distinct classification helper was deferred to avoid an unrequested schema/data migration. |
| A4 | **Two divergent scenario copies and an unused mount.** Root `data/scenarios` and `backend/data/scenarios` contain all four same-named but different YAML files. Compose mounts the root copy at `/data`; the scenario endpoint reads packaged `backend/data/scenarios`. | Operators can edit the mounted directory and see no change in served templates. Choose one canonical source and remove/retarget the other. |
| A5 | **CORS only admits the `localhost` origin.** | The dashboard at `127.0.0.1:3000` failed browser CORS calls; `localhost:3000` succeeded. Document/configure allowed development origins and keep an explicit production allow-list. |
| A6 | **Vite proxy settings are bypassed.** | The client builds an absolute API URL using `VITE_API_BASE_URL` or `window.location.hostname:8000`; Vite's relative `/api` and `/ws` proxies therefore do not handle these requests. Either remove the unused proxy or use relative client paths consistently. |
| A7 | **Response contracts are weakly typed.** | Most FastAPI routes declare `dict` or `list[dict]`; TypeScript casts server JSON without runtime validation. Invalid-input FastAPI validation responses also have a different `detail` shape from string HTTP errors. |
| A8 | **Frontend lint command is broken; backend lint is not clean.** | `npm run lint` exits 1 because ESLint is not installed or declared. `ruff check app` reports unsorted imports and unused `deepcopy` in `app/evaluation/participation_frontier.py`. |
| A9 | **Build warnings and duplicate design tokens.** | Production build succeeds but warns that the Vite CJS API is deprecated, `postcss.config.js` is reparsed as ESM because package module type is unspecified, and the ~882 kB JS chunk exceeds 500 kB. `index.css` contains two `:root` token blocks; the later one overrides values from the first. |
| A10 | **Compose environment customization is inconsistent.** | README instructs copying `.env.example` to `.env`, but backend `env_file` points at `.env.example`; Compose interpolation sees `.env`, while non-overridden backend variables do not. Compose syntax itself validates; it emits a warning that the top-level `version` attribute is obsolete. |
| A11 | **Architecture documentation contradicts the live NILM implementation.** | `docs/architecture.md` says NILM is not enabled in the live simulation/dashboard, but `SimulationClock` runs the detector and API/UI expose samples and evaluation. Clarify that it is live synthetic estimation, not independent meter data. |
| A12 | **Some declared scope is not connected to the active simulation.** | `InProcessBus` and its delay/duplicate/reorder fault modes are only exercised by unit tests, not imported into the run loop. Live scenario validation rejects those modes; packet loss is the implemented active communication fault. Decide whether to wire them or remove/defer misleading configuration. |
| A13 | **A few names still expose Rakshak internals.** | The unused bus has `rakshak/v1/...` topics and `participation_frontier.py` calls itself “GridShield / Project Rakshak.” Root reference documents are outside the app; no Rakshak runtime import was found. |
| A14 | **Interrupted runs can be left stale.** | Run status changes to `running` in the database, but active clocks and live diagnostics are process-local. There is no startup reconciliation for runs left running after process termination; some event/telemetry batches are flushed only on normal completion. |

### Checks actually run

| Check / flow | Result | Evidence |
|---|---|---|
| Backend unit/integration suite | PASS | `python -m pytest -q`: 105 passed in 179.50 s. |
| Frontend tests | PASS | Runtime plan: Vitest 20/20 passed. |
| Frontend production build | PASS with warnings | `npm run build` and standalone runtime-plan build passed; Vite reported CJS/module-type and large-chunk warnings. |
| Frontend development server | PASS | Standalone runtime plan's HTTP probe returned 200. |
| Backend health/template routes | PASS | Uvicorn on local port 8765 returned healthy status and four scenario templates. Port 8000 was already occupied by the host's Splunk service, so the audit used a temporary SQLite DB and alternate port. |
| API scenario → P2 run → results | PASS | Created a scenario, completed a 300 s run, read 12 building snapshots, 48 events, and 23 metrics. |
| Browser dashboard → P2 run → decision log | PASS | At the allowed `localhost:3000` origin, API connected, 12 city assets rendered, Start simulation completed, telemetry reached 50.00 Hz at t=300 s, and the UI displayed 8 event-log entries with no in-app alert. |
| Alternate-host CORS behavior | FAIL as configured | `127.0.0.1:3000` was rejected by the backend's `localhost:3000` allow-list; expected behavior only works on the documented hostname or with an updated allow-list. |
| Same-seed restoration repeatability | FAIL | Two completed identical-seed P2 runs had different restoration order/timing when the scenario allowed recovery. See A1. |
| Frontend lint | FAIL | ESLint executable missing; see A8. |
| Backend lint | FAIL | Two Ruff findings; see A8. |
| Compose parse | PASS with warning | `docker compose config --quiet` passed; `version` is obsolete. Full Compose services were not started. |
| Python environment consistency | Environment warning | `pip check` reports conflicts between globally installed unrelated packages (including google-genai/httpx and TensorFlow/protobuf). This is not a declared GridShield dependency conflict; the project test suite passed in this environment. |

### Not verified in Phase 1

Docker services/PostgreSQL were not launched; no physical HIL device, independent meter, real grid, LAN deployment, WCAG contrast measurement, mobile-browser session, or production-served frontend was tested. The project makes explicit model limitations; simulation output must not be presented as live utility telemetry. These checks belong in the approved implementation/verification phases.

## Phase 2 resolution update

The approved backend/configuration fixes are implemented in `gridshield/`; Rakshak remains untouched.

| Finding | Phase 2 status |
|---|---|
| A1 | Fixed: restoration incident identity is derived from stable scenario contents, independent of scenario/run UUIDs; the run seed override is applied to both the stored snapshot and simulation. Regression tests cover the stable identity and saved/executed seed. |
| A2 | Fixed: terminal in-memory runs are limited to the newest 20 eligible entries; active runs are retained and the unused task field was removed. |
| A3 | Deferred: unused database table definitions and the test-only NILM evaluation helper were not removed; removing existing schema definitions needs a separate data-compatibility decision. The confirmed unused single-event repository writer was removed after adding batched persistence. |
| A4 / A10 | Fixed: the backend scenario directory remains canonical, the unused root-data mount and obsolete Compose `version` were removed, and Compose uses the committed `.env.example` defaults. `docker compose config --quiet` passes without requiring a local `.env`. |
| A5 / A6 | Fixed: `localhost` and `127.0.0.1` are both in the default CORS allow-list; unused Vite proxy entries were removed because the client uses an absolute API URL. |
| A7 | Fixed at the API boundary: scenario, run, telemetry, event, metrics, experiment, diagnostic, and health routes declare Pydantic response schemas; requests reject unknown fields and validate ranges/policies. HTTP, validation, and unexpected errors share a structured envelope consumed by the frontend client. TypeScript still trusts JSON at runtime. |
| A8 | Fixed for backend Ruff; the missing ESLint command was replaced with the existing TypeScript compiler check (`npm run check`). This is a type check, not a style linter. |
| A9 | Deferred to Phase 3: large initial JS chunk and Vite/PostCSS warnings remain; design-token consolidation and code splitting are not Phase 2 work. |
| A11 | Fixed: architecture documentation now correctly states that dashboard NILM is estimated from simulated aggregate load, not independent meter readings. |
| A12 / A13 | Clarified: delay/duplication/reordering remain unavailable in live simulation; the isolated test bus topics and module description no longer use Rakshak names. No Rakshak source is imported at runtime. This is an explicit limitation, not a newly added feature. |
| A14 | Fixed for graceful failure/restart: pending telemetry/events are flushed on simulation exceptions, failure status is persisted, and startup marks stale pending/running/paused records failed. Hard process loss still cannot preserve unflushed in-memory samples. |

Phase 2 verification: backend suite **110 passed**; `ruff check app tests` passed; `npm run check` passed; `docker compose config --quiet` passed. The TypeScript runtime plan passed build, 20 Vitest tests, and its dev-server probe. A real SQLite-backed API smoke run on port 8765 completed P2 with request seed 902, 34 reasoned events, 23 metrics, and 12 building snapshots; invalid UUID input returned the validation envelope and `127.0.0.1:3000` CORS passed. An intermediate runtime-plan retry hit Windows `EPERM` because its prior Vite process remained open; after stopping that exact process and restoring dependencies, the plan passed again. `npm ci` reported six dependency advisories (2 moderate, 2 high, 2 critical); they were not triaged or changed in this phase.

## Phase 5 resolution update

The public product name is now BlackoutFree in the README, dashboard, browser title, and API documentation; internal `gridshield` folder, package, and database identifiers remain unchanged. The final verification report records the local end-to-end flow and the Docker-daemon limitation.
