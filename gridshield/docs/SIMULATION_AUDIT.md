# Simulation behavior audit

## Scope and evidence

This audit follows the requested UI-to-simulation-to-visualization path through
the current `gridshield/` application. It inspects the React/Three.js frontend,
scenario tuning and types, FastAPI routes and schemas, simulation clock, grid
and disturbance models, policies, appliance state machine, shipped backend
scenario templates, and existing tests and documentation.

The audit was written before runtime changes. Its baseline backend suite passed
110 tests; baseline frontend type-checking and tests passed. The original
Playwright branding assertion was stale after the UI was renamed Rakshak.
Following the user's later request, Phases 4–12 have now also been implemented
and verified; current results are recorded in
[SIMULATION_VERIFICATION.md](./SIMULATION_VERIFICATION.md).

Relevant existing documentation includes [architecture.md](./architecture.md),
[assumptions.md](./assumptions.md), and [VERIFICATION.md](./VERIFICATION.md).
The latter reports an older verification state and should not be treated as
evidence for the current source without rerunning its commands.

## Existing architecture

- **Frontend:** React + TypeScript (`frontend/src/App.tsx`) owns the selected
  template and tuning-control state. `scenarioTuning.ts` builds the submitted
  scenario. `api/client.ts` calls FastAPI over REST and opens the run telemetry
  WebSocket. `CityTwin.tsx` maps backend building snapshots into stable Three.js
  building rigs in `scene/createStage.ts` and `scene/buildings.ts`.
- **API/configuration:** FastAPI routes live in `backend/app/api/`. Pydantic
  schemas validate scenario and response data. Scenario templates are loaded
  from `backend/data/scenarios/`, validated, then persisted by the repository.
- **Simulation:** `/runs` retrieves the persisted scenario, applies the
  requested seed, constructs `BuildingTwin`, `GridModel`, a disturbance profile,
  and the selected policy, then runs `SimulationClock` as a background task.
  The clock advances the RK4 grid state at `dt_s`, ticks appliances at each
  integration step, evaluates policies at the configured sample interval, and
  emits telemetry at the WebSocket interval.
- **Live state:** Telemetry and sequenced appliance-state updates share the run
  WebSocket. `GET /runs/{run_id}/buildings` remains the authoritative snapshot
  and reconciliation endpoint; the frontend also polls it and other diagnostics
  once per second.
- **Persistence:** Scenario, run, telemetry, event, and metric records use
  SQLModel and SQLite by default, or PostgreSQL in Compose. The active clock and
  building objects remain in process memory for live diagnostics.

## End-to-end data flow

```text
template selector + tuning controls
  -> App React state
  -> withScenarioTuning(template.config, seed, controls)
  -> POST /api/v1/scenarios (Pydantic validation and persistence)
  -> POST /api/v1/runs (policy + seed + playback/HIL options)
  -> persisted scenario snapshot -> BuildingTwin / GridModel / disturbance / policy
  -> SimulationClock integration and appliance ticks
  -> policy actions mutate appliance state and current_power_kw
  -> telemetry and appliance-update WebSocket + event REST endpoint + building snapshot REST endpoint
  -> App telemetry/state updates, replay cursor, and periodic snapshot reconciliation
  -> liveBuildings -> CityTwin -> CityStage.updateBuildings -> BuildingRig.setBuilding
  -> per-frame material/indicator interpolation in Three.js
```

`SimulationClock` derives the restoration incident key from the scenario JSON
excluding `scenario_id` and `seed`, and passes the explicit seed separately to
the restoration policy. The final API run snapshot returns the saved scenario,
policy, and seed. Building snapshots scale appliance rated/current kW by
`weight_k`; the frontend uses these snapshot values directly for live rendering.
Appliance transitions carry the same represented-building kW values, a global
monotonic sequence, simulation time, and update timestamp. WebSocket clients
can resume after a sequence cursor; retention gaps or queue overflow request a
fresh snapshot.

## UI-to-backend mapping

| UI control / source | Submitted field and transform | Backend consumer | Policies / notes |
|---|---|---|---|
| Scenario selector | Starts from the validated template config | `POST /scenarios`; stored config is read back by `POST /runs` | Template-only fields (buildings, weights, feeder stages, non-editable grid parameters, fault fields) are carried from the selected template. |
| Seed | `ScenarioConfig.seed`; same seed is sent to run start | Run endpoint overrides the persisted config seed and seeds disturbance/communication and policy calculations | No live-edit after start. |
| Disturbance type | `disturbance.type` | `make_disturbance` factory | generation loss, demand surge, combined, solar surplus, solar cloud drop. |
| Magnitude slider | Percent divided by 100 into `magnitude_pu` | Disturbance profile | For combined, backend divides the configured total equally between generation loss and demand surge. For solar cloud drop it is the reduction fraction, multiplied by `solar_share_pu`. |
| Solar share | Percent divided by 100 into `solar_share_pu` | `SolarCloudDropDisturbance` | Shown only for solar cloud dip. |
| Start, active duration, recovery ramp | `start_time_s`, template `duration_s`, `recovery_ramp_s` | Disturbance profile | UI can tune start/ramp but preserves active duration from the template. |
| Simulation duration | `simulation_duration_s` | `SimulationClock` termination condition | UI range is 90–1800 s and covers the 900 s severe preset. |
| Inertia | `grid_params.H` | Grid swing equation and restoration projection | |
| Governor droop / response | `grid_params.R` (percent divided by 100), `grid_params.Tg` | Grid governor equation | Droop UI allows 0.1–20%, matching the tuning validator's supported range. |
| S1/S2 frequency | `grid_params.f_s1_hz`, `f_s2_hz` | P1 feeder and P2 shedding logic | `withScenarioTuning` checks S1 > S2 > preset S3. |
| S0/S1/S2/S3 holds | `t_s0_hold_s`, `t_s1_hold_s`, `t_s2_hold_s`, `t_s3_hold_s` | P2: S0/S1 holds; P1: S1/S2/S3 feeder holds | P2 S2/S3 triggers are immediate; P1 does not consume S0. |
| P1 recovery hold | `t_p1_recovery_s` | P1 feeder restoration | Not used by P2 restoration. |
| O1 hold | `t_o1_hold_s` | P2/P3 over-frequency deferrable-load absorption | P0/P1 do not consume it. |
| Restoration stability | `t_stable_s` | P2 staggered/synchronized restoration | P3 disables automatic restoration; P1 uses its separate P1 recovery hold. |
| Edge mode / comm-loss slider | `edge_mode`; `fault_config.loss_probability` | `EdgeAgent` for P2/P3; seeded random link sample every agent tick | P0/P1 do not instantiate edge agents. UI covers the full 0–100% schema range. |
| Playback speed | `/runs` request `playback_speed`, later `/speed` | `SimulationClock` wall-time pacing | Backend validates 1–120×. |
| HIL enabled / port / building | `/runs` options `hil_port`, `hil_building_id`; API baud rate defaults to 115200 | Optional serial adapter for P2 modes | A target building must exist in the persisted scenario. |
| Comparison seed count | `POST /experiments/compare` `n_seeds` | Paired four-policy backend comparison | P3 is not part of this comparison endpoint. |

The frontend scenario contract now includes the backend's startup-recovery
profile, feeder-stage assignments, and complete grid parameter set. API tests
compare template keys with the Pydantic schema and verify that the effective
run snapshot returns the saved scenario. Runtime validation of arbitrary
frontend API responses remains outside this implementation.

## Findings

Severity is based on the scope of incorrect simulation or user-visible state;
it is not a calibrated risk score.

| ID | Severity | Finding and evidence | Impact | Recommended correction |
|---|---|---|---|---|
| A1 | High | `frontend/src/scene/buildingState.ts` treats `ceiling_fan` as a lighting load, falls back to all appliances if no light exists, and computes illumination by counting active records rather than aggregating their power. | A fan, refrigerator, AC, or other powered appliance can illuminate windows; partial-load lighting is inaccurate; buildings with no LED load can show fabricated light. | Derive a clamped ratio only from `lighting_led` snapshots using total current kW / total rated kW; return zero explicitly when there is no rated LED load. Cover all requested states and appliance indicator behavior with unit tests. |
| A2 | High | Appliance snapshots are only polled by `App.tsx` once per second. The existing WebSocket in `api/websocket.py` publishes telemetry samples only. | At 30–120×, state transitions can occur between polls and never be rendered as intermediate transitions. The next snapshot converges to the latest state but does not guarantee delivery of important transitions. | Publish bounded, sequenced appliance-state deltas alongside (not instead of) telemetry, reject stale messages per run, and keep periodic full-state reconciliation with sequence metadata. |
| A3 | High | `PriorityEdgePolicy` S0 action writes 70% power directly, while `Appliance.tick()` resets an `ON` appliance's power to rated power at the next integration step. | S0 throttling is transient and does not persist for the configured interval; its event can imply an action that the following step undoes. | Represent the throttle in appliance state/power logic (or remove the claimed action), and test power and demand over multiple integration ticks. |
| A4 | High | Edge modes originally shared almost all policy behavior. | The selector suggested distinctions that did not alter dispatch behavior. | **Resolved for P2/P3:** central pauses during grace then fails over to autonomous local evaluation; distributed keeps local evaluation during link loss; communication-degraded pauses until reconnection; islanded mode always runs locally and reports no link. P0/P1 edge controls are disabled. Focused transition and recovery tests cover the modes. |
| A5 | Medium | All timing and edge controls were enabled regardless of policy. | Users could change settings unused by the selected run. | **Resolved:** policy-inapplicable thresholds, holds, restoration, edge mode, and communication-loss controls are disabled. |
| A6 | Medium | Simulation duration slider capped at 600 seconds despite a shipped 900-second preset. | Preset duration was outside the control's range. | **Resolved:** range now extends to 1800 seconds. |
| A7 | Medium | Communication-loss slider capped at 50% while Pydantic accepts 0–100%. | UI could not explore full supported range. | **Resolved:** range now matches 0–100%. |
| A8 | Medium | Frontend scenario interfaces omitted backend fields. | Schema drift could lose or mis-handle values. | **Resolved for static contract coverage:** complete nested fields, scenario-template contract checks, and effective run-snapshot tests are present. Arbitrary runtime API response validation is not added. |
| A9 | Medium | Playwright asserted the old “BlackoutFree” page title/header. | E2E was stale after the Rakshak rebrand and did not verify tuning/inspector behavior. | **Resolved:** Rakshak branding, policy-aware controls, effective run configuration, and live simulation flow are covered by Playwright. Three.js material appearance is covered by state logic tests, not screenshot comparison. |
| A10 | Medium | Visual mapping coverage was incomplete and there was no authoritative live-run inspector. | Incorrect visual mappings and live run/config discrepancies were difficult to diagnose. | **Resolved:** LED power-ratio and appliance-state indicator tests were expanded; rig reuse is tested; the inspector reads scenario/policy from the backend run snapshot and live telemetry/building/agent/restoration state. |
| A11 | Low | Root `data/scenarios/` and `backend/data/scenarios/` contain same-named but non-identical YAML files; the scenario API loads the backend copy. | Edits to the unused copy can be mistaken for active preset changes. | Choose and document one canonical scenario directory; compare/validate duplicate copies before removal or consolidation. |
| A12 | Low | Existing test coverage did not verify important disturbance/policy behavior through API and live simulation. | Passing isolated unit tests did not establish runtime integration. | **Improved:** disturbance-profile, policy, snapshot, contract, and browser simulation coverage was added. The E2E checks a live backend run and reasoned decisions; it does not exhaustively replay every disturbance × policy pair in the browser. |

## Implementation status through Phase 12

- **A1 fixed:** window illumination uses only powered `lighting_led` appliances
  and a clamped current/rated-power ratio; appliance indicator and blackout
  states have focused frontend tests.
- **A2 fixed:** appliance transitions are sequenced, replayable, streamed, and
  reconciled against versioned snapshots. Queue overflow and replay gaps
  request an authoritative snapshot.
- **A3 fixed:** S0's 70% power limit persists across appliance ticks, emits
  demand and event deltas, restores when frequency leaves the S0 band, and
  produces a sequenced update even when the appliance state remains ON.
- **A4–A5 fixed:** edge modes have distinct connection-loss behavior and
  policy-irrelevant controls are disabled. P0/P1 do not expose edge controls
  they do not consume.
- **A6–A7 fixed:** duration controls cover the 900 s shipped preset and
  communication loss spans the backend-supported 0–100%.
- **A8 improved:** TypeScript covers the nested scenario fields, API tests
  verify the template contract, and run snapshots are checked against the
  persisted effective scenario. Runtime validation of arbitrary API responses
  is not included.
- **A9–A10 fixed:** Rakshak E2E branding is current; the run inspector uses the
  saved backend scenario/policy and live telemetry, building state, edge-agent,
  and restoration status. LED/appliance visual mappings and stable rig reuse
  have focused tests.
- **A11 remains open:** the API loads canonical templates from
  `backend/data/scenarios/`; same-named root `data/scenarios/` copies remain
  and were not consolidated.
- **A12 improved:** disturbance, policy, API-contract, snapshot, and live-run
  browser tests were added. The Playwright flow does not exhaustively replay
  every disturbance × policy combination.

## Disturbance and policy behavior verified statically

- Generation loss and demand surge use the same non-negative magnitude and
  timed active/recovery profile, but are represented in separate signed
  generation and demand components. The grid swing equation applies those
  signs so both lower frequency.
- Combined disturbance splits total `magnitude_pu` equally into generation
  loss and demand surge; the total imbalance therefore equals the configured
  magnitude, not twice the magnitude.
- Solar surplus produces a positive generation change and raises frequency.
- Solar cloud dip computes `solar_share_pu * magnitude_pu`; the existing backend
  test checks `0.40 * 0.18 == 0.072` pu.
- P0 is no-op; P1 trips configured feeder groups without priority awareness and
  can interrupt critical appliances; P2 sheds by priority and protects critical
  appliances; synchronized P2 changes restoration batching; P3 disables
  automatic restoration.
- P1 uses configured S1/S2/S3 holds and P1 recovery hold. P2 uses S1 hold,
  immediate S2/S3 triggers (including its RoCoF path), S0/O1 timers, and P2
  restoration stability. These differences are material to the tuning UI.
- Delay, duplication, and out-of-order fault settings are explicitly rejected
  by scenario validation because the in-process fault bus is not wired into
  active run execution. Only seeded packet-loss sampling is used for edge
  connectivity.

These are reduced-order simulation behaviors, not live utility measurements,
validated protection settings, a solved feeder power flow, or real HIL/AMI
telemetry. The procedural city and feeder animations are illustrative and do
not model geographic or electrical topology.

## Phase 11 verification

The final command results and environment notes are recorded in
[SIMULATION_VERIFICATION.md](./SIMULATION_VERIFICATION.md). The full backend
suite, backend lint, frontend type-check/tests/build, and Playwright browser
flow passed after implementation.
