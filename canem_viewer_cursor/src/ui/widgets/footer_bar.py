from __future__ import annotations

import tkinter as tk
import time

from src.model.vehicle_model import VehicleModel
from src.ui.theme import status_color


class FooterBar(tk.Frame):
    def __init__(self, parent: tk.Widget, model: VehicleModel) -> None:
        super().__init__(parent, bg="#1e1e1e", padx=12, pady=8)
        self.model = model

        self.panel = tk.Frame(self, bg="#2a2a2a", highlightbackground="#3a3a3a", highlightthickness=1)
        self.panel.pack(fill="both", expand=True)

        self.top = tk.Frame(self.panel, bg="#2a2a2a")
        self.top.pack(fill="x", padx=12, pady=(8, 4))
        self.top.grid_columnconfigure(0, weight=1)
        self.top.grid_columnconfigure(1, weight=1)
        self.top.grid_columnconfigure(2, weight=1)
        self.top.grid_columnconfigure(3, weight=1)

        self.voltage = tk.Label(self.top, font=("Roboto", 11, "bold"), fg="#f2f2f2", bg="#2a2a2a", anchor="w")
        self.temp = tk.Label(self.top, font=("Roboto", 11, "bold"), fg="#f2f2f2", bg="#2a2a2a", anchor="w")
        self.traction = tk.Label(self.top, font=("Roboto", 11, "bold"), fg="#f2f2f2", bg="#2a2a2a", anchor="w")
        self.status = tk.Label(self.top, font=("Roboto", 11, "bold"), fg="#f2f2f2", bg="#2a2a2a", anchor="w")
        self.alerts = tk.Label(
            self.panel,
            font=("Roboto", 10),
            fg="#d0d0d0",
            bg="#2a2a2a",
            anchor="w",
            justify="left",
        )

        self.voltage.grid(row=0, column=0, sticky="ew", padx=6)
        self.temp.grid(row=0, column=1, sticky="ew", padx=6)
        self.traction.grid(row=0, column=2, sticky="ew", padx=6)
        self.status.grid(row=0, column=3, sticky="ew", padx=6)
        self.alerts.pack(fill="x", padx=18, pady=(0, 8))

        self.ts_line = tk.Frame(self, bg="#22C55E", height=10)
        self.ts_line.pack(fill="x", side="bottom")
        self._last_line_color = "#22C55E"
        self._dark_mode = True

    def refresh(self, now: float | None = None) -> None:
        with self.model.lock():
            vehicle = self.model.vehicle
            voltage = vehicle.battery_voltage
            temp = vehicle.battery_temp
            traction_on = vehicle.traction_on
            traction = "ON" if traction_on else "OFF"
            global_status = vehicle.global_status
            alerts = vehicle.critical_alerts

        self.voltage.config(text=f"Bateria: {voltage:.1f} V")
        self.temp.config(text=f"Temp Bateria: {temp:.1f} C")
        self.traction.config(text=f"TS: {traction}", fg="#C62828" if traction_on else "#2E7D32")
        self.status.config(text=f"Vehicle: {global_status}", fg=status_color(global_status))
        self.alerts.config(text=" | ".join(alerts) if alerts else "Sense alertes crítiques")

        t = now if now is not None else time.monotonic()
        if traction_on:
            # 1 Hz blinking: full cycle 1000 ms, toggling every 500 ms.
            blink_on = int(t * 2.0) % 2 == 0
            line_color = "#D32F2F" if blink_on else ("#1e1e1e" if self._dark_mode else "#DDD")
        else:
            line_color = "#2E7D32"

        if line_color != self._last_line_color:
            self.ts_line.config(bg=line_color)
            self._last_line_color = line_color

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled
        if enabled:
            self.configure(bg="#1e1e1e")
            self.panel.configure(bg="#2a2a2a", highlightbackground="#3a3a3a")
            self.top.configure(bg="#2a2a2a")
            self.voltage.configure(bg="#2a2a2a", fg="#f2f2f2")
            self.temp.configure(bg="#2a2a2a", fg="#f2f2f2")
            self.traction.configure(bg="#2a2a2a", fg="#f2f2f2")
            self.status.configure(bg="#2a2a2a", fg="#f2f2f2")
            self.alerts.configure(bg="#2a2a2a", fg="#d0d0d0")
        else:
            self.configure(bg="#DDD")
            self.panel.configure(bg="white", highlightbackground="#C8C8C8")
            self.top.configure(bg="white")
            self.voltage.configure(bg="white", fg="#1A1A1A")
            self.temp.configure(bg="white", fg="#1A1A1A")
            self.traction.configure(bg="white", fg="#1A1A1A")
            self.status.configure(bg="white", fg="#1A1A1A")
            self.alerts.configure(bg="white", fg="#1A1A1A")
