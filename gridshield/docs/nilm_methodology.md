# NILM methodology and limitations

GridShield's optional `app.nilm` package consumes timestamped aggregate active
power samples. It detects step changes, extracts signed change, magnitude,
sample interval and change rate, then compares the magnitude with a configurable
catalogue of nominal appliance signatures. A confidence score, and explicit
`unknown` / `ambiguous` outcomes, prevent every event from being forced into a
class.

`NILMStateEstimator` emits `nilm_estimate` records separately from ground-truth
`Appliance` state and does not mutate the simulation twin. The source protocol
allows future real-meter adapters; `make_synthetic_signal` provides reproducible
test signals. `evaluate_classification` reports precision, recall, F1 and a
confusion matrix. Run the synthetic experiment from the repository root with:

```powershell
Set-Location .\backend
python ..\experiments\sensitivity_analysis\run_e9.py
```

Default signature powers are representative synthetic class templates, not
measured Karnataka appliance fingerprints. Real aggregate meters contain
overlapping loads, changing duty cycles, noise, and appliances absent from the
catalogue; this simple event-magnitude classifier is not a validated field
NILM model. Synthetic precision and recall must not be presented as evidence
of real-world recognition accuracy. NILM is not enabled in the deterministic
simulation or current dashboard.
