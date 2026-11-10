# GridShield — Model Assumptions and Parameters

All parameters are configurable via `GridParams` in the scenario YAML.
Values marked "sweep" are varied in Experiment E5 (sensitivity analysis).

| Parameter | Symbol | Default value | Source / justification | Swept in E5 |
|-----------|--------|---------------|------------------------|-------------|
| Nominal frequency | f₀ | 50 Hz | IEGC 2023 reference frequency | No |
| Inertia constant | H | 4.0 s | Typical Indian grid estimate; sweep 3–6 s | Yes |
| Load damping | D | 1.5 pu | Mid-range estimate; sweep 1–2 pu | Yes |
| Droop | R | 0.05 (5%) | IEGC 2023: governor droop 3–6% | Yes |
| Governor deadband | ±db | ±0.03 Hz | IEGC 2023: deadband not exceeding ±0.03 Hz | No |
| Governor time constant | Tg | 0.1 s | Typical steam/hydro governor | Yes |
| Turbine time constant | Tt | 0.4 s | Typical steam turbine | Yes |
| Up reserve | up_reserve | 0.20 pu | Design choice; limits governor headroom | Yes |
| Down reserve | down_reserve | 0.10 pu | Design choice | Yes |
| RK4 time step | dt | 0.02 s (20 ms) | Confirmed numerically in E5 | No |
| Agent sample interval | T_agent | 0.5 s | Configurable; see E7 for communication faults | No |
| S0 Advisory trigger | f_s0 | 49.90 Hz | IEGC 2023 lower band limit | No |
| S1 trigger | f_s1 | 49.85 Hz | Southern Region ADMS trip level | No |
| S2 trigger | f_s2 | 49.60 Hz | Original synopsis; RoCoF ≤ −0.3 Hz/s also triggers | No |
| S3 trigger | f_s3 | 49.40 Hz | Typical first UFLS stage (Himachal Grid Code 2026) | No |
| O1 absorb trigger | f_o1 | 50.05 Hz | IEGC 2023 upper band limit | No |
| O2 absorb+ trigger | f_o2 | 50.20 Hz | Design choice | No |
| Recovery band | f_rec | 49.95 Hz | With hysteresis above S0 | No |
| Stability hold duration | T_stable | 60 s | Design choice for restoration eligibility | No |
| S0 hold before action | T_s0 | 10 s | Advisory: sustained below 49.90 Hz | No |
| S1 hold before action | T_s1 | 5 s | Matches ADMS delay intent | No |
| O1 hold before action | T_o1 | 30 s | Prevents chatter on transient over-freq | No |

## Appliance startup and lockout assumptions

The following are configurable illustrative software defaults, not measured
Karnataka data: split ACs use a 3.0 startup multiplier for 1.0 s and 180 s
compressor restart lockout; refrigerators use 2.0 for 0.5 s and the same
compressor lockout; water pumps use 2.0 for 0.5 s; other categories default to
no startup demand above rated power. Startup recovery defaults to linear and is
evaluated on simulation time at the grid timestep. Minimum ON/OFF values remain
category-specific configuration values; compressor lockout is not applied to
water heaters, EV chargers, fans, or lighting.

These coarse transient shapes support software sensitivity testing. They do
not represent measured starting current, voltage-dependent motor behavior, or
a validated cold-load pickup model.

## Known limitations

- Single-area reduced-order model: no network topology, voltage, or inter-area oscillations.
- Simplified governor: no valve limits beyond headroom clamp, no reheat.
- Synthetic load behaviour: duty cycles and comfort limits are approximate.
- Consumer consent and behaviour beyond the enrolled/not-enrolled flag are not modelled.
- Cyber-security is out of scope.
- Absolute MW figures are NOT claimed for real Karnataka grids in Mode A (scaled); results are per-unit and relative.

## Sources

- IEGC 2023 reference frequency and band: Mercom India (checked 27 Oct 2026)
  https://www.mercomindia.com/high-grid-frequency-events-prompt-grid-india-to-warn-users-to-be-cautious
- Governor droop 3–6%, deadband ±0.03 Hz: Grid-India / IRADE presentation (checked 27 Oct 2026)
  https://irade.org/presentation-21-22nd-Nov2024/Grid%20stability%20and%20balancing%20due%20to%20Intermittent%20Generation_Alok%20Pratap.pdf
- S3 / UFLS 49.40 Hz: Himachal Grid Code 2026 (checked 27 Oct 2026)
  https://powerpeakdigest.com/hperc-notifies-grid-code-2026-iegc-2023/
- Southern Region ADMS trip thresholds: CERC proceedings (checked 27 Oct 2026)
  https://cercind.gov.in/2013/ROP/ROP263.pdf
