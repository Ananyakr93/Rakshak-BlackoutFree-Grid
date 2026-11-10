# ESP32 laboratory reference firmware

The PlatformIO Arduino reference is under `firmware/esp32`. From that
directory, install PlatformIO and run:

```powershell
pio run
pio run --target upload
pio device monitor --baud 115200
```

The firmware uses the versioned newline-delimited JSON protocol in
`backend/app/hil/protocol.py`. Frequency and RoCoF are **simulated values
received from GridShield**; the firmware does not measure utility frequency.
Its local P2-inspired rules protect critical loads, prioritize deferrable
loads, enforce compressor restart lockout and stagger restoration using a
deterministic delay derived from the ESP32 MAC address.

Outputs are disabled by default (`kEnableLowVoltageOutputs = false`). The
reference is for laboratory testing only, not certified protection equipment.
Do not connect it directly to mains. Any output validation must use low-voltage
DC loads and appropriately isolated relay interfaces. Never use this prototype
to automatically shed critical loads.

Physical timing, serial reconnection and isolated-output behavior require
laboratory validation. Hardware tests cannot be inferred from software-only
simulation results.
