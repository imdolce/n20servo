#!/usr/bin/env python3
"""Live dashboard for the n20servo CH32V003 serial CSV output."""

from __future__ import annotations

import argparse
import csv
import math
import queue
import random
import sys
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from tkinter import messagebox, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


ADC_FIELDS = [
    "sample",
    "raw",
    "avg16",
    "mv",
    "pct",
    "angle_deg",
    "direction_changes",
]
ADC_WITH_EXTRA_FIELDS = [
    "sample",
    "raw",
    "avg16",
    "mv",
    "pct",
    "angle_deg",
    "direction_changes",
    "extra",
]
RC_FIELDS = [
    "frame",
    "pulse_us",
    "period_us",
    "freq_hz",
    "valid",
    "sg90_deg",
    "n20_deg",
]
SERVO_FIELDS = [
    "sample",
    "target_deg",
    "angle_deg",
    "error_deg",
    "duty",
    "pulse_us",
    "valid",
]

FIELD_LABELS = {
    "sample": "Sample",
    "target_deg": "Target",
    "raw": "Raw ADC",
    "avg16": "Avg16 ADC",
    "mv": "Millivolts",
    "pct": "Percent",
    "angle_deg": "Angle",
    "error_deg": "Error",
    "duty": "Duty",
    "direction_changes": "Direction Changes",
    "frame": "Frame",
    "pulse_us": "Pulse",
    "period_us": "Period",
    "freq_hz": "Frequency",
    "valid": "Valid",
    "sg90_deg": "SG90 Angle",
    "n20_deg": "N20 Angle",
}

FIELD_UNITS = {
    "raw": "counts",
    "avg16": "counts",
    "mv": "mV",
    "pct": "%",
    "target_deg": "deg",
    "angle_deg": "deg",
    "error_deg": "deg",
    "duty": "0..1000",
    "pulse_us": "us",
    "period_us": "us",
    "freq_hz": "Hz",
    "sg90_deg": "deg",
    "n20_deg": "deg",
}

SERIES_COLORS = {
    "raw": "#d64f4f",
    "avg16": "#1d78b5",
    "mv": "#2d8a57",
    "pct": "#8e5fb8",
    "target_deg": "#1d78b5",
    "angle_deg": "#d09b22",
    "error_deg": "#d64f4f",
    "duty": "#8e5fb8",
    "direction_changes": "#5c6773",
    "pulse_us": "#1d78b5",
    "period_us": "#6c7782",
    "freq_hz": "#2d8a57",
    "valid": "#2d8a57",
    "sg90_deg": "#8e5fb8",
    "n20_deg": "#d09b22",
}


class TelemetryParser:
    """Parse both firmware CSV modes, with or without a printed header."""

    def __init__(self) -> None:
        self.mode: str | None = None
        self.fields: list[str] | None = None

    def parse_line(self, line: str) -> dict | None:
        line = line.strip()
        if not line:
            return None

        try:
            parts = next(csv.reader([line]))
        except csv.Error:
            return {"type": "log", "text": line}

        parts = [part.strip() for part in parts]
        lowered = [part.lower() for part in parts]

        if lowered == ADC_FIELDS:
            self.mode = "adc"
            self.fields = ADC_FIELDS
            return {"type": "header", "mode": self.mode, "fields": self.fields}

        if lowered == RC_FIELDS:
            self.mode = "rc"
            self.fields = RC_FIELDS
            return {"type": "header", "mode": self.mode, "fields": self.fields}

        if lowered == SERVO_FIELDS:
            self.mode = "servo"
            self.fields = SERVO_FIELDS
            return {"type": "header", "mode": self.mode, "fields": self.fields}

        fields = self._fields_for_parts(parts)
        if fields is None:
            return {"type": "log", "text": line}

        try:
            values = self._convert(fields, parts)
        except ValueError:
            return {"type": "log", "text": line}

        return {
            "type": "sample",
            "mode": self.mode,
            "fields": fields,
            "values": values,
            "line": line,
        }

    def _fields_for_parts(self, parts: list[str]) -> list[str] | None:
        if self.mode == "adc" and self.fields and len(parts) == len(self.fields):
            return self.fields

        if self.mode == "rc" and self.fields and len(parts) == len(self.fields):
            return self.fields

        if self.mode == "servo" and self.fields and len(parts) == len(self.fields):
            return self.fields

        if len(parts) == len(RC_FIELDS):
            if self._looks_like_rc_sample(parts):
                self.mode = "rc"
                self.fields = RC_FIELDS
                return RC_FIELDS

            if self._looks_like_servo_sample(parts):
                self.mode = "servo"
                self.fields = SERVO_FIELDS
                return SERVO_FIELDS

            self.mode = "adc"
            self.fields = ADC_FIELDS
            return ADC_FIELDS

        # Some older local firmware variants briefly printed raw+avg+... plus
        # an extra column. Keep this tolerant rather than dropping useful data.
        if len(parts) == len(ADC_WITH_EXTRA_FIELDS):
            self.mode = "adc"
            self.fields = ADC_WITH_EXTRA_FIELDS
            return ADC_WITH_EXTRA_FIELDS

        return None

    @staticmethod
    def _looks_like_rc_sample(parts: list[str]) -> bool:
        try:
            pulse_us = int(parts[1], 10)
            period_us = int(parts[2], 10)
            valid = int(parts[4], 10)
        except ValueError:
            return False

        return (
            500 <= pulse_us <= 2500
            and 10000 <= period_us <= 30000
            and valid in (0, 1)
        )

    @staticmethod
    def _looks_like_servo_sample(parts: list[str]) -> bool:
        try:
            target_deg = float(parts[1])
            angle_deg = float(parts[2])
            error_deg = float(parts[3])
            duty = int(parts[4], 10)
            pulse_us = int(parts[5], 10)
            valid = int(parts[6], 10)
        except ValueError:
            return False

        return (
            -180.0 <= target_deg <= 180.0
            and -180.0 <= angle_deg <= 180.0
            and -360.0 <= error_deg <= 360.0
            and 0 <= duty <= 1000
            and 0 <= pulse_us <= 2500
            and valid in (0, 1)
        )

    @staticmethod
    def _convert(fields: list[str], parts: list[str]) -> dict:
        values: dict[str, int | float | str] = {}
        for field, part in zip(fields, parts):
            if field in {
                "sample",
                "raw",
                "avg16",
                "mv",
                "direction_changes",
                "duty",
            }:
                values[field] = int(part, 10)
            elif field in {"frame", "pulse_us", "period_us", "valid"}:
                values[field] = int(part, 10)
            elif field in {
                "pct",
                "target_deg",
                "angle_deg",
                "error_deg",
                "freq_hz",
                "sg90_deg",
                "n20_deg",
            }:
                values[field] = float(part)
            else:
                values[field] = part
        return values


@dataclass(frozen=True)
class PanelSpec:
    title: str
    fields: tuple[str, ...]
    y_min: float
    y_max: float


PANEL_SPECS = {
    "adc": (
        PanelSpec("Angle", ("angle_deg",), 0.0, 333.0),
        PanelSpec("ADC", ("raw", "avg16"), 0.0, 1023.0),
        PanelSpec("Voltage", ("mv",), 0.0, 5000.0),
    ),
    "rc": (
        PanelSpec("Pulse", ("pulse_us",), 750.0, 2250.0),
        PanelSpec("Frequency", ("freq_hz",), 40.0, 60.0),
        PanelSpec("Angles", ("sg90_deg", "n20_deg"), -160.0, 160.0),
    ),
    "servo": (
        PanelSpec("Position", ("target_deg", "angle_deg"), -160.0, 160.0),
        PanelSpec("Error", ("error_deg",), -80.0, 80.0),
        PanelSpec("Output", ("duty",), 0.0, 1000.0),
    ),
}


class SerialWorker(threading.Thread):
    def __init__(
        self,
        *,
        events: queue.Queue,
        port: str,
        baud: int,
        demo: bool,
        demo_mode: str,
    ) -> None:
        super().__init__(daemon=True)
        self.events = events
        self.port = port
        self.baud = baud
        self.demo = demo
        self.demo_mode = demo_mode
        self.stop_event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        if self.demo:
            self._run_demo()
            return

        if serial is None:
            self.events.put(("error", "pyserial is not installed"))
            self.events.put(("closed", None))
            return

        try:
            with serial.Serial(self.port, self.baud, timeout=0.2) as ser:
                self.events.put(("status", f"Connected to {self.port} at {self.baud}"))
                while not self.stop_event.is_set():
                    raw_line = ser.readline()
                    if not raw_line:
                        continue
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if line:
                        self.events.put(("line", line))
        except Exception as exc:  # noqa: BLE001 - display serial failures to user.
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("closed", None))

    def _run_demo(self) -> None:
        sample = 0
        direction_changes = 0
        direction = 1
        angle = 0.0
        frame = 0
        target = 0.0

        mode = self.demo_mode
        if mode == "rc":
            header = ",".join(RC_FIELDS)
        elif mode == "servo":
            header = ",".join(SERVO_FIELDS)
        else:
            header = ",".join(ADC_FIELDS)
        self.events.put(("status", f"Demo {mode.upper()} stream"))
        self.events.put(("line", header))

        next_tick = time.monotonic()
        while not self.stop_event.is_set():
            now = time.monotonic()
            if now < next_tick:
                time.sleep(min(0.02, next_tick - now))
                continue

            if mode == "rc":
                pulse = int(1500 + 450 * math.sin(frame / 30.0))
                period = int(20000 + 150 * math.sin(frame / 11.0))
                freq = 1000000.0 / period
                sg90 = (pulse - 1500) * 90.0 / 500.0
                n20 = (pulse - 1500) * 150.0 / 500.0
                line = (
                    f"{frame},{pulse},{period},{freq:.1f},1,"
                    f"{sg90:+.1f},{n20:+.1f}"
                )
                frame += 1
            elif mode == "servo":
                target = 130.0 * math.sin(sample / 70.0)
                error = target - angle
                duty = 0 if abs(error) < 1.2 else min(1000, int(220 + abs(error) * 18))
                angle += max(-3.0, min(3.0, error * 0.08))
                pulse = int(1500 + target * 500.0 / 150.0)
                line = (
                    f"{sample},{target:+.1f},{angle:+.1f},{error:+.1f},"
                    f"{duty},{pulse},1"
                )
                sample += 1
            else:
                angle += direction * 4.5
                if angle >= 330.0:
                    angle = 330.0
                    direction = -1
                    direction_changes += 1
                elif angle <= 0.0:
                    angle = 0.0
                    direction = 1
                    direction_changes += 1

                avg = int((angle / 330.0) * 1023.0)
                raw = max(0, min(1023, avg + random.randint(-4, 4)))
                mv = int(avg * 5000 / 1023)
                pct = avg * 100.0 / 1023.0
                line = (
                    f"{sample},{raw},{avg},{mv},{pct:.1f},"
                    f"{angle:.1f},{direction_changes}"
                )
                sample += 1

            self.events.put(("line", line))
            next_tick += 0.02 if mode in {"rc", "servo"} else 0.01

        self.events.put(("closed", None))


class SerialDashboard(tk.Tk):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__()
        self.title("N20 Servo Serial Dashboard")
        self.geometry("1100x720")
        self.minsize(900, 580)

        self.args = args
        self.events: queue.Queue = queue.Queue()
        self.parser = TelemetryParser()
        self.worker: SerialWorker | None = None
        self.paused = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value="Disconnected")
        self.mode_text = tk.StringVar(value="Mode: waiting")
        self.rate_text = tk.StringVar(value="0.0 lines/s")
        self.port_var = tk.StringVar(value=args.port or self._default_port())
        self.baud_var = tk.StringVar(value=str(args.baud))
        self.demo_mode_var = tk.StringVar(value=args.demo_mode)

        self.current_mode: str | None = None
        self.latest_values: dict[str, int | float | str] = {}
        self.value_vars: dict[str, tk.StringVar] = {}
        self.histories: dict[str, deque[tuple[float, float]]] = {}
        self.max_points = args.max_points
        self.line_times: deque[float] = deque(maxlen=200)
        self.log_lines: deque[str] = deque(maxlen=200)

        self._build_ui()
        self._refresh_ports()

        if args.demo:
            self.after(200, self.start_demo)
        elif args.port:
            self.after(200, self.connect_serial)

        self.after(50, self._process_events)
        self.after(100, self._redraw_plots)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill=tk.X)

        ttk.Label(toolbar, text="Port").pack(side=tk.LEFT)
        self.port_combo = ttk.Combobox(
            toolbar,
            textvariable=self.port_var,
            width=14,
            values=[],
        )
        self.port_combo.pack(side=tk.LEFT, padx=(6, 12))

        ttk.Label(toolbar, text="Baud").pack(side=tk.LEFT)
        ttk.Entry(toolbar, textvariable=self.baud_var, width=10).pack(
            side=tk.LEFT, padx=(6, 12)
        )

        ttk.Button(toolbar, text="Refresh", command=self._refresh_ports).pack(
            side=tk.LEFT, padx=(0, 6)
        )
        self.connect_button = ttk.Button(
            toolbar, text="Connect", command=self.connect_serial
        )
        self.connect_button.pack(side=tk.LEFT, padx=(0, 6))
        self.disconnect_button = ttk.Button(
            toolbar, text="Disconnect", command=self.disconnect_serial, state=tk.DISABLED
        )
        self.disconnect_button.pack(side=tk.LEFT, padx=(0, 14))

        ttk.Label(toolbar, text="Demo").pack(side=tk.LEFT)
        ttk.Combobox(
            toolbar,
            textvariable=self.demo_mode_var,
            width=5,
            values=("adc", "rc", "servo"),
            state="readonly",
        ).pack(side=tk.LEFT, padx=(6, 6))
        ttk.Button(toolbar, text="Start Demo", command=self.start_demo).pack(
            side=tk.LEFT, padx=(0, 14)
        )

        ttk.Checkbutton(toolbar, text="Pause", variable=self.paused).pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Button(toolbar, text="Clear", command=self.clear_data).pack(side=tk.LEFT)

        status_bar = ttk.Frame(root, padding=(0, 8, 0, 8))
        status_bar.pack(fill=tk.X)
        ttk.Label(status_bar, textvariable=self.status_text).pack(side=tk.LEFT)
        ttk.Label(status_bar, textvariable=self.mode_text).pack(side=tk.LEFT, padx=(20, 0))
        ttk.Label(status_bar, textvariable=self.rate_text).pack(side=tk.LEFT, padx=(20, 0))

        body = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(body, padding=(0, 0, 10, 0))
        right = ttk.Frame(body)
        body.add(left, weight=1)
        body.add(right, weight=4)

        values_frame = ttk.LabelFrame(left, text="Latest Values", padding=10)
        values_frame.pack(fill=tk.X)
        self.values_inner = ttk.Frame(values_frame)
        self.values_inner.pack(fill=tk.X)
        ttk.Label(
            self.values_inner,
            text="Waiting for CSV data",
            foreground="#64707d",
        ).grid(row=0, column=0, sticky=tk.W)

        log_frame = ttk.LabelFrame(left, text="Raw Lines", padding=8)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.log_box = tk.Text(log_frame, height=12, wrap=tk.NONE, state=tk.DISABLED)
        self.log_box.pack(fill=tk.BOTH, expand=True)

        self.plot_canvas = tk.Canvas(
            right,
            background="#f6f8fa",
            highlightthickness=1,
            highlightbackground="#c9d1d9",
        )
        self.plot_canvas.pack(fill=tk.BOTH, expand=True)

    def _default_port(self) -> str:
        ports = self._available_ports()
        return ports[0] if ports else "COM3"

    def _available_ports(self) -> list[str]:
        if list_ports is None:
            return []
        return [port.device for port in list_ports.comports()]

    def _refresh_ports(self) -> None:
        ports = self._available_ports()
        self.port_combo.configure(values=ports)
        if ports and (not self.port_var.get() or self.port_var.get() == "COM3"):
            self.port_var.set(ports[0])

    def connect_serial(self) -> None:
        if self.worker is not None:
            return

        port = self.port_var.get().strip()
        if not port:
            messagebox.showerror("Missing Port", "Enter a COM port first.")
            return

        try:
            baud = int(self.baud_var.get().strip(), 10)
        except ValueError:
            messagebox.showerror("Invalid Baud", "Baud rate must be a number.")
            return

        self.clear_data()
        self._start_worker(port=port, baud=baud, demo=False, demo_mode="adc")

    def start_demo(self) -> None:
        if self.worker is not None:
            self.disconnect_serial()

        mode = self.demo_mode_var.get()
        self.clear_data()
        self._start_worker(port="", baud=0, demo=True, demo_mode=mode)

    def disconnect_serial(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.status_text.set("Disconnecting...")

    def _start_worker(self, *, port: str, baud: int, demo: bool, demo_mode: str) -> None:
        self.worker = SerialWorker(
            events=self.events,
            port=port,
            baud=baud,
            demo=demo,
            demo_mode=demo_mode,
        )
        self.worker.start()
        self.connect_button.configure(state=tk.DISABLED)
        self.disconnect_button.configure(state=tk.NORMAL)
        if demo:
            self.status_text.set(f"Starting {demo_mode.upper()} demo...")
        else:
            self.status_text.set(f"Opening {port}...")

    def clear_data(self) -> None:
        self.parser = TelemetryParser()
        self.current_mode = None
        self.latest_values = {}
        self.histories = {}
        self.line_times.clear()
        self.log_lines.clear()
        self.mode_text.set("Mode: waiting")
        self.rate_text.set("0.0 lines/s")
        self._rebuild_value_grid([])
        self._update_log_box()
        self.plot_canvas.delete("all")

    def _process_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "line":
                    self._handle_line(payload)
                elif event == "status":
                    self.status_text.set(str(payload))
                elif event == "error":
                    self.status_text.set(f"Error: {payload}")
                    messagebox.showerror("Serial Dashboard", str(payload))
                elif event == "closed":
                    self.worker = None
                    self.connect_button.configure(state=tk.NORMAL)
                    self.disconnect_button.configure(state=tk.DISABLED)
                    if not self.status_text.get().startswith("Error:"):
                        self.status_text.set("Disconnected")
        except queue.Empty:
            pass

        self._update_rate()
        self.after(50, self._process_events)

    def _handle_line(self, line: str) -> None:
        self.log_lines.append(line)
        parsed = self.parser.parse_line(line)
        if parsed is None:
            return

        if parsed["type"] == "header":
            self._set_mode(parsed["mode"], parsed["fields"])
            self._update_log_box()
            return

        if parsed["type"] != "sample":
            self._update_log_box()
            return

        if self.paused.get():
            self._update_log_box()
            return

        mode = parsed["mode"]
        fields = parsed["fields"]
        values = parsed["values"]
        self._set_mode(mode, fields)
        self.latest_values = values

        now = time.monotonic()
        self.line_times.append(now)
        for field, value in values.items():
            if isinstance(value, (int, float)) and field != "sample" and field != "frame":
                self.histories.setdefault(field, deque(maxlen=self.max_points)).append(
                    (now, float(value))
                )

        self._update_values()
        self._update_log_box()

    def _set_mode(self, mode: str, fields: list[str]) -> None:
        if mode == self.current_mode and all(field in self.value_vars for field in fields):
            return

        self.current_mode = mode
        self.mode_text.set(f"Mode: {mode.upper()}")
        self._rebuild_value_grid(fields)

    def _rebuild_value_grid(self, fields: list[str]) -> None:
        for child in self.values_inner.winfo_children():
            child.destroy()

        self.value_vars = {}
        if not fields:
            ttk.Label(
                self.values_inner,
                text="Waiting for CSV data",
                foreground="#64707d",
            ).grid(row=0, column=0, sticky=tk.W)
            return

        for row, field in enumerate(fields):
            label = FIELD_LABELS.get(field, field)
            unit = FIELD_UNITS.get(field, "")
            if unit:
                label = f"{label} ({unit})"
            var = tk.StringVar(value="-")
            self.value_vars[field] = var
            ttk.Label(self.values_inner, text=label).grid(
                row=row, column=0, sticky=tk.W, padx=(0, 12), pady=2
            )
            ttk.Label(self.values_inner, textvariable=var, font=("Consolas", 10)).grid(
                row=row, column=1, sticky=tk.E, pady=2
            )

        self.values_inner.columnconfigure(1, weight=1)

    def _update_values(self) -> None:
        for field, value in self.latest_values.items():
            var = self.value_vars.get(field)
            if var is None:
                continue
            if isinstance(value, float):
                var.set(f"{value:.1f}")
            else:
                var.set(str(value))

    def _update_rate(self) -> None:
        now = time.monotonic()
        while self.line_times and now - self.line_times[0] > 5.0:
            self.line_times.popleft()
        if len(self.line_times) < 2:
            self.rate_text.set("0.0 lines/s")
            return
        elapsed = max(0.001, self.line_times[-1] - self.line_times[0])
        self.rate_text.set(f"{(len(self.line_times) - 1) / elapsed:.1f} lines/s")

    def _update_log_box(self) -> None:
        self.log_box.configure(state=tk.NORMAL)
        self.log_box.delete("1.0", tk.END)
        self.log_box.insert(tk.END, "\n".join(self.log_lines))
        self.log_box.see(tk.END)
        self.log_box.configure(state=tk.DISABLED)

    def _redraw_plots(self) -> None:
        self.plot_canvas.delete("plot")
        width = max(1, self.plot_canvas.winfo_width())
        height = max(1, self.plot_canvas.winfo_height())

        mode = self.current_mode
        if mode not in PANEL_SPECS:
            self._draw_empty_plot(width, height)
        else:
            self._draw_panels(width, height, PANEL_SPECS[mode])

        self.after(100, self._redraw_plots)

    def _draw_empty_plot(self, width: int, height: int) -> None:
        self.plot_canvas.create_text(
            width / 2,
            height / 2,
            text="Waiting for serial CSV data",
            fill="#64707d",
            font=("Segoe UI", 14),
            tags="plot",
        )

    def _draw_panels(
        self,
        width: int,
        height: int,
        panels: tuple[PanelSpec, ...],
    ) -> None:
        margin_left = 62
        margin_right = 22
        margin_top = 18
        margin_bottom = 26
        gap = 18
        panel_height = max(
            80,
            int((height - margin_top - margin_bottom - gap * (len(panels) - 1)) / len(panels)),
        )
        x0 = margin_left
        x1 = width - margin_right
        now = time.monotonic()
        window_seconds = 12.0

        for index, panel in enumerate(panels):
            y0 = margin_top + index * (panel_height + gap)
            y1 = y0 + panel_height
            self._draw_panel_frame(panel, x0, y0, x1, y1)
            self._draw_panel_series(panel, x0, y0, x1, y1, now, window_seconds)

    def _draw_panel_frame(self, panel: PanelSpec, x0: int, y0: int, x1: int, y1: int) -> None:
        self.plot_canvas.create_rectangle(
            x0,
            y0,
            x1,
            y1,
            outline="#d0d7de",
            fill="#ffffff",
            tags="plot",
        )
        self.plot_canvas.create_text(
            x0,
            y0 - 5,
            text=panel.title,
            anchor=tk.SW,
            fill="#24292f",
            font=("Segoe UI", 10, "bold"),
            tags="plot",
        )
        for fraction in (0.25, 0.5, 0.75):
            y = y0 + (y1 - y0) * fraction
            self.plot_canvas.create_line(x0, y, x1, y, fill="#edf1f5", tags="plot")

        y_mid = (panel.y_min + panel.y_max) / 2.0
        for value, y in ((panel.y_max, y0), (y_mid, (y0 + y1) / 2), (panel.y_min, y1)):
            self.plot_canvas.create_text(
                x0 - 8,
                y,
                text=self._format_axis(value),
                anchor=tk.E,
                fill="#64707d",
                font=("Consolas", 8),
                tags="plot",
            )

        legend_x = x1 - 12
        for field in reversed(panel.fields):
            color = SERIES_COLORS.get(field, "#0969da")
            label = FIELD_LABELS.get(field, field)
            self.plot_canvas.create_text(
                legend_x,
                y0 + 13,
                text=label,
                anchor=tk.E,
                fill=color,
                font=("Segoe UI", 9),
                tags="plot",
            )
            legend_x -= max(74, len(label) * 7)

    def _draw_panel_series(
        self,
        panel: PanelSpec,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        now: float,
        window_seconds: float,
    ) -> None:
        y_span = max(0.001, panel.y_max - panel.y_min)
        x_span = max(1, x1 - x0)

        for field in panel.fields:
            points = []
            for timestamp, value in self.histories.get(field, ()):
                age = now - timestamp
                if age > window_seconds:
                    continue

                clipped = max(panel.y_min, min(panel.y_max, value))
                x = x1 - (age / window_seconds) * x_span
                y = y1 - ((clipped - panel.y_min) / y_span) * (y1 - y0)
                points.extend((x, y))

            if len(points) >= 4:
                self.plot_canvas.create_line(
                    *points,
                    fill=SERIES_COLORS.get(field, "#0969da"),
                    width=2,
                    tags="plot",
                )

    @staticmethod
    def _format_axis(value: float) -> str:
        if abs(value) >= 100 or float(value).is_integer():
            return f"{value:.0f}"
        return f"{value:.1f}"

    def _on_close(self) -> None:
        if self.worker is not None:
            self.worker.stop()
        self.destroy()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Live dashboard for n20servo serial CSV data.",
    )
    parser.add_argument("--port", help="Serial port, for example COM5")
    parser.add_argument("--baud", type=int, default=921600, help="Serial baud rate")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run with generated data instead of opening a serial port",
    )
    parser.add_argument(
        "--demo-mode",
        choices=("adc", "rc", "servo"),
        default="servo",
        help="Generated data mode used with --demo",
    )
    parser.add_argument(
        "--max-points",
        type=int,
        default=800,
        help="Maximum points kept per plotted series",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run parser checks and exit without opening the UI",
    )
    return parser


def run_self_test() -> int:
    parser = TelemetryParser()
    samples = [
        (
            "adc",
            "0,512,513,2507,50.1,165.5,3",
            {"sample": 0, "avg16": 513, "angle_deg": 165.5},
        ),
        (
            "rc",
            "frame,pulse_us,period_us,freq_hz,valid,sg90_deg,n20_deg",
            {},
        ),
        (
            "rc",
            "42,1500,20000,50.0,1,+0.0,+0.0",
            {"frame": 42, "pulse_us": 1500, "n20_deg": 0.0},
        ),
        (
            "servo",
            "sample,target_deg,angle_deg,error_deg,duty,pulse_us,valid",
            {},
        ),
        (
            "servo",
            "9,+45.0,+41.2,+3.8,337,1650,1",
            {"sample": 9, "target_deg": 45.0, "error_deg": 3.8, "duty": 337},
        ),
    ]

    for expected_mode, line, expected_values in samples:
        parsed = parser.parse_line(line)
        if parsed is None:
            print(f"failed to parse: {line}", file=sys.stderr)
            return 1
        if parsed["mode"] != expected_mode:
            print(f"wrong mode for {line}: {parsed['mode']}", file=sys.stderr)
            return 1
        values = parsed.get("values", {})
        for key, expected in expected_values.items():
            if values.get(key) != expected:
                print(
                    f"wrong value for {key}: got {values.get(key)!r}, expected {expected!r}",
                    file=sys.stderr,
                )
                return 1

    print("serial_dashboard parser self-test passed")
    return 0


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.self_test:
        return run_self_test()

    app = SerialDashboard(args)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
