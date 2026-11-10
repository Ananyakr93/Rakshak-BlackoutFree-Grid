# Project Rakshak: Knowledge Transfer Document

## Software-Only Grid Digital Twin

**Project title:** Edge-Intelligent Grid Resilience for Blackout-Free
Smart Cities\
**Implementation mode:** Software-only, no physical hardware\
**Primary objective:** Build a simulation-based digital twin that models
grid-frequency disturbances and evaluates priority-aware load shedding
and staggered restoration.\
**Technology principle:** Use free and open-source tools that can run
locally.

------------------------------------------------------------------------

## 1. Purpose of This Document

This document transfers the project vision, architecture, implementation
plan, technology choices, engineering constraints, and evaluation
approach to any team member who needs to implement, review, or continue
the project.

It is based on the team's original synopsis and the software-only
implementation direction agreed for the project. The physical ESP32,
INA219 sensor, relay modules, and proxy loads are replaced with software
models.

## 2. Project Overview

Project Rakshak models a neighbourhood electricity system in software.
The system injects disturbances such as a drop in solar generation or a
sudden increase in demand, calculates the resulting grid-frequency
response, and lets virtual building-level controllers decide whether to
shed eligible loads.

Each building contains virtual appliances grouped into three priority
tiers:

1.  **Critical:** Loads that the standard policy must not deliberately
    shed.
2.  **Essential:** Loads that may be shed only under a more severe
    event, according to configurable policy.
3.  **Deferrable:** Flexible loads that are shed first and restored
    last.

The digital twin updates appliance states and aggregate demand when
control actions occur. These changes feed back into the grid model, so
frequency recovery is a result of the simulated system dynamics rather
than a visual animation.

### What the project is

-   A simulation-based grid digital twin.
-   A closed-loop software model of disturbance, control, shedding, and
    restoration.
-   A platform for repeatable experiments and policy comparisons.
-   A way to investigate the behaviour of virtual edge agents under
    different assumptions.

### What the project is not

-   It is not a physical hardware-in-the-loop prototype.
-   It is not a live, continuously synchronised digital twin of an
    operating utility grid.
-   It is not a certified protection relay or a deployment-ready
    blackout-prevention system.
-   Its results do not prove real-world grid performance unless the
    models and assumptions are validated against suitable real-system
    evidence.

Use these boundaries consistently in the report, demo, and presentation.

------------------------------------------------------------------------

## 3. Project Goals

The software system should:

1.  Simulate a grid around a nominal frequency of 50 Hz.
2.  Inject reproducible generation and demand disturbances.
3.  Represent buildings and appliances as virtual entities with explicit
    states and priorities.
4.  Implement independent virtual edge agents that make local control
    decisions.
5.  Shed eligible low-priority loads when configured trigger conditions
    are met.
6.  Restore loads gradually after the frequency meets a defined
    stability condition.
7.  Stream the simulation state to a live dashboard.
8.  persist scenarios, telemetry, decisions, and metrics.
9.  Compare unmanaged, feeder-level, and priority-aware control
    policies.
10. Produce repeatable evaluation results with documented assumptions
    and limitations.

## 4. System Architecture

``` mermaid
flowchart TD
    A["Scenario Engine: solar drop or demand surge"] --> B["Grid Digital Twin: generation, demand, frequency"]
    B --> C["Virtual Metering: synthetic and replayed load data"]
    C --> D["Building and Appliance Twins"]
    D --> E["Virtual Edge Agents"]
    E --> F["Priority-Based Shedding"]
    F --> G["Frequency Recovery"]
    G --> H["Staggered Restoration"]
    H --> I["Metrics and Experiment Comparison"]
    I --> B
```

### Main layers

**1. Scenario layer** - Defines the initial state and disturbance
profile. - Controls event start time, magnitude, duration, and recovery
conditions. - Uses a random seed where stochastic behaviour is involved.

**2. Grid model** - Calculates frequency dynamics from the
generation-demand imbalance. - Receives load changes resulting from
appliance switching. - Exposes the current frequency and other modelled
variables.

**3. Building and appliance twins** - Store building identity, appliance
profiles, power demand, priority, and current state. - Update aggregate
building demand when an appliance changes state. - Enforce allowed state
transitions and switching constraints.

**4. Virtual metering and NILM** - Produces aggregate load readings from
appliance states or replays public load data. - Detects candidate
appliance events. - Optionally classifies events using a
machine-learning model.

**5. Virtual edge agents** - Receive the measurements relevant to their
building. - Evaluate the configured policy. - Issue local shedding and
restoration commands. - Record the reason for each decision.

**6. Evaluation engine** - Calculates grid, service, controller, and
NILM metrics. - Compares policies under identical scenario conditions.

**7. API and dashboard** - Exposes scenario and run management. -
Streams current simulation state. - Displays grid frequency, buildings,
appliance states, control events, and results.

**8. Persistence and observability** - Saves configurations, telemetry,
decisions, and metrics. - Records errors, processing latency, and run
status.

------------------------------------------------------------------------

## 5. Recommended Open-Source Technology Stack

All components should be runnable locally. No paid API or cloud hosting
is required.

  -----------------------------------------------------------------------
  Component               Recommended tool        Role
  ----------------------- ----------------------- -----------------------
  Programming language    Python                  Simulation, control,
                                                  data processing

  Numerical modelling     NumPy, SciPy            Grid equations and
                                                  numerical integration

  Data processing         Pandas                  Load data and
                                                  experiment analysis

  Backend API             FastAPI                 Run management and REST
                                                  endpoints

  Live updates            WebSockets              Stream simulation state
                                                  to the UI

  Frontend                React, TypeScript, Vite Dashboard application

  Styling                 Tailwind CSS            UI styling

  Charts                  Chart.js                Frequency, demand, and
                                                  metric charts

  Database                PostgreSQL              Runs, telemetry,
                                                  events, and metrics

  ORM                     SQLAlchemy or SQLModel  Database access

  Optional message broker Eclipse Mosquitto       MQTT communication
                                                  among virtual agents

  Tests                   pytest                  Unit, integration, and
                                                  scenario tests

  Code quality            Ruff                    Python linting and
                                                  formatting

  Containers              Docker Compose          Reproducible local
                                                  services

  Optional power-system   ANDES                   More detailed dynamic
  simulator                                       simulation

  Optional network        pandapower              Distribution-network
  analysis                                        modelling and power
                                                  flow

  Optional monitoring     Prometheus and Grafana  Runtime metrics and
                                                  visual monitoring

  Optional                OpenTelemetry           Standardised
  instrumentation                                 application telemetry
  -----------------------------------------------------------------------

### Selection guidance

Begin with a custom reduced-order frequency model in Python. Do not
integrate every tool at once.

-   **ANDES** may be introduced later for more detailed time-domain
    power-system dynamic studies.
-   **pandapower** may be introduced when the project needs buses,
    feeders, line loading, or power-flow studies. Ordinary power-flow
    calculations do not replace transient frequency simulation.
-   **Mosquitto** is optional for the first working version. Start with
    in-process events, then add MQTT when virtual-agent separation is
    useful.
-   **Prometheus/Grafana** are optional. They are not necessary to
    demonstrate the core research contribution.

Check individual project licences and version compatibility when
preparing the final repository.

------------------------------------------------------------------------

## 6. Grid Dynamics Model

The initial model can use a simplified swing-equation-style
relationship:

\[ `\frac{d\Delta f}{dt}`{=tex} = `\frac{f_0}{2H}`{=tex}
`\left`{=tex}(`\Delta `{=tex}P_m-`\Delta `{=tex}P_e-D`\Delta `{=tex}f`\right`{=tex})
\]

Where:

-   (f_0): nominal frequency, set to 50 Hz in this model.
-   (`\Delta `{=tex}f): frequency deviation from nominal.
-   (H): equivalent inertia constant.
-   (`\Delta `{=tex}P_m): change in mechanical or equivalent generation.
-   (`\Delta `{=tex}P_e): change in electrical demand.
-   (D): frequency-dependent damping.

The power quantities must use a consistent per-unit base, and the
parameter values must be documented. This equation is a starting point,
not a complete model of a real grid.

### Important modelling requirement

Add a simplified generation-governor or primary-frequency-response model
if required by the chosen experiment. The grid should not automatically
reset frequency to 50 Hz. Its response must emerge from the implemented
dynamics, generation response, disturbance, and load changes.

### Initial disturbance scenarios

-   Sudden reduction in solar generation.
-   Sudden demand surge.
-   Combined generation reduction and demand surge.
-   Disturbance of different magnitudes and durations.
-   Different equivalent inertia and damping assumptions.

Use configurable scenario files rather than hardcoding scenario values
in the simulator.

### Numerical validation

Before adding the dashboard:

1.  Test the model with no disturbance.
2.  Test the direction of frequency response after a generation loss.
3.  Test the direction of response after a demand reduction.
4.  Check that shedding demand affects the frequency trajectory.
5.  Test different integration time steps for numerical convergence.
6.  Record model assumptions and known limitations.

An initial integration step such as 10--20 milliseconds can be explored
for the reduced-order model, but the final step must be justified by
numerical and runtime testing. Dashboard refresh rate should be slower
than or independent of the numerical integration step.

------------------------------------------------------------------------

## 7. Building and Appliance Digital Twins

Each building should have a stable ID, an associated feeder or grid
connection, a local load profile, and a collection of appliances.

### Example priority categories

  -----------------------------------------------------------------------
  Tier                    Example loads           Default policy
  ----------------------- ----------------------- -----------------------
  Critical                Medical or life-support Do not deliberately
                          equipment, designated   shed under the standard
                          critical lighting,      policy
                          designated              
                          refrigeration           

  Essential               Fans and other          Shed only when the
                          configurable household  configured severity
                          loads                   rule permits

  Deferrable              EV charging, air        Shed first and restore
                          conditioning, water     last
                          heating                 
  -----------------------------------------------------------------------

These categories are illustrative. Actual criticality depends on context
and should not be treated as a universal classification of every device
of that type.

### Appliance state machine

``` text
OFF
  |
  v
ON
  |
  v
SHED
  |
  v
WAITING_FOR_RESTORATION
  |
  v
ON
```

The implementation may require additional states for unavailable
devices, invalid measurements, lockout intervals, or failed commands.

Every appliance should define: - `appliance_id` - `building_id` -
appliance type - priority tier - rated or configured power - current
state - permitted state transitions - minimum on/off times where
relevant - whether the appliance is eligible for shedding - restoration
eligibility and constraints

A state change must update the actual simulated power demand. Changing a
dashboard colour alone is not a valid simulation response.

------------------------------------------------------------------------

## 8. Virtual Edge-Agent Control

Each building receives a virtual edge agent that evaluates its
measurements and makes a local decision.

### Shedding flow

1.  Receive the latest valid frequency and local load information.
2.  Check measurement freshness and validity.
3.  Check whether the configured shedding condition is met.
4.  Identify eligible appliances.
5.  Select appliances according to priority and policy.
6.  Issue virtual switching commands.
7.  Update appliance and aggregate demand states.
8.  Record the decision, reason, and latency.

### Restoration flow

1.  Continue monitoring the modelled frequency.
2.  Check that frequency is within the configured recovery band.
3.  Require the configured stability duration to be satisfied.
4.  Select an eligible shed appliance.
5.  Compute a deterministic delay based on a stable virtual building ID,
    incident ID, and experiment seed.
6.  Reconnect the appliance when permitted.
7.  Check the updated demand and frequency before continuing
    restoration.

The original synopsis specifies 49.6 Hz as the shedding threshold and
50.0 Hz as the restoration threshold. Keep these as configurable
experimental parameters, not certified utility protection settings. Add
hysteresis, stability-duration checks, and switching constraints to
avoid rapid on/off cycling.

### Failure behaviour

Define explicit behaviour for: - missing or stale frequency data; -
unknown appliance identity; - failed or duplicated commands; -
unavailable agents; - messages arriving out of order; - restoration
conditions that become unsafe again.

The normal priority policy must not deliberately shed critical loads.
The model should also distinguish this policy guarantee from a guarantee
that critical loads can always be served under every possible generation
shortage.

------------------------------------------------------------------------

## 9. NILM: Non-Intrusive Load Monitoring

The original idea identifies appliance events from aggregate power
rather than a separate sensor on every appliance. In the software-only
system, use public load data and a synthetic high-resolution test
harness.

### Data sources

**Empirical data:** The REFIT Electrical Load Measurements dataset
contains aggregate and appliance-level measurements from 20 homes at
eight-second intervals and is available under CC BY 4.0. Verify the
dataset's current access instructions and licence before redistribution.

**Synthetic data:** Generate configurable appliance activation,
power-step, and inrush-like waveforms. Add noise, overlapping events,
and varying load profiles.

Important limitation: eight-second REFIT samples are not sufficient to
validate detailed subsecond inrush signatures. Keep empirical evaluation
and synthetic high-resolution evaluation separate. Synthetic results do
not prove real-world appliance-recognition accuracy.

### Implementation sequence

1.  Generate aggregate power by combining appliance profiles.
2.  Detect candidate changes using a configurable difference/window
    rule.
3.  Extract features such as event magnitude, duration, and steady-state
    power.
4.  Add waveform-derived features only to the appropriate
    high-resolution synthetic experiment.
5.  Establish a rule-based baseline.
6.  Train a baseline classifier, such as a scikit-learn Random Forest,
    using labelled events.
7.  Evaluate on held-out homes, sessions, or scenarios where the data
    permits.
8.  Return an `unknown` result when confidence is insufficient.

### Metrics

-   Event detection precision and recall.
-   Appliance-classification macro-F1.
-   Confusion matrix.
-   Missed and false events.
-   Unknown-event rate.
-   Performance by appliance type and scenario.

The controller must not blindly shed an unidentified load. A safe
fallback should be defined independently of the classifier.

------------------------------------------------------------------------

## 10. Backend, API, and Real-Time Updates

Use FastAPI for experiment management and WebSockets for live updates.

### Suggested endpoints

  Endpoint                              Purpose
  ------------------------------------- ----------------------------------
  `POST /api/v1/scenarios`              Create a scenario
  `POST /api/v1/runs`                   Start a simulation run
  `GET /api/v1/runs/{run_id}`           Get run status and current state
  `POST /api/v1/runs/{run_id}/stop`     Request a controlled stop
  `GET /api/v1/runs/{run_id}/metrics`   Retrieve metrics
  `GET /api/v1/runs/{run_id}/events`    Retrieve control events
  `WS /api/v1/runs/{run_id}/stream`     Stream live simulation updates

Use typed request/response schemas and publish the REST interface
through OpenAPI. Version endpoints and message schemas.

### Suggested telemetry fields

-   `simulation_id`
-   `simulation_time_s`
-   `wall_clock_timestamp`
-   `frequency_hz`
-   `generation_kw`
-   `demand_kw`
-   `building_id`
-   `appliance_id`
-   `appliance_state`
-   `event_type`
-   `sequence_number`
-   `schema_version`

Only include fields applicable to a particular message. Document units
and distinguish model-estimated, synthetic, and empirical data.

### MQTT option

When independent virtual agents are required, use a local Mosquitto
broker and topics such as:

``` text
rakshak/v1/grid/telemetry
rakshak/v1/buildings/{building_id}/meter
rakshak/v1/buildings/{building_id}/events
rakshak/v1/buildings/{building_id}/commands
```

Start with an in-process event bus to reduce initial complexity. Add
MQTT after the control loop works.

------------------------------------------------------------------------

## 11. Dashboard Requirements

The React + TypeScript dashboard should show the actual internal state
of the simulation.

### Main views

1.  **Grid overview:** frequency, generation, demand, disturbance
    status, and frequency nadir.
2.  **Building map or topology view:** virtual buildings, feeder
    relationships, and agent status.
3.  **Appliance panel:** priority tier, current state, power demand, and
    recent commands.
4.  **Scenario controls:** disturbance type, magnitude, duration, model
    parameters, and policy selection.
5.  **Event timeline:** disturbance onset, threshold crossing, shedding
    commands, state changes, and restoration.
6.  **Experiment comparison:** frequency trajectories, recovery time,
    rebound peak, and critical energy not served.
7.  **Run history:** run ID, configuration, seed, status, and results.

The frontend must receive its values from the backend. Do not hardcode a
frequency curve or appliance changes for a demonstration.

------------------------------------------------------------------------

## 12. Database Design

Use PostgreSQL to preserve repeatability and auditability.

  -----------------------------------------------------------------------
  Table                               Example content
  ----------------------------------- -----------------------------------
  `grid_assets`                       Generators, buses, feeders, and
                                      grid parameters

  `buildings`                         Building IDs, feeder associations,
                                      and local settings

  `appliances`                        Type, priority, power, state, and
                                      constraints

  `scenarios`                         Disturbance settings and model
                                      parameters

  `simulation_runs`                   Run ID, seed, configuration
                                      version, status, and timestamps

  `telemetry_samples`                 Time-series frequency, generation,
                                      demand, and building power

  `control_events`                    Trigger, decision, target
                                      appliance, reason, and state
                                      transition

  `run_metrics`                       Nadir, recovery time, energy not
                                      served, rebound peak, and
                                      classification results
  -----------------------------------------------------------------------

Store the scenario configuration and model version with every run. Keep
simulation time separate from wall-clock timestamps. Use explicit units
in field names or the data dictionary.

Large raw datasets should not be committed to Git. Document data source,
licence, acquisition steps, and preprocessing.

------------------------------------------------------------------------

## 13. Repository Structure

``` text
rakshak-digital-twin/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── scenarios.py
│   │   │   ├── runs.py
│   │   │   ├── metrics.py
│   │   │   └── websocket.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   └── logging.py
│   │   ├── twin/
│   │   │   ├── grid_model.py
│   │   │   ├── simulation_clock.py
│   │   │   ├── disturbances.py
│   │   │   ├── building_twin.py
│   │   │   └── appliance.py
│   │   ├── nilm/
│   │   │   ├── data_generator.py
│   │   │   ├── event_detector.py
│   │   │   ├── features.py
│   │   │   └── classifier.py
│   │   ├── control/
│   │   │   ├── edge_agent.py
│   │   │   ├── shedding_policy.py
│   │   │   └── restoration_policy.py
│   │   ├── evaluation/
│   │   │   ├── metrics.py
│   │   │   └── experiments.py
│   │   ├── messaging/
│   │   │   └── mqtt_adapter.py
│   │   ├── db/
│   │   │   ├── models.py
│   │   │   └── repository.py
│   │   └── schemas/
│   │       ├── scenario.py
│   │       ├── events.py
│   │       └── telemetry.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── scenarios/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── charts/
│   │   ├── api/
│   │   ├── hooks/
│   │   └── types/
│   └── package.json
├── data/
│   ├── raw/
│   ├── processed/
│   └── scenarios/
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

The `mqtt_adapter.py` file can remain a placeholder until MQTT is
introduced. Do not create unused abstractions before the first working
version.

------------------------------------------------------------------------

## 14. Evaluation Protocol

The central experiment compares three policies on the same scenario,
starting state, and random seed.

1.  **Unmanaged:** No automated shedding.
2.  **Feeder-level shedding:** Disconnect a predefined feeder or
    proportion of load.
3.  **Priority-aware shedding:** Shed eligible loads according to the
    tiered policy.

### Metrics

**Frequency nadir**

\[ f\_{`\min`{=tex}} = `\min`{=tex}\_t f(t) \]

**RoCoF:** Estimate (df/dt), reporting the estimation interval and
maximum absolute value.

**Frequency recovery time:** Time from disturbance onset until frequency
enters the defined acceptable band and remains there for the required
stability duration.

**Shedding response latency:** Time from the triggering condition to the
virtual appliance state change. Report configured communication delay
separately from computation latency.

**Critical energy not served:** Integrate unmet critical-load demand
over time and report in kWh. Distinguish intentional shedding from
shortage caused by insufficient simulated generation.

**Restoration rebound peak:** Compare the peak demand during restoration
with baseline demand and with simultaneous reconnection.

**NILM performance:** Report precision, recall, macro-F1, confusion
matrices, false events, missed events, and unknown-event rate.

### Experiment matrix

  -----------------------------------------------------------------------
  Experiment              Change                  Main question
  ----------------------- ----------------------- -----------------------
  E1: Baseline            No control              How severe is the
                                                  disturbance without
                                                  intervention?

  E2: Feeder-level        Predefined feeder/load  What are the service
                          cut                     and frequency
                                                  consequences of blunt
                                                  shedding?

  E3: Priority-aware      Shed eligible           How does priority-aware
                          low-priority loads      control change service
                                                  and frequency outcomes?

  E4: Restoration         Simultaneous versus     Does staggering reduce
                          staggered reconnection  rebound demand?

  E5: Sensitivity         Change inertia,         How sensitive are the
                          disturbance magnitude,  results to model
                          and load mix            assumptions?

  E6: Scalability         Increase buildings and  How does participation
                          participating agents    affect performance and
                                                  computation?
  -----------------------------------------------------------------------

Do not assume priority-aware shedding wins every metric. Report
trade-offs and repeat experiments over multiple scenarios. Use the same
disturbance profiles for fair comparisons.

------------------------------------------------------------------------

## 15. Industry-Style Engineering Practices

### Reproducibility

-   Store a configuration snapshot, random seed, model version, and
    disturbance events per run.
-   Aim for deterministic results within documented numerical
    tolerances.
-   Preserve experiment scripts and raw result exports.

### Testing

-   Unit tests for grid dynamics, state machines, and control policies.
-   Integration tests for disturbance-to-shedding-to-frequency feedback.
-   Scenario regression tests for expected behaviours.
-   API and WebSocket tests.
-   Tests for missing data, duplicate commands, and unavailable agents.

### Fail-safe semantics

-   Reject invalid or stale measurements.
-   Enforce appliance switching constraints.
-   Do not deliberately shed critical loads under the standard policy.
-   Provide an unknown-appliance fallback.
-   Record every control decision and its reason.
-   Do not claim a software policy guarantees critical service under
    every possible supply shortage.

### Versioning and interfaces

-   Version REST endpoints and message schemas.
-   Use consistent units and timestamps.
-   Distinguish simulated, synthetic, empirical, and estimated values.
-   Publish OpenAPI documentation.

### Observability

-   Use structured logs and track simulation throughput, API latency,
    WebSocket delays, errors, and control-decision latency.
-   Add Prometheus/Grafana only if separate runtime monitoring is
    useful.
-   Use Ruff and pytest in automated checks.

### Standards alignment

The project may adopt common engineering practices without claiming
certification or complete conformance to utility standards. OpenAPI
provides API descriptions, MQTT enables message-based communication, and
the IEC Common Information Model can inform future power-system entity
design. A CIM-inspired model is not itself proof of IEC compliance.

------------------------------------------------------------------------

## 16. Implementation Roadmap

### Phase 1: Deterministic grid simulator

Build the frequency model, simulation clock, and disturbance scenarios.

**Exit criteria:** A standalone Python run produces validated frequency,
generation, and demand series.

### Phase 2: Building and appliance twins

Add virtual buildings, appliance profiles, priority tiers, state
machines, and aggregate demand.

**Exit criteria:** Appliance state changes alter the simulated demand.

### Phase 3: Closed-loop control

Add virtual edge agents, shedding, recovery checks, restoration delays,
and event logs.

**Exit criteria:** A disturbance triggers a real simulated state change,
and the changed demand feeds back into the grid model.

### Phase 4: NILM and data replay

Add REFIT data preprocessing, synthetic high-resolution signals, event
detection, and a baseline classifier.

**Exit criteria:** Empirical and synthetic evaluations are reported
separately.

### Phase 5: API and dashboard

Add FastAPI, WebSockets, React dashboard, PostgreSQL persistence, and
run history.

**Exit criteria:** A user can start a scenario, watch the twin respond,
and inspect saved results.

### Phase 6: Reliability and research validation

Add containers, regression tests, performance measurements, optional
MQTT, and the full experiment matrix.

**Exit criteria:** The experiment suite is repeatable from a documented
local setup.

------------------------------------------------------------------------

## 17. Recommended First Milestone

Do not start by implementing the entire architecture.

Build the smallest end-to-end version:

-   One aggregated grid.
-   Three virtual buildings.
-   Three appliance priority categories.
-   One solar-generation-drop scenario.
-   Two policies: unmanaged and priority-aware.
-   One frequency chart.
-   A control-event log.
-   A script that exports experiment metrics.

Defer NILM, MQTT, advanced network simulation, and a complex dashboard
until the closed-loop grid model works. This milestone proves the
central idea and gives the team a stable base for parallel development.

------------------------------------------------------------------------

## 18. Research Extensions

Choose one or two after the core system is validated.

### Fairness-aware load shedding

Measure how curtailment is distributed among buildings while respecting
priority constraints. Jain's fairness index can be explored alongside
energy curtailed and critical-load protection.

### Adaptive restoration

Compare randomized restoration delays with a policy that considers
frequency stability, available demand headroom, and waiting loads.

### Communication-resilient control

Inject delayed, lost, duplicated, or out-of-order messages and evaluate
local control under communication failures.

### Participation-resilience analysis

Vary the percentage of buildings participating in the policy, for
example 20%, 40%, 60%, 80%, and 100%. Measure effects on frequency,
critical service, and curtailment.

These should be evaluated as explicit research hypotheses. Do not claim
novelty solely because the project uses a digital twin, machine
learning, or a dashboard.

------------------------------------------------------------------------

## 19. Knowledge-Transfer Checklist

A new team member should be able to answer these questions before
modifying the system:

-   [ ] Where is the grid-frequency equation implemented?
-   [ ] Which units and per-unit base does the model use?
-   [ ] How does a disturbance alter generation or demand?
-   [ ] How does a virtual appliance state change affect aggregate
    demand?
-   [ ] Which component makes shedding decisions?
-   [ ] How are critical loads protected by the standard policy?
-   [ ] What conditions must hold before restoration?
-   [ ] How is a run reproduced from its configuration and seed?
-   [ ] Where are control events and metrics stored?
-   [ ] Which tests validate the closed-loop response?
-   [ ] Which results are empirical, synthetic, or model-generated?
-   [ ] What are the limitations of the software-only model?

------------------------------------------------------------------------

## 20. Final Design Decision

The recommended core is:

**Python + NumPy/SciPy + FastAPI/WebSockets + React/TypeScript +
PostgreSQL + pytest + Docker Compose.**

Start with a reduced-order grid model and in-process virtual agents. Add
empirical load data and NILM after the feedback loop works. Introduce
MQTT and advanced power-system simulation only when the project has a
concrete need for them.

The central contribution is the measured feedback loop:

**Disturbance → frequency response → local decision → appliance shedding
→ grid response → staggered restoration.**

The final demonstration should show this loop operating from real
backend state, with repeatable experiments and transparent metrics. That
is the heart of Project Rakshak's software-only digital twin.
