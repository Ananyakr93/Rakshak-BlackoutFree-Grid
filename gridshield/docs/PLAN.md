# Phase 1 — Proposed Plan

## Direction

Keep the selected `gridshield/` codebase as the base. The audit found the core grid-resilience capabilities already exist and are generally stronger than their Rakshak counterparts. **No net-new feature is proposed for porting from Rakshak.** Fix the reproducibility and integration defects first; preserve the working policies, persisted results, explainable events, diagnostics, and existing control-room/3D UI.

The user-stated product name is BlackoutFree while the selected base currently labels itself GridShield. Proposed presentation direction: align the public title and README with **BlackoutFree**, retaining GridShield internal identifiers and database names where renaming would add risk. The existing distinctive SCADA-style scene, font choices, and operator-oriented dashboard should be refined, not replaced.

## Rakshak feature decisions

Each line gives the reason a Rakshak-only or weaker implementation is not being ported. Shared features in the matrix remain in BlackoutFree; their implementation is not replaced.

- **MAC-address restoration delay — do not adopt:** BlackoutFree already has deterministic, seed-aware staggering; fix its run-ID dependency instead of copying Rakshak's synthetic MAC identity.
- **Per-building sensor offsets — do not adopt:** Rakshak's offsets are deterministic synthetic noise with no calibrated sensor evidence, so they would add ungrounded variability.
- **Medical ECG overlay and static “HIL ready” badge — do not adopt:** these are decorative/status claims without independent patient or hardware telemetry and could mislead operators.
- **Rakshak's browser-local simulation and monolithic static dashboard — do not adopt:** the browser does not consume WebSocket messages and its pause control does not pause the backend; BlackoutFree already has a modular backend-connected React UI.
- **Separate Rakshak benchmark page — do not adopt:** BlackoutFree already has persisted history, policy comparison, and result views; another dashboard would duplicate workflows.
- **Rakshak's additional UI/firmware presentation elements — do not adopt:** BlackoutFree already has an optional HIL adapter, firmware, diagnostics, and model provenance; retain its heartbeat-gated status and documented estimate boundaries.
- **Delay/duplication/reordering fault modes — do not port from Rakshak:** Rakshak does not implement these; BlackoutFree's same-named bus/configuration is currently unwired. Either wire and validate BlackoutFree's own implementation or remove/defer those misleading knobs—do not claim support as-is.

## Phase 2 — Backend and simulation logic

1. Make restoration and paired comparisons reproducible by deriving incident/stagger identifiers from stable scenario inputs and seed, not random run UUIDs. Add a regression test that repeats the same recovered scenario and checks identical event decisions/timing.
2. Keep seeded communication loss deterministic; test each control policy, protected-load behavior, restoration gates, and decision reason on boundary conditions.
3. Add named response schemas and a consistent validation/error envelope to the existing API. Keep route behavior and frontend contracts aligned; do not introduce new endpoints without a workflow need.
4. Choose one canonical scenario directory and remove the unused Compose mount or point it at that directory. Make `.env` / `.env.example` behavior consistent and support documented local origins safely.
5. Bound/clean in-memory run buffers and WebSocket subscribers; reconcile stale database run states after restart. Persist events/telemetry predictably on failure/stop as well as successful completion.
6. Remove only confirmed dead structures (unused Building/ApplianceRecord persistence tables, unused task field, duplicated evaluation helper) after checking existing callers/tests. Clarify or remove the test-only/unwired message bus and its unsupported fault settings.
7. Fix the two Ruff findings, make the declared frontend lint command runnable or replace it with a project-standard check, and use lockfile-based installation in Docker (`npm ci`). Keep existing pinned runtime dependencies.
8. Retain the single supported launch path `docker compose up --build` and document local SQLite as an alternative. The Compose file already parses; verify its services and port behavior when approved.

## Phase 3 — Frontend and design

1. Preserve the current calm, dark utility-control-room style, the 3D city, and the readable DM Sans / JetBrains Mono pairing. Do not copy Rakshak's high-chrome/futuristic decoration or present synthetic estimates as live measurements.
2. Consolidate CSS variables into one token block; retain consistent normal/warning/critical/restoring states and check contrast for the actual foreground/background pairs.
3. Arrange controls by operator workflow: scenario and primary run action first; tuning, edge/fault options, and HIL progressively disclosed; selected building and reasoned decisions easy to inspect. Keep existing Operations, Systems, and Results functions.
4. Preserve loading, empty, offline, and API error states, the keyboard building selector, responsive panel navigation, and reduced-motion behavior. Add explicit destructive-action confirmation only where an action actually discards or stops a run.
5. Use lazy loading/code splitting for non-initial views if it reduces the observed >500 kB initial chunk without degrading startup or 3D performance.
6. Record final tokens, type scale, layout, and rationale in `docs/DESIGN.md`.

## Phase 4 — Verification

- Run backend unit/integration tests and frontend Vitest/build/lint after the fixes.
- Add API tests for scenario creation, run lifecycle, invalid requests, persisted metrics/events, offline database state, and deterministic restoration.
- Add a browser smoke test that loads the dashboard, selects a fault scenario, starts a run, and verifies telemetry, asset state, and reasoned decision-log updates through the actual API.
- Exercise pause/resume, speed, stop, comparison, and history flows; test both normal and backend-unavailable states.
- Verify WebSocket cleanup, polling cleanup, CORS on documented hosts, console/network errors, production build and served output, and no unhandled request errors.
- Perform a clean-clone setup using only the README and existing open-source dependencies. Do not claim physical HIL or real-grid behavior without hardware/measurement evidence.

## Phase 5 — Deliverables

Update the README with setup/run/test steps, architecture diagram, screenshot placeholders, and decision logic. Add `docs/DESIGN.md` and `docs/VERIFICATION.md` with evidence for every exercised flow. Keep this Phase 1 `AUDIT.md` and `PLAN.md`. Clearly state model assumptions, what was adopted (none net-new from Rakshak), what was deliberately rejected, and any remaining limits.

## Change boundaries

Phase 1 changes only the two requested audit/plan documents; no application code or Rakshak files were changed. The workspace root is not a Git repository, so phase commits are unavailable here; changes will need to be reviewed as separate file sets unless version control is initialized.

## Phase 2 execution update

Implemented stable restoration identity and effective-seed snapshots, bounded terminal-run retention, stale-run startup reconciliation, failure-path persistence, named Pydantic request/response contracts, consistent API error responses, frontend error-envelope parsing, CORS and Compose corrections, and the directly related architecture/setup updates. Removed only confirmed-unused code and renamed isolated bus topics; no Rakshak files or imports were added.

Verification completed: 110 backend tests passed; backend Ruff, frontend TypeScript check, and Compose configuration passed; a real API run returned 34 reasoned control events, 23 metrics, and 12 building snapshots with the requested seed; the standalone TypeScript runtime plan passed build, 20 tests, and its dev-server probe. A transient Windows `EPERM` during runtime-plan setup was resolved by stopping the prior Vite server and restoring locked dependencies. `npm ci` reported six dependency advisories (2 moderate, 2 high, 2 critical), which were not changed in this phase.

Remaining known limits: unused `Building`/`ApplianceRecord` table definitions and the separate NILM classification helper remain; a hard process crash can lose telemetry/events not yet flushed, although startup marks the run failed. Dependency advisories remain untriaged.

## Phase 3 execution update

Consolidated the duplicate CSS root blocks into one token set, applied a restrained slate/sage palette with distinct normal, warning, critical, and restoring colors, and documented the self-hosted DM Sans / JetBrains Mono type scale and measured contrast ratios in `docs/DESIGN.md`. Refined the frequency readout and notification spacing, increased key control/data text sizing, disclosed the long tuning form behind a native keyboard-operable details control, moved the primary run action directly after scenario selection, and added confirmation before stopping an active simulation. Existing dashboard views, 3D city, mobile panel tabs, empty/offline/error states, and reduced-motion behavior remain in place.

Verification completed: the frontend standalone runtime plan passed production build, all 20 Vitest tests, and its dev-server probe. Desktop (1440×900) and mobile (390×844) browser checks confirmed the primary action is visible and the frequency/status banners no longer overlap. The backend was not running during the visual check, so its expected offline state appeared; live API behavior was verified in Phase 4 below.

## Phase 4 execution update

Added a pinned Playwright dependency, a production-preview browser smoke test, and lockfile-based frontend installation in Docker. The browser test verified the fault-scenario start, live telemetry and reasoned decisions, pause/resume, speed adjustment, and stop through the real frontend/API flow. The isolated test backend uses file-backed SQLite to support concurrent simulation writes and dashboard reads.

Verification completed: 110 backend tests and Ruff passed; the frontend runtime plan passed its production build, 20 Vitest tests, and dev-server probe; the Playwright production-preview E2E passed; and `docker compose config --quiet` passed. The Docker daemon was unavailable, so Compose startup and a README-only fresh-clone test remain blocked. Build warnings and the untested browser screens are recorded in `docs/VERIFICATION.md`. No Rakshak files were changed or imported.

## Phase 5 execution update

Updated the README with BlackoutFree product framing, screenshot placeholders, a frontend/backend architecture diagram, Docker and local SQLite setup, accurate test commands, and a concise explanation of policy decisions. Aligned the public dashboard, document title, and API documentation with BlackoutFree while retaining internal `gridshield` identifiers. The audit, plan, design, and verification documents are present. No net-new Rakshak feature was adopted; the audit records what was retained and why Rakshak-only decoration or unsupported behavior was rejected.

Final limits remain: Docker service startup and fresh-clone verification require a running Docker engine; Vite reports the documented CJS/module-type and large-chunk warnings; six npm advisories (2 moderate, 2 high, 2 critical) remain untriaged; comparison/history/diagnostic browser screens are not covered by the smoke test; and all grid measurements are simulated rather than live.
