# Simulation Phases 4–12 Verification

## Scope

This report records implementation and verification for the requested
simulation work after Phases 1–3. Findings, architecture, and UI-to-backend
mapping are in [SIMULATION_AUDIT.md](./SIMULATION_AUDIT.md).

## Phase completion

| Phase | Result |
|---|---|
| 4 — Disturbance profiles | Corrected solar-surplus generation sign; profile component and clock/telemetry tests cover all five disturbance types, including sign, magnitude, timing, recovery, and frequency direction. |
| 5 — Policy actions | Made the P2 S0 70% deferrable-load throttle persistent through appliance ticks, recoverable above the threshold, and observable through event, demand, and sequenced building-state updates. |
| 6 — Edge dispatch | Defined behavior for centralized grace/failover, continuous distributed local control, communication-degraded pause/reconnect, and always-autonomous islanded operation. Added sustained/intermittent loss and recovery tests. |
| 7 — Scenario contract and controls | Completed frontend scenario fields; verified template keys and effective run snapshots through API tests. Disabled policy-irrelevant controls and expanded duration, communication-loss, and droop ranges. |
| 8 — Visual consistency | Retained LED-power-ratio lighting and appliance-specific indicator mappings; tested state transitions and reuse of stable building rigs. |
| 9 — Run inspector | Added a diagnostics view sourced from the selected backend run snapshot and live telemetry, building state, edge-agent, and restoration status. |
| 10 — Test coverage | Expanded backend, frontend, API, and Playwright coverage. The browser flow verifies Rakshak branding, policy-aware controls, a live run, reasoned events, and the saved effective configuration. |
| 11 — Verification | Full backend tests/lint, frontend type-check/tests/build, and the Playwright smoke flow passed. |
| 12 — Documentation | Updated the audit and this report with results, limitations, and remaining work. |

## Commands and results

| Command | Result |
|---|---|
| `python -m pytest -q` from `backend\` | **Passed:** 131 tests in 189.49 s. |
| `python -m ruff check app tests` from `backend\` | **Passed.** |
| `npm run check` from `frontend\` | **Passed.** |
| `npm test` from `frontend\` | **Passed:** 8 files, 42 tests. |
| `npm run build` from `frontend\` | **Passed.** |
| `npm run test:e2e` from `frontend\` | **Passed:** 1 Playwright test, including live backend simulation and run inspection. |

Port 8001 was already occupied in the test environment. The Playwright
configuration now accepts origin overrides; the successful browser run used
these PowerShell values to keep the existing listener untouched:

```powershell
$env:GRIDSHIELD_E2E_API_ORIGIN = "http://127.0.0.1:8002"
$env:GRIDSHIELD_E2E_FRONTEND_ORIGIN = "http://127.0.0.1:3002"
npm run test:e2e
```

With the default ports free, no overrides are required. The successful build
and E2E run reported existing tooling warnings: Vite's CJS Node API is
deprecated, `postcss.config.js` is reparsed as an ES module because
`package.json` does not declare a module type, and the minified JavaScript
bundle exceeds 500 kB. They did not fail type-checking, tests, build, or E2E.

## Remaining limitations

- The similarly named root `data/scenarios/` copies remain; the API currently
  loads templates from `backend/data/scenarios/`. No consolidation was done.
- The browser suite verifies live policy decisions and saved configuration,
  but does not pixel-compare Three.js materials or exhaustively test every
  disturbance × policy combination in a browser. Visual state mappings and
  rig reuse are covered by focused frontend tests.
- Communication delay, duplication, and out-of-order fault fields remain
  rejected because the in-process fault bus is not wired into active runs.
- The grid, feeder, HIL, and appliance behaviors remain reduced-order
  simulation outputs. They are not calibrated protection settings, measured
  utility data, a solved power flow, or evidence of real-world protection.
