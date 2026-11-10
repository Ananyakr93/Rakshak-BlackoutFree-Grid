# GridShield — Data Dictionary

## TelemetrySample fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| run_id | UUID | — | Parent simulation run |
| simulation_time_s | float | s | Simulation clock time |
| wall_clock_ts | datetime (UTC) | — | Wall clock at sample creation |
| frequency_hz | float | Hz | Current grid frequency |
| generation_pu | float | pu | Total generation per-unit |
| demand_pu | float | pu | Total demand per-unit |
| generation_disturbance_pu | float | pu | Signed exogenous generation change; positive adds generation, negative removes it |
| demand_disturbance_pu | float | pu | Signed exogenous demand change; positive increases demand |
| frequency_stage | str | — | One of: normal, s0_advisory, s1, s2, s3, o1_absorb, o2_absorb_plus |
| rocof_hz_per_s | float | Hz/s | Rate of change of frequency |
| sequence_number | int | — | Monotonically increasing per run; gaps indicate dropped samples |
| schema_version | str | — | "1.0" |

`generation_pu` includes baseline generation, governor response, and the signed
generation disturbance. `demand_pu` includes baseline demand, appliance demand
changes, and the signed demand disturbance. The component fields default to
zero when reading telemetry written before the component schema was introduced.

## Run metrics

| Metric | Unit | Description |
|--------|------|-------------|
| medical_load_interruption_s | device-s | Interruption duration summed across configured `medical_device` appliances; not patient-minutes |
| critical_ens_kwh | kWh | Estimated critical-priority energy not served |

Backup generators, UPS runtime, and clinical service continuity are not modeled.

## ControlEvent fields

| Field | Type | Unit | Description |
|-------|------|------|-------------|
| event_id | UUID | — | Unique event identifier |
| run_id | UUID | — | Parent run |
| simulation_time_s | float | s | Simulation time when event occurred |
| wall_clock_ts | datetime (UTC) | — | Wall clock time |
| event_type | str | — | e.g. shed_deferrable, shed_essential, restore, feeder_trip, no_op |
| building_id | str | — | Target building |
| appliance_id | str or null | — | Target appliance (null for feeder events) |
| reason | str | — | Human-readable decision reason (must be non-empty) |
| frequency_hz | float | Hz | Frequency at time of decision |
| priority | str or null | — | critical / essential / deferrable |
| schema_version | str | — | "1.0" |
