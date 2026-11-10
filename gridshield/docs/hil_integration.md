# Hardware-in-the-loop (HIL) reference

The optional adapter exchanges newline-delimited JSON using protocol version
`1.0`. It is bound to one configured virtual building; it does not replace the
policy for the rest of the simulated fleet. Install the backend's optional
dependency with `python -m pip install -e ".[hil]"`, then start a P2 run with
`hil_port`, `hil_building_id`, and (optionally) `hil_baud_rate` in the
`POST /api/v1/runs` request. The building ID must exist in the selected
scenario. Without those request fields, GridShield's normal simulation has no
serial dependency.

Telemetry messages carry a monotonically increasing sequence, **simulation**
timestamp, simulated grid frequency and RoCoF, and the designated building's
appliance identifiers, categories, priorities, and state. Feedback includes
the target building, appliance states/decisions, controller status, protocol
version, and a monotonic sequence. The adapter rejects malformed, wrong-building,
unknown-appliance, duplicate, and stale messages. A missing heartbeat marks
the adapter disconnected and reports `fallback_active`; the virtual edge policy
remains the safe fallback and the rest of the virtual fleet continues to run.

The reference firmware uses the frequency and RoCoF supplied by the simulator;
it has no actual grid-frequency measurement interface. Its relay abstraction is
disabled by default (`kEnableLowVoltageOutputs = false`). The project is a
laboratory prototype, not certified protection equipment. Do not connect this
prototype directly to mains. Any output testing must use low-voltage DC loads
and appropriately isolated relay interfaces; critical loads are never shed by
its local policy.

Build and flash from `firmware/esp32` using PlatformIO (`pio run`,
`pio run --target upload`, `pio device monitor`). On its first telemetry
message, the firmware adopts the requested virtual building ID and reports
local shed/restore actions back as feedback commands. A lost heartbeat falls
back to the GridShield P2 policy for that building. Physical-controller timing,
serial reconnection and low-voltage output behavior still require laboratory
validation.
