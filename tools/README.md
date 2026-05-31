# Serial Dashboard

Run the dashboard against the CH32V003 UART CSV output:

```powershell
python tools\serial_dashboard.py --port COM5 --baud 921600
```

Use the COM port shown by your USB-UART adapter. Close PlatformIO's serial
monitor before connecting, because only one program can normally hold the COM
port at a time.

The default `genericCH32V003J4M6_servo_control` firmware disables servo-control
telemetry so UART TX cannot block the control loop. Build
`genericCH32V003J4M6_servo_control_debug` when you want dashboard output:

```powershell
platformio run -e genericCH32V003J4M6_servo_control_debug -t upload
```

The dashboard auto-detects both firmware output modes:

- ADC / motor sweep:
  `sample,raw,avg16,mv,pct,angle_deg,direction_changes`
- RC input capture:
  `frame,pulse_us,period_us,freq_hz,valid,sg90_deg,n20_deg`
- Closed-loop servo control:
  `sample,target_deg,angle_deg,error_deg,duty,pulse_us,valid`

Useful test commands:

```powershell
python tools\serial_dashboard.py --demo --demo-mode adc
python tools\serial_dashboard.py --demo --demo-mode rc
python tools\serial_dashboard.py --demo --demo-mode servo
python tools\serial_dashboard.py --self-test
```

If `pyserial` is missing:

```powershell
python -m pip install -r requirements-dashboard.txt
```

## Servo Configurator

Run the Tkinter configurator for `include/servo_config.h`:

```powershell
python tools\servo_configurator.py
```

It edits the existing `#define` values, validates common range mistakes, and
creates a timestamped `.bak` copy of the header every time you save.

Parser/validation check without opening the GUI:

```powershell
python tools\servo_configurator.py --self-test
```

Changing `TEST_MODE` or `SERVO_CONTROL_TELEMETRY_ENABLE` in the header only
affects builds where `platformio.ini` does not override those macros with
`build_flags`.
