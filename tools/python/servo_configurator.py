#!/usr/bin/env python3
"""Tkinter configurator for include/servo_config.h."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "include" / "servo_config.h"
DEFINE_RE = re.compile(
    r"^(?P<indent>\s*)#define\s+(?P<name>[A-Za-z_]\w*)\s+"
    r"(?P<value>.*?)(?P<newline>\r?\n)?$"
)
SYMBOL_RE = re.compile(r"^[A-Za-z_]\w*$")
EXPRESSION_RE = re.compile(r"^[A-Za-z0-9_()|&+\-*/<>=!\s]+$")


class ConfigError(Exception):
    """Raised when a config file cannot be parsed or written safely."""


@dataclass(frozen=True)
class ConfigItem:
    category: str
    name: str
    label: str
    description: str
    kind: str = "uint"
    unit: str = ""
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None


def item(
    category: str,
    name: str,
    label: str,
    description: str,
    kind: str = "uint",
    unit: str = "",
    choices: tuple[str, ...] = (),
    minimum: int | None = None,
    maximum: int | None = None,
) -> ConfigItem:
    return ConfigItem(
        category=category,
        name=name,
        label=label,
        description=description,
        kind=kind,
        unit=unit,
        choices=choices,
        minimum=minimum,
        maximum=maximum,
    )


GPIO_PORTS = ("GPIOA", "GPIOC", "GPIOD")
GPIO_PINS = tuple(f"GPIO_Pin_{pin}" for pin in range(8))
ADC_CHANNELS = tuple(f"ADC_Channel_{channel}" for channel in range(8))
TEST_MODES = (
    "TEST_MODE_ADC_ONLY",
    "TEST_MODE_MOTOR_SWEEP",
    "TEST_MODE_RC_INPUT_CAPTURE",
    "TEST_MODE_SERVO_CONTROL",
)
MOTOR_DIRECTION_PINS = ("MOTOR_PC1_PIN", "MOTOR_PC2_PIN")
BOOL_VALUES = ("0U", "1U")


CONFIG_ITEMS: tuple[ConfigItem, ...] = (
    item(
        "Firmware",
        "TEST_MODE",
        "Default Test Mode",
        "Default mode used only when platformio.ini does not pass -DTEST_MODE.",
        "choice",
        choices=TEST_MODES,
    ),
    item(
        "Firmware",
        "SERVO_CONTROL_TELEMETRY_ENABLE",
        "Servo Telemetry",
        "Enables UART CSV output in closed-loop mode. Keep disabled for least loop jitter.",
        "bool",
        choices=BOOL_VALUES,
    ),
    item(
        "Firmware",
        "UART_BAUD_RATE",
        "UART Baud Rate",
        "Baud rate used by printf when SDI_PRINT is disabled.",
        unit="baud",
        minimum=1200,
        maximum=3000000,
    ),
    item(
        "ADC & Sensor",
        "ADC_INPUT_GPIO_PORT",
        "ADC GPIO Port",
        "GPIO port used by the potentiometer wiper ADC input.",
        "choice",
        choices=GPIO_PORTS,
    ),
    item(
        "ADC & Sensor",
        "ADC_INPUT_GPIO_PIN",
        "ADC GPIO Pin",
        "GPIO pin used by the potentiometer wiper ADC input.",
        "choice",
        choices=GPIO_PINS,
    ),
    item(
        "ADC & Sensor",
        "ADC_INPUT_CHANNEL",
        "ADC Channel",
        "ADC channel matching the selected GPIO pin.",
        "choice",
        choices=ADC_CHANNELS,
    ),
    item(
        "ADC & Sensor",
        "ADC_AVERAGE_SAMPLES",
        "Diagnostic Samples",
        "Number of ADC samples averaged in ADC-only and sweep debug output.",
        "uint",
        "samples",
        minimum=1,
        maximum=128,
    ),
    item(
        "ADC & Sensor",
        "ADC_CONTROL_SAMPLES",
        "Control Samples",
        "Number of ADC samples averaged per closed-loop control update.",
        "uint",
        "samples",
        minimum=1,
        maximum=64,
    ),
    item(
        "ADC & Sensor",
        "ADC_FULL_SCALE_COUNTS",
        "ADC Full Scale",
        "Maximum ADC count. The CH32V003 ADC is currently used as 10-bit.",
        "uint",
        "counts",
        minimum=1,
        maximum=65535,
    ),
    item(
        "ADC & Sensor",
        "ADC_REFERENCE_MV",
        "ADC Reference",
        "Reference voltage used only for millivolt calculations in debug output.",
        "uint",
        "mV",
        minimum=1,
        maximum=6000,
    ),
    item(
        "ADC & Sensor",
        "ADC_UPDATE_INTERVAL_MS",
        "ADC Debug Interval",
        "Delay between ADC-only or motor-sweep diagnostic rows.",
        "uint",
        "ms",
        minimum=1,
        maximum=10000,
    ),
    item(
        "ADC & Sensor",
        "ANGLE_FULL_SCALE_DEGREES",
        "ADC Display Range",
        "Full potentiometer travel used by ADC-only angle display.",
        "uint",
        "deg",
        minimum=1,
        maximum=360,
    ),
    item(
        "RC Input",
        "RC_INPUT_GPIO_PORT",
        "RC GPIO Port",
        "GPIO port for the incoming 50 Hz RC servo PWM signal.",
        "choice",
        choices=GPIO_PORTS,
    ),
    item(
        "RC Input",
        "RC_INPUT_GPIO_PIN",
        "RC GPIO Pin",
        "GPIO pin for the incoming 50 Hz RC servo PWM signal.",
        "choice",
        choices=GPIO_PINS,
    ),
    item(
        "RC Input",
        "RC_INPUT_MIN_US",
        "Command Minimum",
        "Pulse width mapped to full negative command.",
        "uint",
        "us",
        minimum=100,
        maximum=5000,
    ),
    item(
        "RC Input",
        "RC_INPUT_CENTER_US",
        "Command Center",
        "Pulse width mapped to center command.",
        "uint",
        "us",
        minimum=100,
        maximum=5000,
    ),
    item(
        "RC Input",
        "RC_INPUT_MAX_US",
        "Command Maximum",
        "Pulse width mapped to full positive command.",
        "uint",
        "us",
        minimum=100,
        maximum=5000,
    ),
    item(
        "RC Input",
        "RC_INPUT_VALID_MIN_US",
        "Valid Pulse Minimum",
        "Lowest captured pulse width accepted as a valid signal.",
        "uint",
        "us",
        minimum=100,
        maximum=5000,
    ),
    item(
        "RC Input",
        "RC_INPUT_VALID_MAX_US",
        "Valid Pulse Maximum",
        "Highest captured pulse width accepted as a valid signal.",
        "uint",
        "us",
        minimum=100,
        maximum=5000,
    ),
    item(
        "RC Input",
        "RC_INPUT_PERIOD_VALID_MIN_US",
        "Valid Period Minimum",
        "Lowest accepted RC frame period.",
        "uint",
        "us",
        minimum=1000,
        maximum=100000,
    ),
    item(
        "RC Input",
        "RC_INPUT_PERIOD_VALID_MAX_US",
        "Valid Period Maximum",
        "Highest accepted RC frame period.",
        "uint",
        "us",
        minimum=1000,
        maximum=100000,
    ),
    item(
        "RC Input",
        "RC_INPUT_REPORT_INTERVAL_MS",
        "Capture Report Interval",
        "Delay between rows in RC input-capture diagnostic mode.",
        "uint",
        "ms",
        minimum=1,
        maximum=10000,
    ),
    item(
        "RC Input",
        "RC_INPUT_TIMEOUT_MS",
        "RC Timeout",
        "Time without a fresh RC frame before closed-loop mode coasts the motor.",
        "uint",
        "ms",
        minimum=1,
        maximum=5000,
    ),
    item(
        "RC Input",
        "RC_SG90_FULL_SCALE_TENTHS",
        "SG90 Display Scale",
        "Reference SG90-style command range shown in input-capture diagnostics.",
        "int",
        "0.1 deg",
        minimum=1,
        maximum=3600,
    ),
    item(
        "RC Input",
        "RC_N20_FULL_SCALE_TENTHS",
        "N20 Display Scale",
        "N20 servo command range shown in input-capture diagnostics.",
        "int",
        "0.1 deg",
        minimum=1,
        maximum=3600,
    ),
    item(
        "Servo Calibration",
        "SERVO_ANGLE_FULL_SCALE_TENTHS",
        "Measured Full Scale",
        "Absolute measured servo range used by feedback mapping.",
        "int",
        "0.1 deg",
        minimum=1,
        maximum=3600,
    ),
    item(
        "Servo Calibration",
        "POT_ADC_AT_NEG160",
        "ADC At Negative End",
        "ADC count measured at the negative mechanical endpoint.",
        "uint",
        "counts",
        minimum=0,
        maximum=65535,
    ),
    item(
        "Servo Calibration",
        "POT_ADC_AT_CENTER",
        "ADC At Center",
        "ADC count measured at the center position.",
        "uint",
        "counts",
        minimum=0,
        maximum=65535,
    ),
    item(
        "Servo Calibration",
        "POT_ADC_AT_POS160",
        "ADC At Positive End",
        "ADC count measured at the positive mechanical endpoint.",
        "uint",
        "counts",
        minimum=0,
        maximum=65535,
    ),
    item(
        "Servo Calibration",
        "SERVO_COMMAND_GAIN_PERMILLE",
        "Command Gain",
        "Command scale trim in permille. 1000 means no scale correction.",
        "int",
        "permille",
        minimum=100,
        maximum=5000,
    ),
    item(
        "Servo Calibration",
        "SERVO_COMMAND_OFFSET_TENTHS",
        "Command Offset",
        "Command offset trim applied after gain.",
        "int",
        "0.1 deg",
        minimum=-3600,
        maximum=3600,
    ),
    item(
        "Servo Calibration",
        "SERVO_ENDPOINT_PROTECTION_ENABLE",
        "Endpoint Protection",
        "Clamps commands below the physical range to avoid the potentiometer dead zone.",
        "bool",
        choices=BOOL_VALUES,
    ),
    item(
        "Servo Calibration",
        "SERVO_ENDPOINT_LIMIT_TENTHS",
        "Endpoint Limit",
        "Command clamp used when endpoint protection is enabled.",
        "int",
        "0.1 deg",
        minimum=0,
        maximum=3600,
    ),
    item(
        "Control Loop",
        "CONTROL_LOOP_INTERVAL_MS",
        "Control Interval",
        "Closed-loop update interval.",
        "uint",
        "ms",
        minimum=1,
        maximum=1000,
    ),
    item(
        "Control Loop",
        "CONTROL_DEBUG_INTERVAL_MS",
        "Telemetry Interval",
        "Delay between telemetry rows when closed-loop telemetry is enabled.",
        "uint",
        "ms",
        minimum=1,
        maximum=10000,
    ),
    item(
        "Control Loop",
        "CONTROL_POSITION_DEADBAND_TENTHS",
        "Position Deadband",
        "Position error band where the controller stops driving the motor.",
        "uint",
        "0.1 deg",
        minimum=0,
        maximum=1000,
    ),
    item(
        "Control Loop",
        "CONTROL_REVERSE_DEADBAND_TENTHS",
        "Reverse Deadband",
        "Small-error reversal band where the controller brakes before reversing.",
        "uint",
        "0.1 deg",
        minimum=0,
        maximum=2000,
    ),
    item(
        "Control Loop",
        "CONTROL_SLOW_ZONE_TENTHS",
        "Slow Zone",
        "Error size where drive reaches full duty; below this it ramps down.",
        "uint",
        "0.1 deg",
        minimum=1,
        maximum=3600,
    ),
    item(
        "Control Loop",
        "CONTROL_HOLD_BRAKE_ENABLED",
        "Hold Brake",
        "Uses H-bridge brake inside the deadband instead of coasting.",
        "bool",
        choices=BOOL_VALUES,
    ),
    item(
        "Motor PWM",
        "MOTOR_PWM_HZ",
        "PWM Frequency",
        "GPIO PWM frequency for the two H-bridge input pins.",
        "uint",
        "Hz",
        minimum=1,
        maximum=100000,
    ),
    item(
        "Motor PWM",
        "MOTOR_PWM_TIMER_HZ",
        "PWM Timer Rate",
        "Timer tick rate used to generate the GPIO PWM waveform.",
        "uint",
        "Hz",
        minimum=1,
        maximum=48000000,
    ),
    item(
        "Motor PWM",
        "MOTOR_PWM_PERIOD_TICKS",
        "PWM Period Ticks",
        "Timer period ticks. Usually keep this derived from timer rate and PWM frequency.",
        "expression",
    ),
    item(
        "Motor PWM",
        "MOTOR_PWM_DUTY_MAX",
        "Duty Maximum",
        "Maximum motor duty command. 1000 represents 100.0 percent.",
        "uint",
        "counts",
        minimum=1,
        maximum=65535,
    ),
    item(
        "Motor PWM",
        "MOTOR_PWM_MIN_DUTY",
        "Minimum Drive Duty",
        "Minimum duty used once outside the position deadband.",
        "uint",
        "counts",
        minimum=0,
        maximum=65535,
    ),
    item(
        "Motor PWM",
        "MOTOR_REVERSE_BRAKE_MS",
        "Reverse Brake Time",
        "Brake time before reversing direction in sweep mode.",
        "uint",
        "ms",
        minimum=0,
        maximum=10000,
    ),
    item(
        "Motor PWM",
        "MOTOR_GPIO_PORT",
        "Motor GPIO Port",
        "GPIO port shared by both H-bridge control pins.",
        "choice",
        choices=GPIO_PORTS,
    ),
    item(
        "Motor PWM",
        "MOTOR_PC1_PIN",
        "Motor Pin 1",
        "First H-bridge control pin.",
        "choice",
        choices=GPIO_PINS,
    ),
    item(
        "Motor PWM",
        "MOTOR_PC2_PIN",
        "Motor Pin 2",
        "Second H-bridge control pin.",
        "choice",
        choices=GPIO_PINS,
    ),
    item(
        "Motor PWM",
        "MOTOR_GPIO_PINS",
        "Motor Pin Mask",
        "Combined H-bridge pin mask.",
        "expression",
    ),
    item(
        "Motor PWM",
        "MOTOR_TOWARD_HIGH_PIN",
        "Toward High Pin",
        "H-bridge pin that increases the measured potentiometer angle.",
        "choice",
        choices=MOTOR_DIRECTION_PINS,
    ),
    item(
        "Motor PWM",
        "MOTOR_TOWARD_LOW_PIN",
        "Toward Low Pin",
        "H-bridge pin that decreases the measured potentiometer angle.",
        "choice",
        choices=MOTOR_DIRECTION_PINS,
    ),
    item(
        "Sweep Test",
        "SWEEP_ENDPOINT_SETTLE_MS",
        "Endpoint Settle Time",
        "Pause after each completed endpoint in sweep test mode.",
        "uint",
        "ms",
        minimum=0,
        maximum=60000,
    ),
    item(
        "Sweep Test",
        "SWEEP_LOW_TARGET_TENTHS",
        "Sweep Low Target",
        "Low endpoint target for motor sweep test mode.",
        "uint",
        "0.1 deg",
        minimum=0,
        maximum=3600,
    ),
    item(
        "Sweep Test",
        "SWEEP_HIGH_TARGET_TENTHS",
        "Sweep High Target",
        "High endpoint target for motor sweep test mode.",
        "uint",
        "0.1 deg",
        minimum=0,
        maximum=3600,
    ),
    item(
        "Sweep Test",
        "SWEEP_TARGET_TOLERANCE_TENTHS",
        "Sweep Target Tolerance",
        "Endpoint tolerance used before changing direction.",
        "uint",
        "0.1 deg",
        minimum=0,
        maximum=1000,
    ),
)


def read_config_values(path: Path) -> dict[str, str]:
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
        match = DEFINE_RE.match(line)
        if match:
            values[match.group("name")] = match.group("value").strip()
    return values


def write_config_values(path: Path, updates: dict[str, str]) -> Path:
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")

    original = path.read_text(encoding="utf-8").splitlines(keepends=True)
    output: list[str] = []
    seen: set[str] = set()

    for line in original:
        match = DEFINE_RE.match(line)
        if match and match.group("name") in updates:
            name = match.group("name")
            newline = match.group("newline") or "\n"
            output.append(f"{match.group('indent')}#define {name} {updates[name]}{newline}")
            seen.add(name)
        else:
            output.append(line)

    missing = sorted(set(updates) - seen)
    if missing:
        raise ConfigError("Could not find definitions for: " + ", ".join(missing))

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    shutil.copy2(path, backup_path)
    path.write_text("".join(output), encoding="utf-8", newline="")
    return backup_path


def parse_c_int(value: str) -> int:
    text = value.strip()
    while text and text[-1] in "uUlL":
        text = text[:-1]
    if not text:
        raise ValueError("empty integer")
    return int(text, 0)


def validate_value(config_item: ConfigItem, value: str) -> str | None:
    value = value.strip()
    if not value:
        return f"{config_item.name} is empty"

    if config_item.kind in {"uint", "int", "bool"}:
        try:
            parsed = parse_c_int(value)
        except ValueError:
            return f"{config_item.name} must be an integer value"

        if config_item.kind == "uint" and parsed < 0:
            return f"{config_item.name} must be non-negative"
        if config_item.kind == "bool" and parsed not in (0, 1):
            return f"{config_item.name} must be 0 or 1"
        if config_item.minimum is not None and parsed < config_item.minimum:
            return f"{config_item.name} must be >= {config_item.minimum}"
        if config_item.maximum is not None and parsed > config_item.maximum:
            return f"{config_item.name} must be <= {config_item.maximum}"
        return None

    if config_item.kind == "choice":
        if value not in config_item.choices:
            return f"{config_item.name} must be one of: {', '.join(config_item.choices)}"
        return None

    if config_item.kind == "symbol":
        if not SYMBOL_RE.match(value):
            return f"{config_item.name} must be a C symbol"
        return None

    if config_item.kind == "expression":
        if not EXPRESSION_RE.match(value):
            return f"{config_item.name} contains unsupported expression characters"
        return None

    return f"{config_item.name} uses unknown validator kind: {config_item.kind}"


def validate_all(values: dict[str, str]) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    for config_item in CONFIG_ITEMS:
        value = values.get(config_item.name)
        if value is None:
            errors.append(f"Missing {config_item.name}")
            continue
        error = validate_value(config_item, value)
        if error:
            errors.append(error)

    if errors:
        return errors, warnings

    nums = {
        config_item.name: parse_c_int(values[config_item.name])
        for config_item in CONFIG_ITEMS
        if config_item.kind in {"uint", "int", "bool"}
    }

    if not nums["RC_INPUT_MIN_US"] < nums["RC_INPUT_CENTER_US"] < nums["RC_INPUT_MAX_US"]:
        errors.append("RC command pulse range must be min < center < max")

    if nums["RC_INPUT_VALID_MIN_US"] > nums["RC_INPUT_MIN_US"]:
        errors.append("RC valid minimum should not be higher than command minimum")

    if nums["RC_INPUT_VALID_MAX_US"] < nums["RC_INPUT_MAX_US"]:
        errors.append("RC valid maximum should not be lower than command maximum")

    if nums["RC_INPUT_PERIOD_VALID_MIN_US"] >= nums["RC_INPUT_PERIOD_VALID_MAX_US"]:
        errors.append("RC valid period minimum must be lower than maximum")

    if not nums["POT_ADC_AT_NEG160"] < nums["POT_ADC_AT_CENTER"] < nums["POT_ADC_AT_POS160"]:
        errors.append("Potentiometer calibration must be negative < center < positive")

    if nums["SERVO_ENDPOINT_LIMIT_TENTHS"] > nums["SERVO_ANGLE_FULL_SCALE_TENTHS"]:
        warnings.append("Endpoint limit is above measured full scale; firmware will clamp it")

    if nums["CONTROL_POSITION_DEADBAND_TENTHS"] >= nums["CONTROL_SLOW_ZONE_TENTHS"]:
        errors.append("Control position deadband must be lower than slow zone")

    if nums["CONTROL_REVERSE_DEADBAND_TENTHS"] < nums["CONTROL_POSITION_DEADBAND_TENTHS"]:
        warnings.append("Reverse deadband is below position deadband")

    if nums["MOTOR_PWM_HZ"] > nums["MOTOR_PWM_TIMER_HZ"]:
        errors.append("Motor PWM frequency must not exceed the PWM timer rate")
    else:
        period_ticks = nums["MOTOR_PWM_TIMER_HZ"] // nums["MOTOR_PWM_HZ"]
        if period_ticks < 2:
            errors.append("Motor PWM period must be at least 2 timer ticks")

    if nums["MOTOR_PWM_MIN_DUTY"] > nums["MOTOR_PWM_DUTY_MAX"]:
        errors.append("Motor minimum duty must not exceed maximum duty")

    if values["MOTOR_TOWARD_HIGH_PIN"] == values["MOTOR_TOWARD_LOW_PIN"]:
        errors.append("Motor toward-high and toward-low pins must be different")

    if nums["SWEEP_LOW_TARGET_TENTHS"] >= nums["SWEEP_HIGH_TARGET_TENTHS"]:
        errors.append("Sweep low target must be lower than sweep high target")

    return errors, warnings


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self.canvas.yview
        )
        self.inner = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window(
            (0, 0), window=self.inner, anchor="nw"
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)

    def _on_inner_configure(self, _event: tk.Event) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class ServoConfiguratorApp(tk.Tk):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.title("N20 Servo Configurator")
        self.minsize(920, 680)

        self.config_path = config_path
        self.path_var = tk.StringVar(value=str(config_path))
        self.status_var = tk.StringVar(value="Ready")
        self.vars: dict[str, tk.StringVar] = {}
        self.widgets: dict[str, ttk.Widget] = {}

        self._build_ui()
        self.load_config()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(12, 10, 12, 6))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Config file").grid(row=0, column=0, sticky="w")
        path_entry = ttk.Entry(top, textvariable=self.path_var, state="readonly")
        path_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(top, text="Browse", command=self.browse_config).grid(
            row=0, column=2, padx=(0, 6)
        )
        ttk.Button(top, text="Reload", command=self.load_config).grid(
            row=0, column=3, padx=(0, 6)
        )
        ttk.Button(top, text="Save", command=self.save_config).grid(row=0, column=4)

        note = ttk.Label(
            top,
            text=(
                "Note: platformio.ini build_flags can override TEST_MODE and "
                "SERVO_CONTROL_TELEMETRY_ENABLE at compile time."
            ),
            foreground="#5c6773",
        )
        note.grid(row=1, column=0, columnspan=5, sticky="w", pady=(8, 0))

        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))

        categories = []
        for config_item in CONFIG_ITEMS:
            if config_item.category not in categories:
                categories.append(config_item.category)

        for category in categories:
            frame = ScrollableFrame(self.notebook)
            self.notebook.add(frame, text=category)
            self._build_category(frame.inner, category)

        bottom = ttk.Frame(self, padding=(12, 0, 12, 10))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.status_var, foreground="#2d5f8b").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(bottom, text="Validate", command=self.validate_current).grid(
            row=0, column=1
        )

    def _build_category(self, parent: ttk.Frame, category: str) -> None:
        parent.columnconfigure(1, weight=1)
        row = 0
        for config_item in [entry for entry in CONFIG_ITEMS if entry.category == category]:
            var = tk.StringVar()
            self.vars[config_item.name] = var

            label_text = config_item.label
            if config_item.unit:
                label_text = f"{label_text} ({config_item.unit})"

            ttk.Label(parent, text=label_text).grid(
                row=row, column=0, sticky="nw", padx=(12, 10), pady=(12, 2)
            )

            if config_item.kind in {"choice", "bool"}:
                widget = ttk.Combobox(
                    parent,
                    textvariable=var,
                    values=config_item.choices,
                    state="readonly",
                    width=34,
                )
            else:
                widget = ttk.Entry(parent, textvariable=var, width=36)

            widget.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=(10, 2))
            self.widgets[config_item.name] = widget

            ttk.Label(
                parent,
                text=f"{config_item.name}: {config_item.description}",
                foreground="#5c6773",
                wraplength=620,
            ).grid(row=row + 1, column=1, sticky="w", padx=(0, 12), pady=(0, 6))
            row += 2

    def browse_config(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select servo_config.h",
            initialdir=str(self.config_path.parent),
            filetypes=(("C headers", "*.h"), ("All files", "*.*")),
        )
        if not selected:
            return
        self.config_path = Path(selected)
        self.path_var.set(str(self.config_path))
        self.load_config()

    def load_config(self) -> None:
        try:
            values = read_config_values(self.config_path)
        except ConfigError as error:
            messagebox.showerror("Load failed", str(error))
            return

        missing = []
        for config_item in CONFIG_ITEMS:
            if config_item.name in values:
                self.vars[config_item.name].set(values[config_item.name])
            else:
                self.vars[config_item.name].set("")
                missing.append(config_item.name)

        if missing:
            self.status_var.set("Loaded with missing fields: " + ", ".join(missing))
        else:
            self.status_var.set(f"Loaded {self.config_path}")

    def current_values(self) -> dict[str, str]:
        return {name: var.get().strip() for name, var in self.vars.items()}

    def validate_current(self) -> bool:
        errors, warnings = validate_all(self.current_values())
        if errors:
            messagebox.showerror("Validation failed", "\n".join(errors))
            self.status_var.set(f"Validation failed with {len(errors)} error(s)")
            return False

        if warnings:
            messagebox.showwarning("Validation warnings", "\n".join(warnings))
            self.status_var.set(f"Validation passed with {len(warnings)} warning(s)")
            return True

        messagebox.showinfo("Validation passed", "Configuration looks valid.")
        self.status_var.set("Validation passed")
        return True

    def save_config(self) -> None:
        values = self.current_values()
        errors, warnings = validate_all(values)
        if errors:
            messagebox.showerror("Save blocked", "\n".join(errors))
            self.status_var.set(f"Save blocked by {len(errors)} validation error(s)")
            return

        if warnings:
            proceed = messagebox.askyesno(
                "Save with warnings?",
                "\n".join(warnings) + "\n\nSave anyway?",
            )
            if not proceed:
                self.status_var.set("Save cancelled")
                return

        try:
            backup_path = write_config_values(self.config_path, values)
        except ConfigError as error:
            messagebox.showerror("Save failed", str(error))
            self.status_var.set("Save failed")
            return

        self.status_var.set(f"Saved. Backup: {backup_path.name}")
        messagebox.showinfo(
            "Saved",
            f"Updated {self.config_path.name}\nBackup created: {backup_path.name}",
        )


def run_self_test(config_path: Path) -> int:
    try:
        values = read_config_values(config_path)
    except ConfigError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    editable_values = {
        config_item.name: values.get(config_item.name, "")
        for config_item in CONFIG_ITEMS
    }
    errors, warnings = validate_all(editable_values)

    print(f"Config: {config_path}")
    print(f"Editable parameters: {len(CONFIG_ITEMS)}")
    print(f"Parsed #define values: {len(values)}")

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if errors:
        print("Errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Self-test passed.")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Edit include/servo_config.h with a Tkinter GUI."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to servo_config.h.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Parse and validate the config file without opening the GUI.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    config_path = args.config.resolve()

    if args.self_test:
        return run_self_test(config_path)

    app = ServoConfiguratorApp(config_path)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
