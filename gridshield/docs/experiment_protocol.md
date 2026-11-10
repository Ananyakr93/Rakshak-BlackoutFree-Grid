# GridShield — Experiment Protocol

## E1: Unmanaged baseline (P0)
- **Hypothesis:** Without demand-side response, a 15% generation loss causes frequency to fall below 49.60 Hz (S2 territory).
- **Scenario:** default_scenario.yaml
- **Policy:** P0 only
- **Seeds:** 30 (dev: 3)
- **Metrics:** nadir, max RoCoF, recovery_time_s
- **Results:** experiments/baseline/results_e1_e4.json

## E2: ADMS feeder baseline (P1)
- **Hypothesis:** Feeder tripping recovers frequency but sheds critical loads.
- **Scenario:** default_scenario.yaml
- **Policy:** P1
- **Seeds:** 30
- **Metrics:** nadir, feeder_trips_count, critical_ENS_kwh, rebound_peak_pu

## E3: Priority-aware edge control vs baselines (P2 vs P0, P1)
- **Hypothesis:** P2 achieves higher nadir and zero critical ENS vs P0/P1.
- **Scenario:** default_scenario.yaml
- **Policies:** P0, P1, P2 (paired same seeds)
- **Seeds:** 30
- **Metrics:** all

## E4: Staggered vs synchronized restoration
- **Hypothesis:** Staggered restoration limits each pickup; synchronized restoration waits until the whole batch is eligible and its combined startup pickup passes the safety projection.
- **Runner:** `experiments/sensitivity_analysis/run_e7_e8.py`
- **Metrics:** rebound peak, recovery time, raw telemetry and restoration events.

## E5: Sensitivity analysis
- **Parameters swept:** H [3,4,5,6], D [1,1.5,2], magnitude_pu [0.05..0.25], R [0.03,0.05,0.07]
- **Results:** experiments/sensitivity_analysis/

## E6: Participation frontier (p*)
- **Hypothesis:** There exists a minimum participation fraction p* such that critical loads are never shed.
- **Levels:** [0.2, 0.4, 0.6, 0.8, 1.0]
- **Results:** experiments/sensitivity_analysis/participation_frontier.json

## E7: Compressor lockout and cycling constraints
- **Hypothesis:** Compressor-specific restart lockout reduces rapid AC cycling.
- **Baseline/proposed:** ACs with no additional lockout versus 180 s illustrative compressor lockout.
- **Controlled variables:** appliance profiles, policy, frequency thresholds, and paired seeds.
- **Runner:** `experiments/sensitivity_analysis/run_e7_e8.py`
- **Metrics/raw data:** summary metrics, appliance events, and sampled telemetry in JSON.

## E8: Cold-load pickup under restoration modes
- **Hypothesis:** Deterministic staggered appliance starts and safety-gated synchronized batches produce distinct pickup and rebound behavior.
- **Baseline/proposed:** P2 synchronized batch restoration versus deterministic staggered restoration.
- **Controlled variables:** same scenario, P2 policy, appliance profiles, and seeds.
- **Runner:** `experiments/sensitivity_analysis/run_e7_e8.py`
- **Metrics/raw data:** restoration events and frequency/demand telemetry.

## E9: NILM synthetic event classification
- **Hypothesis:** Magnitude signatures classify distinct synthetic switching steps and abstain on unknown events.
- **Baseline/proposed:** synthetic ground-truth labels versus confidence-based detector.
- **Controlled variables:** generated signal, seed, signature catalogue, and threshold.
- **Runner:** `experiments/sensitivity_analysis/run_e9.py`
- **Metrics/raw data:** precision, recall, F1, confusion matrix, features, confidence, and labels.
- **Limit:** synthetic evaluation does not establish real-world appliance recognition.

## E10: Centralized versus distributed edge response
- **Hypothesis:** Distributed edge decisions retain local response under simulated packet loss.
- **Baseline/proposed:** centralized dispatch versus distributed P2 edge agents.
- **Controlled variables:** communication fault scenario, P2 thresholds, and paired seeds.
- **Runner:** `experiments/sensitivity_analysis/run_e10.py`
- **Metrics/raw data:** per-seed metrics, events, and raw telemetry in JSON.

## E11: HIL protocol versus virtual edge response
- **Hypothesis:** The versioned HIL protocol preserves the virtual edge decision contract in software.
- **Baseline/proposed:** virtual edge P2 versus software-emulated controller over JSON lines.
- **Controlled variables:** simulated frequency, RoCoF, appliance inventory, and building ID.
- **Runner:** `experiments/sensitivity_analysis/run_e11.py`
- **Limit:** protocol parity is not physical response-time or hardware validation.

## E12: Fleet-scale performance and participation
- **Hypothesis:** Runtime and memory costs can be measured across fleet sizes and participation fractions.
- **Fleet sizes:** 12, 100, 500, and 1,000 buildings; participation 0.5, 0.8, and 1.0.
- **Controlled variables:** seeded heterogeneous appliance profiles and P2 configuration.
- **Runner:** `experiments/sensitivity_analysis/run_e6.py`
- **Metrics/raw data:** frequency nadir, protection/fairness metrics, runtime, memory, appliance count, seed, and scenario hash in CSV.
