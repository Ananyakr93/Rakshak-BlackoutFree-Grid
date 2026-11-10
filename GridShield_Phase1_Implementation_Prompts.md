# GridShield — Phase 1 Implementation Prompts for AI Agent

**Project full name:** GridShield: Edge-Intelligent Demand Response Digital Twin  
**Internal code name:** Project Rakshak  
**Subtitle:** *Appliance-Level, Priority-Aware Demand-Side Frequency Response for the Indian Grid — a Karnataka-Calibrated Digital Twin*  
**Phase 1 scope:** Deterministic grid simulator with governor, staged thresholds, appliance twins, closed-loop edge-agent control, baseline policy emulator, staggered restoration, FastAPI + WebSocket backend, React dashboard, PostgreSQL persistence, and the core experiment matrix (E1–E4).  
**Stack (zero cost):** Python, NumPy/SciPy, Pydantic, FastAPI, WebSockets, React + TypeScript + Vite + Tailwind + Chart.js, PostgreSQL, SQLModel, pytest, Ruff, Docker Compose.

---

## How to use these prompts

Give each prompt to the AI agent in the order listed. Each prompt builds on the output of the previous one. Do **not** skip ahead. After each prompt, verify the exit criteria before proceeding.

Every prompt follows the pattern:
1. **Context** — what exists so far.
2. **Task** — what to build now.
3. **Exit criteria** — how to confirm it is done correctly.
4. **Hard constraints** — non-negotiable rules the agent must follow.

---

## PROMPT 1 — Repository scaffold and project skeleton

### Context
Nothing exists yet. We are starting from scratch.

### Task
Create the full repository skeleton for the GridShield digital twin project. Do not implement any logic yet — only create the directory structure, empty or stub files, and configuration files listed below.

Create the following layout exactly:

```
gridshield/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── scenarios.py
│   │   │   ├── runs.py
│   │   │   ├── metrics.py
│   │   │   └── websocket.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── logging.py
│   │   ├── twin/
│   │   │   ├── __init__.py
│   │   │   ├── grid_model.py
│   │   │   ├── simulation_clock.py
│   │   │   ├── disturbances.py
│   │   │   ├── building_twin.py
│   │   │   └── appliance.py
│   │   ├── control/
│   │   │   ├── __init__.py
│   │   │   ├── edge_agent.py
│   │   │   ├── shedding_policy.py
│   │   │   └── restoration_policy.py
│   │   ├── evaluation/
│   │   │   ├── __init__.py
│   │   │   ├── metrics.py
│   │   │   └── experiments.py
│   │   ├── messaging/
│   │   │   ├── __init__.py
│   │   │   └── in_process_bus.py
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── models.py
│   │   │   └── repository.py
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── scenario.py
│   │       ├── events.py
│   │       └── telemetry.py
│   ├── tests/
│   │   ├── unit/
│   │   │   └── __init__.py
│   │   ├── integration/
│   │   │   └── __init__.py
│   │   └── scenarios/
│   │       └── __init__.py
│   ├── pyproject.toml
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── charts/
│   │   ├── api/
│   │   ├── hooks/
│   │   └── types/
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   └── vite.config.ts
├── data/
│   ├── raw/
│   ├── processed/
│   └── scenarios/
│       └── default_scenario.yaml
├── experiments/
│   ├── baseline/
│   ├── controller_comparison/
│   └── sensitivity_analysis/
├── docs/
│   ├── architecture.md
│   ├── assumptions.md
│   ├── data_dictionary.md
│   └── experiment_protocol.md
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

For `pyproject.toml` pinned dependencies include: `fastapi==0.115.0`, `uvicorn[standard]==0.30.6`, `pydantic==2.9.2`, `pydantic-settings==2.5.2`, `sqlmodel==0.0.21`, `asyncpg==0.29.0`, `numpy==1.26.4`, `scipy==1.13.1`, `pandas==2.2.3`, `pytest==8.3.3`, `pytest-asyncio==0.24.0`, `httpx==0.27.2`, `ruff==0.6.9`.

For `package.json` (frontend): `react@18.3.1`, `react-dom@18.3.1`, `typescript@5.6.3`, `vite@5.4.8`, `@vitejs/plugin-react@4.3.2`, `tailwindcss@3.4.13`, `chart.js@4.4.4`, `react-chartjs-2@5.2.0`.

In `docker-compose.yml`, define three services: `postgres` (postgres:16-alpine, port 5432), `backend` (FastAPI, port 8000), `frontend` (Vite dev, port 3000).

In `docs/assumptions.md` pre-populate the parameter table:

| Parameter | Symbol | Default | Source |
|-----------|--------|---------|--------|
| Nominal frequency | f₀ | 50 Hz | IEGC 2023 |
| Inertia constant | H | 4.0 s | Sweep 3–6 s |
| Load damping | D | 1.5 | Sweep 1–2 pu |
| Droop | R | 0.05 | IEGC 2023 (5%) |
| Governor deadband | ±db | ±0.03 Hz | IEGC 2023 |
| Governor time const | Tg | 0.1 s | Literature |
| Turbine time const | Tt | 0.4 s | Literature |
| RK4 time step | dt | 0.02 s | Numerical test |
| Agent sample interval | T_agent | 0.5 s | Configurable |
| S0 trigger | f_s0 | 49.90 Hz | IEGC lower bound |
| S1 trigger | f_s1 | 49.85 Hz | ADMS trip level |
| S2 trigger | f_s2 | 49.60 Hz | Synopsis |
| S3 trigger | f_s3 | 49.40 Hz | UFLS stage 1 |
| O1 absorb | f_o1 | 50.05 Hz | IEGC upper bound |
| Recovery band | f_rec | 49.95 Hz | With hysteresis |
| Stability hold | T_stable | 60 s | Design choice |

### Hard constraints
- Do NOT implement any physics or simulation logic in this prompt.
- Every Python file must have a module-level docstring.
- `.gitignore` must exclude `data/raw/`, `*.env`, `__pycache__/`, `node_modules/`, `.venv/`, `*.db`.
- `README.md` must contain project name, one-paragraph description, and a Getting Started section.

### Exit criteria
- `docker compose up` starts all three services without errors.
- `cd backend && python -m pytest tests/` runs and reports 0 tests collected (not an error).
- `cd frontend && npm run dev` starts the Vite dev server.
- `python -c "from app.twin import grid_model"` succeeds from inside `backend/`.


---

## PROMPT 2 — Configuration, schemas, and database models

### Context
The repository skeleton exists. No logic is implemented yet.

### Task
Implement the configuration layer, Pydantic v2 schemas, and SQLModel database table models.

#### 2A. `backend/app/core/config.py`
Implement a `Settings` class using `pydantic-settings` that reads from environment variables and `.env`:
- `DATABASE_URL: str` — PostgreSQL async URL
- `API_V1_PREFIX: str = "/api/v1"`
- `SIMULATION_DT_S: float = 0.02`
- `AGENT_SAMPLE_INTERVAL_S: float = 0.5`
- `WS_PUSH_INTERVAL_S: float = 0.5`
- `LOG_LEVEL: str = "INFO"`
- `CORS_ORIGINS: list[str] = ["http://localhost:3000"]`

#### 2B. `backend/app/schemas/scenario.py`
Implement Pydantic v2 schemas (request/response shapes, NOT table models):
- `ApplianceConfig` — `appliance_id`, `appliance_type`, `priority (Literal["critical","essential","deferrable"])`, `rated_power_kw`, `min_on_time_s`, `min_off_time_s`, `max_shed_minutes`, `enrolled (bool=True)`
- `BuildingConfig` — `building_id`, `weight_k (int=1)`, `appliances (list[ApplianceConfig])`
- `DisturbanceConfig` — `type (Literal["generation_loss","demand_surge","combined","solar_surplus"])`, `start_time_s`, `magnitude_pu`, `duration_s`, `recovery_ramp_s (float=30.0)`
- `GridParams` — `H`, `D`, `R`, `deadband_hz`, `Tg`, `Tt`, `up_reserve_pu`, `down_reserve_pu`, `f0 (float=50.0)`, all thresholds from assumptions.md as optional fields with defaults
- `ScenarioConfig` — `scenario_id (UUID)`, `name`, `description`, `seed (int)`, `simulation_duration_s`, `area_mode (Literal["scaled","islanded"])`, `disturbance (DisturbanceConfig)`, `grid_params (GridParams)`, `buildings (list[BuildingConfig])`

#### 2C. `backend/app/schemas/events.py`
- `ControlEvent` — `event_id (UUID)`, `run_id (UUID)`, `simulation_time_s`, `wall_clock_ts (datetime UTC)`, `event_type`, `building_id`, `appliance_id (str|None)`, `reason`, `frequency_hz`, `priority (str|None)`, `schema_version (str="1.0")`

#### 2D. `backend/app/schemas/telemetry.py`
- `TelemetrySample` — `run_id (UUID)`, `simulation_time_s`, `wall_clock_ts`, `frequency_hz`, `generation_pu`, `demand_pu`, `frequency_stage (str)`, `rocof_hz_per_s (float)`, `sequence_number (int)`, `schema_version (str="1.0")`
- `RunState` — `run_id (UUID)`, `status (Literal["pending","running","completed","failed"])`, `current_time_s`, `latest_sample (TelemetrySample|None)`, `active_buildings (int)`

#### 2E. `backend/app/db/models.py`
SQLModel table models (`table=True`):
- `Scenario` — `id (UUID PK)`, `name`, `description`, `seed (int)`, `config_json (str)`, `created_at`
- `SimulationRun` — `id (UUID PK)`, `scenario_id (UUID FK)`, `seed (int)`, `policy (str)`, `status`, `started_at`, `completed_at (nullable)`, `config_snapshot_json`, `model_version`
- `Building` — `id (str PK)`, `run_id (UUID FK)`, `weight_k (int)`, `feeder_label (nullable str)`
- `ApplianceRecord` — `id (str PK)`, `building_id (str FK)`, `appliance_type`, `priority`, `rated_power_kw`, `enrolled (bool)`, `min_on_time_s`, `min_off_time_s`, `max_shed_minutes (nullable)`
- `TelemetryRecord` — `id (int PK auto)`, `run_id (UUID FK)`, `simulation_time_s`, `wall_clock_ts`, `frequency_hz`, `generation_pu`, `demand_pu`, `frequency_stage`, `rocof_hz_per_s`, `sequence_number`
- `ControlEventRecord` — `id (UUID PK)`, `run_id (UUID FK)`, `simulation_time_s`, `wall_clock_ts`, `event_type`, `building_id`, `appliance_id (nullable)`, `reason`, `frequency_hz`, `priority (nullable)`
- `RunMetric` — `id (int PK auto)`, `run_id (UUID FK)`, `metric_name`, `metric_value (float)`, `unit`, `notes (nullable)`

#### 2F. `backend/app/db/repository.py`
Async repository functions:
- `create_scenario`, `get_scenario`, `create_run`, `update_run_status`
- `save_telemetry_batch(session, list[TelemetrySample]) -> None`
- `save_control_event(session, ControlEvent) -> None`
- `save_metrics(session, run_id, dict[str, tuple[float,str]]) -> None`
- `get_run_metrics`, `get_telemetry`, `get_control_events`

#### 2G. `data/scenarios/default_scenario.yaml`
Write a complete valid scenario matching `ScenarioConfig`:
- 3 buildings, 5–7 Indian appliances each (split-AC, geyser, EV-charger, ceiling-fan, medical-device [critical], water-pump, refrigerator)
- `area_mode: "scaled"`, `disturbance.type: "generation_loss"`, `disturbance.start_time_s: 10.0`, `disturbance.magnitude_pu: 0.15`, `seed: 42`

### Hard constraints
- Pydantic v2 validators for: `magnitude_pu > 0 and <= 1`, `seed >= 0`, `rated_power_kw > 0`.
- All timestamps UTC.
- Field names include units where ambiguous (`_s`, `_hz`, `_kw`, `_pu`).
- No `Any` type anywhere.
- Schemas use `model_config = ConfigDict(frozen=True)` except where mutation is required.

### Exit criteria
- `python -c "import yaml; from app.schemas.scenario import ScenarioConfig; ScenarioConfig(**yaml.safe_load(open('../data/scenarios/default_scenario.yaml')))"` succeeds.
- `python -c "from app.db.models import SimulationRun, TelemetryRecord, ControlEventRecord"` succeeds.
- `ruff check app/` reports zero violations.


---

## PROMPT 3 — Grid dynamics model with governor

### Context
Repository skeleton, schemas, and database models are complete and tested.

### Task
Implement the per-unit grid frequency model with governor in `backend/app/twin/grid_model.py`.

#### Physics equations
```
Swing equation:   2H * d(Δω)/dt = ΔPm - ΔPL - D * Δω
Governor:         Tg * d(ΔPg)/dt = -ΔPg - (1/R) * DB(Δω)
Turbine:          Tt * d(ΔPm)/dt = ΔPg - ΔPm
Headroom clamp:   ΔPm ∈ [-down_reserve, +up_reserve]

where:
  Δω = (f - f₀) / f₀,   f₀ = 50 Hz
  f  = f₀ * (1 + Δω)
  DB(Δω) = Δω  if |Δω * f₀| > deadband_hz, else 0
  ΔPL = disturbance_pu(t) + demand_delta_pu (from appliance shedding)
```

Numerical method: **RK4 at dt from `GridParams.dt_s` (default 0.02 s)**.

#### `GridState` (frozen dataclass)
Fields: `time_s`, `frequency_hz`, `delta_omega`, `delta_Pm`, `delta_Pg`, `demand_pu`, `generation_pu`, `disturbance_pu`, `rocof_hz_per_s`

#### `GridModel` class
```python
class GridModel:
    def __init__(self, params: GridParams, mode: Literal["scaled","islanded"]) -> None: ...
    def step(self, state: GridState, disturbance_pu: float, demand_delta_pu: float) -> GridState: ...
    def frequency_stage(self, state: GridState) -> str: ...
    def initial_state(self) -> GridState: ...
```

- `step()` must be a **pure function** (no side effects, immutable input).
- `frequency_stage()` returns one of: `"normal"`, `"s0_advisory"`, `"s1"`, `"s2"`, `"s3"`, `"o1_absorb"`, `"o2_absorb_plus"`.
- Stage boundaries come from `GridParams` threshold fields (see Prompt 2 defaults).
- For S2: also trigger if `rocof_hz_per_s <= -0.3`.
- `initial_state()` returns a `GridState` at t=0, f=50.0 Hz, all deltas zero.

#### Unit tests: `tests/unit/test_grid_model.py`
Write these 7 tests:

1. **No disturbance:** 300 s run with zero disturbance, frequency stays 50.0 ± 1e-6 Hz.
2. **Generation loss direction:** After `disturbance_pu = 0.10`, frequency falls below 49.9 Hz within 10 s.
3. **Demand reduction direction:** After demand shed (`demand_delta_pu = -0.05`), frequency rises or stops falling compared to unshed trajectory.
4. **Governor deadband:** Tiny disturbance within ±0.03 Hz band: `delta_Pg` stays zero for at least 20 steps.
5. **Headroom saturation:** With `disturbance_pu = 0.5` (large), `delta_Pm` never exceeds `up_reserve_pu`.
6. **RK4 convergence:** Same scenario at dt=0.01 vs dt=0.02 — final frequency difference < 0.01 Hz.
7. **Stage classification:** Assert correct stage label for f values: 49.39 → "s3", 49.59 → "s2", 49.84 → "s1", 49.89 → "s0_advisory", 50.04 → "normal", 50.19 → "o2_absorb_plus".

### Hard constraints
- `step()` must be pure — no mutations, no global state.
- All parameters from `GridParams` only; no hardcoded physics constants.
- Document every equation in a docstring referencing framework.md §7.
- Model must NOT self-reset frequency. Recovery emerges from governor + load.
- `rocof_hz_per_s` computed as `(f_new - f_old) / dt_s`.

### Exit criteria
- `pytest tests/unit/test_grid_model.py -v` — all 7 tests pass.
- `ruff check app/twin/grid_model.py` — zero violations.
- No-disturbance test confirms frequency within 1e-6 Hz of 50.0 Hz.

---

## PROMPT 4 — Disturbance engine and simulation clock

### Context
Grid model with governor is implemented and all 7 tests pass.

### Task
Implement the disturbance engine (`disturbances.py`) and the simulation clock (`simulation_clock.py`).

#### 4A. `backend/app/twin/disturbances.py`

Abstract base class:
```python
class DisturbanceProfile(ABC):
    @abstractmethod
    def get_disturbance_pu(self, sim_time_s: float) -> float: ...
    # +ve = generation loss or demand surplus (f falls)
    # -ve = demand reduction or solar surplus (f rises)
```

Concrete classes:
- `GenerationLossDisturbance(start_time_s, magnitude_pu, duration_s, recovery_ramp_s)` — step up at start, hold, then linear ramp back to 0.
- `DemandSurgeDisturbance` — same shape, positive sign.
- `CombinedDisturbance(gen_loss: GenerationLossDisturbance, demand_surge: DemandSurgeDisturbance)` — sum of both.
- `SolarSurplusDisturbance(start_time_s, magnitude_pu, duration_s, recovery_ramp_s)` — negative magnitude (over-frequency scenario).

Factory: `make_disturbance(config: DisturbanceConfig, seed: int) -> DisturbanceProfile`.

#### 4B. `backend/app/twin/simulation_clock.py`

```python
class SimulationResult:
    run_id: UUID
    scenario_id: UUID
    policy: str
    seed: int
    final_state: GridState
    events: list[ControlEvent]
    metrics: dict[str, float]   # populated by evaluation engine in Prompt 8

class SimulationClock:
    def __init__(
        self,
        scenario: ScenarioConfig,
        grid: GridModel,
        disturbance: DisturbanceProfile,
        buildings: list,           # BuildingTwin instances from Prompt 5
        policy,                    # BasePolicy from Prompt 6
        telemetry_sink: Callable[[TelemetrySample], Awaitable[None]],
        event_sink: Callable[[ControlEvent], Awaitable[None]],
    ) -> None: ...

    async def run(self) -> SimulationResult: ...
    def stop(self) -> None: ...
    def current_state(self) -> GridState: ...
```

Loop logic:
1. Advance grid by one RK4 step. Collect `disturbance_pu` from profile.
2. Every `AGENT_SAMPLE_INTERVAL_S`: tick all building edge agents. Accumulate appliance demand deltas.
3. Pass accumulated demand delta to the next grid step (`demand_delta_pu`).
4. Every `WS_PUSH_INTERVAL_S`: call `telemetry_sink`.
5. Stop when `sim_time >= simulation_duration_s` or `stop()` called.
6. Return `SimulationResult`.

#### 4C. Unit tests: `tests/unit/test_disturbances.py`
1. `GenerationLossDisturbance` returns 0 before `start_time_s`.
2. Returns `magnitude_pu` during active window.
3. Returns 0 after full recovery ramp.
4. `SolarSurplusDisturbance` returns negative value during active window.
5. `make_disturbance` returns correct subclass for each `DisturbanceConfig.type`.

#### 4D. Integration smoke test: `tests/integration/test_clock_no_buildings.py`
Run `SimulationClock` with no buildings, no policy, `duration_s=60`, generation loss 0.15 pu. Assert: minimum frequency recorded is below 49.60 Hz (S2 territory — governor alone cannot arrest 15% loss in 60 s).

### Hard constraints
- `SimulationClock.run()` must be `async` and must not block the event loop per step (use `await asyncio.sleep(0)` at appropriate intervals).
- `telemetry_sink` and `event_sink` are injected — clock has no direct DB dependency.
- Accumulated demand delta = sum of all appliance changes since last grid step, not just latest tick.

### Exit criteria
- All 5 disturbance unit tests pass.
- Smoke test: minimum frequency < 49.60 Hz with no demand response active.
- `ruff check` zero violations on new files.


---

## PROMPT 5 — Building twins and appliance state machines

### Context
Grid model, disturbance engine, and simulation clock skeleton exist. Now implement the building and appliance layer.

### Task
Implement `backend/app/twin/appliance.py` and `backend/app/twin/building_twin.py`.

#### 5A. `backend/app/twin/appliance.py`

```python
class ApplianceState(str, Enum):
    OFF = "OFF"
    ON = "ON"
    SHED = "SHED"
    WAITING_RESTORATION = "WAITING_RESTORATION"
    LOCKED_OUT = "LOCKED_OUT"       # min on/off time not yet satisfied
    UNAVAILABLE = "UNAVAILABLE"     # fault or unknown

class Appliance:
    appliance_id: str
    building_id: str
    appliance_type: str
    priority: Literal["critical", "essential", "deferrable"]
    rated_power_kw: float
    min_on_time_s: float
    min_off_time_s: float
    max_shed_minutes: float | None
    enrolled: bool

    # runtime state
    state: ApplianceState
    last_state_change_s: float      # simulation time of last transition
    current_power_kw: float         # actual current demand (0 if shed/off)

    def shed(self, sim_time_s: float) -> float:
        """Attempt shed. Returns demand delta (negative = load removed).
        No-op and returns 0.0 if: priority is critical, not enrolled,
        state is not ON, or lockout/min-on-time not satisfied."""
        ...

    def restore(self, sim_time_s: float) -> float:
        """Attempt restore. Returns demand delta (positive = load added).
        No-op and returns 0.0 if state is not WAITING_RESTORATION,
        or min-off-time not satisfied."""
        ...

    def mark_waiting_restoration(self, sim_time_s: float) -> None:
        """Transition from SHED → WAITING_RESTORATION."""
        ...

    def can_shed(self, sim_time_s: float) -> bool:
        """True if appliance is eligible to be shed right now."""
        ...

    def is_shed_too_long(self, sim_time_s: float) -> bool:
        """True if max_shed_minutes exceeded. Only relevant if set."""
        ...

    def tick(self, sim_time_s: float) -> None:
        """Advance internal lockout/timer logic per simulation step."""
        ...
```

Rules to enforce in state transitions:
- `critical` priority appliances: `shed()` always returns 0.0 and leaves state unchanged.
- `min_on_time_s`: cannot shed if `sim_time_s - last_state_change_s < min_on_time_s` after last ON transition.
- `min_off_time_s`: cannot restore if appliance has not been in SHED/WAITING state for `min_off_time_s`.
- A state change **must** update `current_power_kw` immediately (0 when shed, `rated_power_kw` when restored).

#### 5B. `backend/app/twin/building_twin.py`

```python
class BuildingTwin:
    building_id: str
    weight_k: int                   # real buildings this twin represents
    appliances: list[Appliance]
    total_demand_kw: float          # sum of current_power_kw across all appliances

    def get_shed_candidates(self, priority: str | None = None) -> list[Appliance]:
        """Return enrolled, ON appliances eligible to shed, optionally filtered by priority tier."""
        ...

    def get_restoration_candidates(self) -> list[Appliance]:
        """Return appliances in WAITING_RESTORATION state that satisfy min-off-time."""
        ...

    def apply_demand_delta(self) -> float:
        """Recompute total_demand_kw from appliance states. Returns delta vs previous value."""
        ...

    def tick(self, sim_time_s: float) -> None:
        """Advance all appliance timers."""
        ...
```

#### 5C. Unit tests: `tests/unit/test_appliance.py`
1. Shedding a `critical` appliance does nothing — state unchanged, demand delta = 0.
2. Shedding a `deferrable` ON appliance transitions to SHED and returns negative demand delta.
3. Cannot shed an appliance again if it is already SHED.
4. `min_on_time_s` lockout: shed returns 0 if called before min on time has elapsed.
5. Restoring transitions WAITING_RESTORATION → ON and returns positive demand delta.
6. `max_shed_minutes` exceeded: `is_shed_too_long()` returns True at correct sim time.
7. `BuildingTwin.total_demand_kw` equals sum of all `current_power_kw` after shedding two appliances.

### Hard constraints
- Shedding a `critical` appliance must **never** succeed under the standard policy — enforce in the `Appliance` class itself, not just in the policy layer.
- State transitions must update `current_power_kw` atomically.
- No floating-point demand tracking bugs: use `rated_power_kw` directly, not incremental accumulation.

### Exit criteria
- All 7 unit tests pass: `pytest tests/unit/test_appliance.py -v`.
- `BuildingTwin.apply_demand_delta()` returns 0.0 when no state changes occurred.
- `ruff check` zero violations.

---

## PROMPT 6 — Edge agents, shedding and restoration policies

### Context
Appliance state machines and building twins are implemented and tested.

### Task
Implement the virtual edge agents and the three Phase 1 policies.

#### 6A. Policy base class: `backend/app/control/shedding_policy.py`

```python
class BasePolicy(ABC):
    policy_name: str

    @abstractmethod
    def evaluate(
        self,
        grid_state: GridState,
        building: BuildingTwin,
        sim_time_s: float,
    ) -> list[ControlEvent]:
        """Evaluate policy for one building at one agent tick.
        Returns list of ControlEvent describing decisions made."""
        ...
```

Implement three policies:

**P0 — UnmanagedPolicy:**  No shed actions. Returns empty list always. Still records a no-op event for logging at each tick if frequency < S1 trigger (for audit trail).

**P1 — ADMSFeederPolicy (SR-ADMS + UFLS emulator):**
- Simulates the Southern Region ADMS feeder-tripping pattern.
- Has configurable feeder groups (list of `building_id` sets). Stage 1 trips at 49.85 Hz after 5 s sustained, Stage 2 at 49.60 Hz after 2 s, Stage 3 at 49.40 Hz immediately.
- When a feeder group trips, ALL appliances in that feeder (including Essential and Critical) are shed — this emulates the real ADMS which trips whole feeders with no priority awareness.
- Restoration: after 120 s of f ≥ 49.95 Hz, restore all shed loads simultaneously.
- Record a `ControlEvent` for every feeder trip and restoration.

**P2 — PriorityEdgePolicy (Priority-aware, the main contribution):**
- Implements staged shedding from §6.3 of the framework:
  - S0 Advisory (f ≤ 49.90 Hz for ≥ 10 s): soft actions on Deferrable loads only (throttle — reduce power to 70% rated, do not fully shed).
  - S1 (f ≤ 49.85 Hz for ≥ 5 s): shed all Deferrable loads.
  - S2 (f ≤ 49.60 Hz OR RoCoF ≤ −0.3 Hz/s): shed Deferrable then Essential.
  - S3 (f ≤ 49.40 Hz): shed remaining Essential loads. Critical never shed.
  - O1 Absorb (f ≥ 50.05 Hz for ≥ 30 s): permit Deferrable loads to start (if OFF and enrolled).
- Use a `StageHoldTimer` per building per stage: track how long frequency has been continuously in/above a stage trigger.
- All shed/restore actions generate `ControlEvent` objects.

#### 6B. Restoration policy: `backend/app/control/restoration_policy.py`

```python
class StaggeredRestorationPolicy:
    """
    Implements §6.4 staggered, projection-checked restoration.
    Eligible when f >= 49.95 Hz continuously for T_stable (default 60 s).
    Release order: by waiting time (longest first).
    Delay = base_delay_s + (hash(building_id, incident_id, seed) % window_s).
    Before each release: check projected post-pickup frequency >= 49.90 Hz.
    Any relapse below S1 trigger freezes all pending restoration.
    """
    def tick(
        self,
        grid_state: GridState,
        buildings: list[BuildingTwin],
        incident_id: str,
        seed: int,
        sim_time_s: float,
    ) -> list[ControlEvent]: ...
```

For the projection check: estimate `f_post_pickup = f_current - (appliance_power_pu / (2 * H))`. If `f_post_pickup < 49.90`, skip that appliance this tick.

#### 6C. `backend/app/control/edge_agent.py`

```python
class EdgeAgent:
    building_id: str
    building: BuildingTwin
    policy: BasePolicy
    restoration_policy: StaggeredRestorationPolicy

    def tick(
        self,
        grid_state: GridState,
        sim_time_s: float,
        incident_id: str,
        seed: int,
    ) -> tuple[float, list[ControlEvent]]:
        """
        One agent evaluation cycle.
        Returns: (demand_delta_kw, list of ControlEvents).
        demand_delta_kw is negative for load shed, positive for load add.
        """
        ...
```

#### 6D. Unit tests: `tests/unit/test_policies.py`
1. `UnmanagedPolicy.evaluate()` never sheds any appliance regardless of frequency.
2. `ADMSFeederPolicy` trips entire feeder including Critical appliances at S1 threshold.
3. `PriorityEdgePolicy` at S1 only sheds Deferrable, not Essential or Critical.
4. `PriorityEdgePolicy` at S3 sheds Essential but never Critical.
5. `StaggeredRestorationPolicy` does not restore if f < 49.95 Hz.
6. `StaggeredRestorationPolicy` produces different restoration delays for different `building_id` values (hash-based staggering).
7. Restoration is frozen when frequency relapses below S1 threshold.

### Hard constraints
- The standard policy must NEVER deliberately shed Critical loads — enforced at both the `Appliance` level (Prompt 5) and the `PriorityEdgePolicy` level.
- Stage hold timers must track continuous duration (reset on any frequency recovery above the stage trigger).
- Staggered delay must be deterministic given the same `(building_id, incident_id, seed)` triple.
- Every shed and restore action must generate a `ControlEvent`.

### Exit criteria
- All 7 policy unit tests pass: `pytest tests/unit/test_policies.py -v`.
- Integration: wiring `PriorityEdgePolicy` into `SimulationClock` with 3 buildings and running a 0.15 pu generation loss for 120 s should produce at least 1 `ControlEvent` of type `"shed_deferrable"`.
- `ruff check` zero violations.


---

## PROMPT 7 — In-process message bus with fault injection

### Context
Policies, edge agents, and the simulation clock are wired together. Now replace direct function calls between components with an in-process message bus that can simulate communication faults.

### Task
Implement `backend/app/messaging/in_process_bus.py`.

#### Requirements

```python
class FaultConfig:
    delay_range_s: tuple[float, float] = (0.0, 0.0)   # uniform random delay added to each message
    loss_probability: float = 0.0                       # probability [0,1] a message is dropped
    duplicate_probability: float = 0.0                  # probability a message is delivered twice
    out_of_order: bool = False                          # if True, deliver within a shuffle window

class InProcessBus:
    """
    In-process publish/subscribe bus with optional fault injection.
    Topics mirror the MQTT topic structure for future compatibility:
      rakshak/v1/grid/telemetry
      rakshak/v1/buildings/{building_id}/meter
      rakshak/v1/buildings/{building_id}/commands
      rakshak/v1/buildings/{building_id}/events
    """
    def __init__(self, fault_config: FaultConfig, rng: numpy.random.Generator) -> None: ...

    def subscribe(self, topic: str, handler: Callable[[dict], Awaitable[None]]) -> None: ...
    async def publish(self, topic: str, payload: dict) -> None: ...
    async def flush(self) -> None:
        """Deliver all pending delayed/reordered messages."""
        ...
```

All randomness uses the injected `rng` (seeded from the scenario seed) — no `random` module calls.

Fault injection rules:
- **Loss:** if a message is dropped, it is silently discarded with no delivery.
- **Delay:** message is held in a queue until `sim_time_s + delay` is reached; delivered on next `flush()` call when the time condition is met.
- **Duplicate:** message is enqueued twice with independent delay draws.
- **Out-of-order:** within a configurable shuffle window size, messages on the same topic may arrive in a different order.

Update `EdgeAgent.tick()` to publish commands via the bus instead of calling `Appliance.shed()` directly. The bus then delivers the command to a registered handler on the `BuildingTwin`. This simulates communication latency between edge agents and appliances.

#### Unit tests: `tests/unit/test_message_bus.py`
1. With `loss_probability=1.0`, no messages are delivered.
2. With `loss_probability=0.0`, all messages are delivered exactly once.
3. With `duplicate_probability=1.0`, messages are delivered exactly twice.
4. Delayed messages are not delivered before their scheduled time.
5. Out-of-order flag results in at least one reordering across 20 messages on the same topic.
6. `flush()` delivers all pending messages.
7. Subscribing to a topic receives only messages on that topic, not others.

### Hard constraints
- All random draws use the injected `numpy.random.Generator`.
- The bus must be fully in-process — no network sockets, no threads.
- No silent exceptions: bus errors must propagate or be logged.
- For Experiment E7 (communication faults), fault parameters come from the scenario config — add a `FaultConfig` field to `ScenarioConfig`.

### Exit criteria
- All 7 bus unit tests pass.
- Re-run the closed-loop integration test from Prompt 6 with `loss_probability=0.1` and confirm the simulation still completes without exceptions (just with some missed commands).
- `ruff check` zero violations.

---

## PROMPT 8 — Evaluation engine and experiment metrics

### Context
The full simulation loop (grid → disturbance → clock → agents → policies → bus → appliances) is wired and tested. Now implement the metrics and experiment engine.

### Task
Implement `backend/app/evaluation/metrics.py` and `backend/app/evaluation/experiments.py`.

#### 8A. `backend/app/evaluation/metrics.py`

Implement these metric computations on a completed `SimulationResult`:

```python
def frequency_nadir(telemetry: list[TelemetrySample]) -> float:
    """Minimum frequency_hz across the run."""

def max_rocof(telemetry: list[TelemetrySample]) -> float:
    """Maximum absolute rocof_hz_per_s across the run."""

def recovery_time_s(
    telemetry: list[TelemetrySample],
    recovery_band_hz: float = 49.95,
    stability_duration_s: float = 60.0,
    disturbance_start_s: float = 10.0,
) -> float | None:
    """Time from disturbance_start_s until frequency >= recovery_band_hz
    continuously for stability_duration_s. Returns None if never recovered."""

def critical_energy_not_served_kwh(events: list[ControlEvent]) -> float:
    """Integrate unmet Critical-priority demand over time. 
    Source: ControlEvents with priority='critical' and event_type='shed_*'."""

def shed_latency_s(events: list[ControlEvent], stage: str) -> float | None:
    """Mean time from stage trigger event to first shed command at that stage."""

def rebound_peak_pu(
    telemetry: list[TelemetrySample],
    baseline_demand_pu: float,
    restoration_start_s: float,
) -> float:
    """Peak demand_pu during restoration window above baseline."""

def feeder_trips_count(events: list[ControlEvent]) -> int:
    """Count ControlEvents with event_type='feeder_trip' (P1 policy)."""

def energy_curtailed_by_tier(events: list[ControlEvent]) -> dict[str, float]:
    """Total kWh curtailed per priority tier."""

def jains_fairness_index(curtailments_per_building: dict[str, float]) -> float:
    """Jain's fairness index over cumulative curtailment per building.
    J = (Σxi)² / (n * Σxi²)"""

def over_frequency_excursion_time_s(telemetry: list[TelemetrySample]) -> float:
    """Total seconds where frequency_hz > 50.05 Hz."""

def compute_all_metrics(
    result: SimulationResult,
    scenario: ScenarioConfig,
) -> dict[str, float]:
    """Compute and return all applicable metrics as a flat dict."""
```

#### 8B. `backend/app/evaluation/experiments.py`

```python
class ExperimentRunner:
    """
    Runs the same scenario under multiple policies and multiple seeds.
    Collects and compares metrics across runs.
    """
    async def run_experiment(
        self,
        scenario_config: ScenarioConfig,
        policies: list[BasePolicy],
        n_seeds: int = 30,           # Phase 1: use 3 seeds minimum for dev; 30 for final
        telemetry_sink: Callable,
        event_sink: Callable,
    ) -> ExperimentResult: ...
```

```python
class ExperimentResult:
    experiment_id: UUID
    scenario_name: str
    policy_results: dict[str, list[SimulationResult]]   # policy_name → list of per-seed results
    summary: dict[str, PolicySummary]

class PolicySummary:
    policy_name: str
    mean_nadir_hz: float
    std_nadir_hz: float
    ci95_nadir: tuple[float, float]
    mean_recovery_time_s: float | None
    mean_critical_ens_kwh: float
    mean_feeder_trips: float
    mean_rebound_peak_pu: float
```

`ExperimentRunner` should iterate: for each seed, create a new `SimulationClock` with fresh building twins and run the simulation. Use the same disturbance scenario but vary the seed for stochastic parameters (e.g., fault injection).

#### 8C. Unit tests: `tests/unit/test_metrics.py`
1. `frequency_nadir` returns the correct minimum from a known telemetry list.
2. `jains_fairness_index` returns 1.0 for equal curtailments, < 1.0 for unequal.
3. `critical_energy_not_served_kwh` returns 0 when no critical shed events exist.
4. `recovery_time_s` returns `None` when frequency never recovers.
5. `energy_curtailed_by_tier` correctly separates events by priority.

#### 8D. Experiment E1–E4 scripts
Create `experiments/baseline/run_e1_e4.py` — a script that:
1. Loads `default_scenario.yaml`.
2. Runs `ExperimentRunner` with policies `[P0, P1, P2]` and 3 seeds.
3. Prints a comparison table: policy × metric.
4. Exports results to `experiments/baseline/results_e1_e4.json`.

### Hard constraints
- All metric functions must be pure (take only data, return only values).
- Use paired comparisons: the same seed must be used across all policies in a given trial.
- `jains_fairness_index` must handle the case where all curtailments are zero (return 1.0).
- Export JSON must include the scenario config snapshot, seeds used, and schema_version.

### Exit criteria
- All 5 metric unit tests pass.
- `python experiments/baseline/run_e1_e4.py` completes without errors.
- The output table shows P2 achieving higher nadir than P0 in at least 2 of 3 seeds (expected from physics).
- `ruff check` zero violations.


---

## PROMPT 9 — FastAPI backend: REST endpoints and WebSocket streaming

### Context
The full simulation engine with metrics is complete and tested. Now expose it via a FastAPI backend.

### Task
Implement the REST API and WebSocket layer in `backend/app/api/` and wire everything together in `backend/app/main.py`.

#### 9A. `backend/app/main.py`
- Create a `FastAPI` app instance with title `"GridShield API"`, version `"1.0.0"`, and OpenAPI at `/docs`.
- Configure CORS from `Settings.CORS_ORIGINS`.
- Include routers from `api/scenarios.py`, `api/runs.py`, `api/metrics.py`.
- Add a `/health` endpoint returning `{"status": "ok", "version": "1.0.0"}`.
- On startup: create database tables if they do not exist (use SQLModel `create_all`).
- Use structured JSON logging (via `app/core/logging.py`).

#### 9B. `backend/app/api/scenarios.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/scenarios` | POST | Create a new scenario from `ScenarioConfig`. Persist to DB. Return `scenario_id`. |
| `/api/v1/scenarios/{scenario_id}` | GET | Retrieve scenario config. |
| `/api/v1/scenarios` | GET | List all scenarios (id, name, created_at). |

#### 9C. `backend/app/api/runs.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/runs` | POST | Start a simulation run. Body: `{scenario_id, policy, seed}`. Returns `run_id`. Launches background task. |
| `/api/v1/runs/{run_id}` | GET | Get `RunState` (status, current_time_s, latest_sample). |
| `/api/v1/runs/{run_id}/stop` | POST | Request a controlled stop of an active run. |
| `/api/v1/runs` | GET | List all runs (id, policy, status, scenario_id, seed). |

Background task: launch `SimulationClock.run()` as an `asyncio` task. Telemetry and events are buffered and flushed to the DB in batches (every 500 samples or 2 s, whichever comes first).

#### 9D. `backend/app/api/metrics.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/runs/{run_id}/metrics` | GET | Return all `RunMetric` rows for the run. |
| `/api/v1/runs/{run_id}/events` | GET | Return all `ControlEvent` rows. Supports `?event_type=` filter. |
| `/api/v1/runs/{run_id}/telemetry` | GET | Return telemetry. Supports `?downsample=N` (return every Nth sample). |

#### 9E. `backend/app/api/websocket.py`

WebSocket endpoint: `WS /api/v1/runs/{run_id}/stream`

- On connection: stream `TelemetrySample` JSON every `WS_PUSH_INTERVAL_S`.
- Include `sequence_number` for client-side gap detection.
- Handle disconnection gracefully; do not crash the simulation if a client disconnects.
- Support multiple simultaneous clients per run.

#### 9F. Integration tests: `tests/integration/test_api.py`
Use `httpx.AsyncClient` with the FastAPI test client:
1. POST a scenario → GET the same scenario → assert config matches.
2. POST a run → GET run status → assert status is "running" or "completed".
3. GET metrics after run completes → assert `"frequency_nadir"` key exists.
4. GET events after run → assert at least one event exists.
5. WebSocket: connect to stream, receive at least 5 samples, assert `sequence_number` increments.

### Hard constraints
- Telemetry must be written to the DB in batches, not one row per step (performance).
- WebSocket clients must not block the simulation loop.
- All REST responses use typed Pydantic response models.
- Publish OpenAPI schema via `/docs` (automatic with FastAPI).
- Never expose raw database IDs as sequential integers in public-facing endpoints; use UUID.

### Exit criteria
- `pytest tests/integration/test_api.py -v` — all 5 tests pass.
- `curl http://localhost:8000/health` returns `{"status": "ok", "version": "1.0.0"}`.
- `curl http://localhost:8000/docs` returns the OpenAPI JSON.
- A full end-to-end run (POST scenario → POST run → wait → GET metrics) completes with no 500 errors.

---

## PROMPT 10 — React dashboard

### Context
The FastAPI backend with WebSocket streaming is running. Now build the frontend.

### Task
Implement the React + TypeScript dashboard in `frontend/src/`.

#### Pages and components to build

**Page 1: Scenario Setup (`/`)**
- Form to fill in scenario parameters (or load from `default_scenario.yaml` via a GET call).
- Policy selector: P0 Unmanaged / P1 ADMS Feeder / P2 Priority Edge.
- Seed input.
- "Start Simulation" button → POST to `/api/v1/runs`.
- Shows validation errors inline.

**Page 2: Live Dashboard (`/runs/:runId`)**
Must display real backend state (no hardcoded values):

1. **Frequency Chart** — real-time line chart (Chart.js) of `frequency_hz` vs `simulation_time_s`. Draw horizontal reference lines at: 50.05 Hz (O1), 50.0 Hz (nominal), 49.90 Hz (S0), 49.85 Hz (S1), 49.60 Hz (S2), 49.40 Hz (S3). Color the chart background by active stage.
2. **Generation vs Demand Chart** — `generation_pu` and `demand_pu` over time on the same axis.
3. **Building Cards** — one card per building showing: building ID, total demand kW, active stage badge, list of appliances with state icons (ON / SHED / WAITING / CRITICAL).
4. **Event Timeline** — scrollable log of `ControlEvent` entries with timestamp, building, appliance, and reason.
5. **Status Bar** — run status, current simulation time, elapsed wall time, current frequency stage.

**Page 3: Experiment Comparison (`/experiments`)**
- Select two or more completed runs.
- Side-by-side comparison table of all metrics.
- Overlay frequency trajectories on one chart.
- Highlight which policy achieved better nadir and recovery time.

**Page 4: Run History (`/history`)**
- Table of all runs: run ID, scenario name, policy, seed, status, nadir, recovery time.
- Click a row to go to the live dashboard for that run.

#### WebSocket hook: `frontend/src/hooks/useSimulationStream.ts`
```typescript
function useSimulationStream(runId: string): {
  latestSample: TelemetrySample | null;
  history: TelemetrySample[];
  connected: boolean;
  error: string | null;
}
```
- Automatically reconnects on disconnect (up to 5 attempts, exponential backoff).
- Detects sequence number gaps and logs a warning.
- Stops accumulating history after 10,000 samples (drop oldest).

#### TypeScript types: `frontend/src/types/`
Define TypeScript interfaces matching all backend Pydantic schemas: `TelemetrySample`, `ControlEvent`, `ScenarioConfig`, `RunState`, `RunMetric`.

### Hard constraints
- The frequency chart must receive values from the WebSocket — never use `setInterval` with fake values.
- Building and appliance states must come from the REST API (poll `/api/v1/runs/{run_id}` every 2 s for state, or add appliance state to the WebSocket stream).
- No hardcoded frequency curves or appliance state sequences for demos.
- The app must be fully accessible: ARIA labels on all interactive elements, keyboard navigable, color is not the only indicator of state (add text labels).
- Tailwind CSS only — no inline styles except for Chart.js canvas sizing.

### Exit criteria
- `npm run build` completes with zero TypeScript errors.
- Open `http://localhost:3000`: Scenario Setup page renders.
- Start a simulation from the UI: frequency chart updates in real time from the WebSocket.
- After run completes: Experiment Comparison page shows metrics for at least one run.
- Building cards show correct appliance states (manually verify with a known scenario).


---

## PROMPT 11 — Indian synthetic load profiles

### Context
The dashboard and backend are functional. Now add realistic Indian appliance profiles so scenarios reflect Indian homes rather than generic or UK loads.

### Task
Create `backend/app/twin/indian_load_profiles.py` and populate the scenario YAML library.

#### 11A. `backend/app/twin/indian_load_profiles.py`

Define a `LoadProfile` dataclass:
```python
class LoadProfile:
    appliance_type: str
    rated_power_kw: float
    typical_on_hours_per_day: float     # average hours on per day
    duty_cycle: float                   # fraction of on-time drawing rated power
    min_on_time_s: float
    min_off_time_s: float
    max_shed_minutes: float | None
    priority_default: Literal["critical","essential","deferrable"]
    comfort_constraint_notes: str       # human-readable
```

Define these Indian appliance profiles (based on typical Indian residential loads):

| Appliance | Rated power | Priority default | Max shed | Notes |
|-----------|-------------|-----------------|----------|-------|
| split_ac_1ton | 1.0 kW | deferrable | 30 min | Compressor cycling; comfort limit 30 min shed |
| split_ac_1_5ton | 1.5 kW | deferrable | 30 min | |
| geyser_15l | 2.0 kW | deferrable | 60 min | Water stays hot 60 min |
| ev_charger_2wheeler | 0.75 kW | deferrable | None | Can defer overnight |
| ev_charger_car | 3.3 kW | deferrable | None | Can defer overnight |
| ceiling_fan | 0.075 kW | essential | 15 min | |
| water_pump | 0.75 kW | essential | 20 min | Sump tank provides buffer |
| refrigerator | 0.15 kW | essential | 15 min | Food safety limit |
| medical_device | 0.5 kW | critical | None | Never shed |
| inverter_backed_load | 0.3 kW | critical | None | Has battery backup |
| lighting_led | 0.04 kW | essential | 10 min | |

Implement `generate_building_config(building_id: str, weight_k: int, seed: int) -> BuildingConfig` that randomly assigns a realistic mix of Indian appliances to a building using the profiles above, seeded for reproducibility.

#### 11B. Scenario YAML files
Create three additional scenario files in `data/scenarios/`:

**`solar_surplus_scenario.yaml`** — Over-frequency event:
- `disturbance.type: "solar_surplus"`, `magnitude_pu: -0.12`, `start_time_s: 5.0`, `duration_s: 120.0`
- 5 buildings with EV chargers and water heaters (absorb candidates)
- Tests N3 (two-sided response, O1 absorb stage)

**`severe_generation_loss.yaml`** — Stress test:
- `disturbance.type: "generation_loss"`, `magnitude_pu: 0.25`, `duration_s: 600.0`
- 10 buildings, mixed load
- Tests S2 and S3 stages and feeder trip avoidance

**`communication_fault_scenario.yaml`** — Reliability test:
- Same as `default_scenario.yaml` but with `fault_config: {loss_probability: 0.15, delay_range_s: [0.1, 2.0]}`
- Tests Experiment E7

### Hard constraints
- `generate_building_config` must be fully reproducible given the same seed.
- Profiles must be backed by comments citing approximate real-world values (links not required, just BIS/EESL references).
- REFIT data is NOT used in this prompt — these are entirely synthetic Indian profiles.

### Exit criteria
- `python -c "from app.twin.indian_load_profiles import generate_building_config; c = generate_building_config('B1', 1, 42); print(len(c.appliances))"` prints a number between 4 and 8.
- All three new YAML files load successfully through `ScenarioConfig` validation.
- Running `default_scenario.yaml` with `generate_building_config` profiles produces at least one S1-stage ControlEvent with `generation_loss 0.15 pu`.

---

## PROMPT 12 — Participation frontier (N2) and sensitivity analysis (E5–E6)

### Context
The full system is functional. Now implement the two key analytical results that support the novel contribution claims.

### Task
Implement the participation frontier experiment and the sensitivity analysis suite.

#### 12A. Participation frontier (N2): `backend/app/evaluation/participation_frontier.py`

```python
def compute_participation_frontier(
    base_scenario: ScenarioConfig,
    participation_levels: list[float],   # e.g., [0.2, 0.4, 0.6, 0.8, 1.0]
    n_seeds: int = 10,
    protection_criteria: dict,           # e.g., {"critical_ens_kwh": 0.0, "feeder_trips": 0}
) -> ParticipationFrontierResult:
    """
    For each participation level p, mark a fraction p of buildings as enrolled.
    Run the simulation under P2 policy.
    Find p* = minimum p such that protection_criteria are met in ≥ 90% of seeds.
    Returns the full frontier data and p*.
    """
```

```python
class ParticipationFrontierResult:
    participation_levels: list[float]
    metrics_by_level: dict[float, PolicySummary]
    p_star: float | None    # None if criteria never met even at p=1.0
    criteria: dict
```

`participation_levels` controls enrollment: at level 0.2, only 20% of buildings (chosen by sorted building_id, deterministic) have `enrolled=True` on their appliances.

#### 12B. Sensitivity analysis: `experiments/sensitivity_analysis/run_e5.py`

Script that sweeps these parameters, one at a time, holding others at default:
- `H`: [3.0, 4.0, 5.0, 6.0]
- `D`: [1.0, 1.5, 2.0]
- `disturbance.magnitude_pu`: [0.05, 0.10, 0.15, 0.20, 0.25]
- `R (droop)`: [0.03, 0.05, 0.07]

For each parameter value: run P0 and P2 with 3 seeds. Collect `frequency_nadir` and `recovery_time_s`. Export a CSV per sweep to `experiments/sensitivity_analysis/`.

#### 12C. Scalability experiment: `experiments/sensitivity_analysis/run_e6.py`

Script that varies the number of buildings: [3, 5, 10, 20, 50]. For each count, use `generate_building_config` to create buildings, run P2 with 3 seeds. Record: frequency nadir, total simulation time (wall clock), and memory usage (via `tracemalloc`). Export CSV.

#### 12D. Frontier and sensitivity unit tests: `tests/unit/test_frontier.py`
1. At `participation_level=0.0`, no enrolled appliances → metrics equal P0 (unmanaged).
2. At `participation_level=1.0`, all buildings enrolled → metrics equal standard P2 run.
3. `p_star` is always between 0.0 and 1.0 (or None).
4. Sensitivity sweep produces `len(H_values) + len(D_values) + ...` result rows.

### Hard constraints
- Enrollment selection must be deterministic (sorted building_id, not random).
- All scripts must be runnable standalone: `python experiments/sensitivity_analysis/run_e5.py`.
- Export CSVs must include a header row and a `scenario_config_hash` column for traceability.

### Exit criteria
- `python -c "from app.evaluation.participation_frontier import compute_participation_frontier"` succeeds.
- `python experiments/sensitivity_analysis/run_e5.py` completes and produces CSV files.
- `python experiments/sensitivity_analysis/run_e6.py` completes; wall-clock time for 50 buildings is recorded.
- All 4 frontier unit tests pass.


---

## PROMPT 13 — Docker, CI, and final integration

### Context
All simulation, API, and dashboard components are implemented. Now containerise everything and set up CI.

### Task
Finalize `docker-compose.yml`, add GitHub Actions CI, and run the full integration smoke test.

#### 13A. `docker-compose.yml` (final)

Define four services:
1. `postgres` — `postgres:16-alpine`, health check via `pg_isready`, credentials from `.env`.
2. `backend` — builds from `./backend`, port 8000, depends on `postgres` (health), environment from `.env`, mounts `./data` read-only.
3. `frontend` — builds from `./frontend`, port 3000, depends on `backend`.
4. `test-runner` (profile `test`) — runs `pytest` inside the backend image; exits 0 on success.

#### 13B. `backend/Dockerfile`
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### 13C. `frontend/Dockerfile`
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```

#### 13D. `.github/workflows/ci.yml`
GitHub Actions workflow triggered on `push` and `pull_request` to `main`:

```yaml
jobs:
  backend-test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_DB: gridshield_test, POSTGRES_USER: gs, POSTGRES_PASSWORD: gs }
        ports: ["5432:5432"]
        options: --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
        working-directory: backend
      - run: ruff check app/
        working-directory: backend
      - run: pytest tests/ -v --tb=short
        working-directory: backend
        env: { DATABASE_URL: "postgresql+asyncpg://gs:gs@localhost:5432/gridshield_test" }

  frontend-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
        working-directory: frontend
      - run: npm run build
        working-directory: frontend
```

#### 13E. Final integration smoke test: `tests/scenarios/test_full_e1_e4.py`

End-to-end test that:
1. Starts the FastAPI app with a test database.
2. POSTs the `default_scenario.yaml` as a new scenario.
3. Runs all three policies (P0, P1, P2) in sequence with `seed=42`.
4. Waits for each run to complete (poll every 500 ms, timeout 120 s).
5. Fetches metrics for each run.
6. Asserts:
   - P2 `frequency_nadir` > P0 `frequency_nadir` (priority control improves nadir).
   - P2 `critical_energy_not_served_kwh` == 0.0 (standard policy never sheds Critical).
   - P1 `feeder_trips_count` > 0 (ADMS emulator does trip feeders).
   - P2 `feeder_trips_count` == 0 (edge control avoids feeder trips).
   - All runs have `status == "completed"`.

### Hard constraints
- Dockerfiles must use exact version pins (no `:latest` tags except postgres:16-alpine which is acceptable).
- CI must run in under 10 minutes on a standard GitHub Actions runner.
- The smoke test must not use `time.sleep` inside assertions — use polling with timeout.
- `docker compose up` must bring up the whole stack from a clean state without manual steps.

### Exit criteria
- `docker compose up --build` starts all services; `docker compose run test-runner` exits 0.
- GitHub Actions CI passes on a clean push to main.
- All 5 assertions in `test_full_e1_e4.py` pass.
- `curl http://localhost:8000/health` returns 200 from inside Docker network.

---

## PROMPT 14 — Documentation and claim boundaries

### Context
All code is implemented, tested, and containerised.

### Task
Write the final documentation files. These must accurately reflect the implemented system and its limitations.

#### 14A. `docs/architecture.md`
Document the full system architecture with:
- System overview and the two modes (scaled area / islanded microgrid).
- Component diagram (Mermaid flowchart matching §6.6 of framework.md).
- Data flow description: disturbance → frequency → agents → appliances → demand delta → frequency.
- Policy descriptions: P0, P1, P2, staggered restoration.
- API layer: REST endpoints table and WebSocket stream format.
- Database schema summary.

#### 14B. `docs/assumptions.md` (complete the stub from Prompt 1)
Fill in the assumptions table with actual values used in the implementation. For each parameter, state:
- The value implemented.
- The source or justification (cite from framework.md §7 and §4).
- Whether it was swept in sensitivity analysis (link to E5).
- Any known limitation.

#### 14C. `docs/experiment_protocol.md`
For each experiment E1–E6 implemented in Phase 1:
- Hypothesis being tested.
- Scenario(s) used.
- Policies compared.
- Metrics reported.
- Number of seeds.
- Location of results files.

#### 14D. `docs/data_dictionary.md`
Document every field in:
- All database tables (name, type, unit, description, example value).
- All WebSocket telemetry fields.
- All ControlEvent fields.
- The `SimulationResult` and `ExperimentResult` JSON export.

#### 14E. `README.md` (final version)
Replace the stub with a complete README:
1. Project name and subtitle.
2. One-paragraph abstract matching the claim wording from framework.md §5.3.
3. Architecture diagram (embed the Mermaid chart).
4. Quick start: `git clone`, `docker compose up`, open `http://localhost:3000`.
5. Running experiments: `docker compose run test-runner python experiments/baseline/run_e1_e4.py`.
6. Claim boundaries section — verbatim from framework.md §11 (what you may and may not claim).
7. Known limitations section.
8. Sources and acknowledgements.

### Hard constraints
- The README abstract must use the claim wording from framework.md §5.3 exactly: *"We present an open, reproducible, Karnataka-calibrated digital twin that benchmarks appliance-level priority-aware demand response against Southern-Region-style feeder tripping, quantifies the participation needed for critical-load protection, and evaluates two-sided (under- and over-frequency) response."*
- Do NOT write "first", "novel algorithm", or "guarantees blackout-free" anywhere in the documentation.
- Use "blackout-risk reduction" not "blackout-free" in all documentation.
- Every cited source from framework.md §13 must appear in the README sources section with its URL and checked date.

### Exit criteria
- `docs/assumptions.md` has no TBD values — all are filled in.
- `README.md` contains the exact abstract from framework.md §5.3.
- `docs/experiment_protocol.md` covers all 6 experiments (E1–E6).
- A peer (human reviewer) can follow the README and reproduce results from scratch.

---

## Phase 1 completion checklist

Before declaring Phase 1 done, verify every item:

- [ ] `docker compose up --build` starts all services without errors.
- [ ] `pytest tests/` — all unit and integration tests pass (zero failures, zero errors).
- [ ] `ruff check backend/app/` — zero violations.
- [ ] `npm run build` — zero TypeScript errors.
- [ ] GitHub Actions CI passes on main branch.
- [ ] Smoke test `test_full_e1_e4.py` — all 5 assertions pass.
- [ ] P2 `critical_energy_not_served_kwh` == 0.0 across all seeds.
- [ ] P1 emulates feeder trips including Critical loads (as intended).
- [ ] P2 frequency nadir > P0 nadir in E3 results.
- [ ] Participation frontier p* is computed and exported.
- [ ] All three scenario YAML files (default, solar surplus, severe loss) run without errors.
- [ ] Dashboard receives real WebSocket data (verified by observing frequency chart update).
- [ ] `docs/assumptions.md` has no TBD values.
- [ ] README contains the exact claim wording from framework.md §5.3.
- [ ] No occurrences of "guarantees blackout-free" or "novel algorithm" in any document.
- [ ] `data/raw/` is in `.gitignore` and not committed.
- [ ] Every `ControlEvent` has a non-empty `reason` field.
- [ ] `SimulationRun` records include `config_snapshot_json` (reproducibility requirement).

---

## Appendix: droppable modules (do not implement in Phase 1)

The following are explicitly deferred. Do not implement them unless Phase 1 is fully complete and the team has remaining time:

- **NILM (Non-Intrusive Load Monitoring):** REFIT data replay, event detection, sklearn classifier. The stub files (`nilm/`) exist but are empty.
- **MQTT / Mosquitto broker:** The `in_process_bus.py` is the complete messaging solution for Phase 1. MQTT is a stretch goal.
- **Equity/fairness module (N4):** Jain's index metric is implemented in `metrics.py` but the full credit-weighted rotation policy is a Phase 2 extension.
- **Prometheus/Grafana monitoring:** Not needed for research deliverable.
- **ANDES / pandapower integration:** The reduced-order model is sufficient for Phase 1 claims.

---

*Document generated: 27 Oct 2026. Derived from framework.md and Project_Rakshak_Knowledge_Transfer.md.*
