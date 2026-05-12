from __future__ import annotations

import tkinter as tk
import time

from src.model.vehicle_model import VehicleModel
from src.ui.theme import status_color, COLORS
from src.validation.car_state_manager import get_car_state_manager


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
        self.sdc_status = tk.Label(self.top, font=("Roboto", 11, "bold"), fg="#f2f2f2", bg="#2a2a2a", anchor="w")
        self.vehicle_state = tk.Label(self.top, font=("Roboto", 22, "bold"), fg=COLORS["green"], bg="#2a2a2a", anchor="e")  # Verd unificat
        
        self.voltage.grid(row=0, column=0, sticky="ew", padx=6)
        self.temp.grid(row=0, column=1, sticky="ew", padx=6)
        self.sdc_status.grid(row=0, column=2, sticky="ew", padx=6)
        self.vehicle_state.grid(row=0, column=3, sticky="ew", padx=6)
        
        self.ts_line = tk.Frame(self, bg="#22C55E", height=10)
        self.ts_line.pack(fill="x", side="bottom")
        self._last_line_color = "#22C55E"
        self._last_state_color = "#22C55E"
        self._dark_mode = False

    def refresh(self, now: float | None = None) -> None:
        with self.model.lock():
            vehicle = self.model.vehicle
            voltage = vehicle.battery_voltage
            temp = vehicle.battery_temp
            
            # Obtenir estat del SDC
            sdc_bms_status = self.model._safe_signal_value("SDC", "SpSDCbms")
            sdc_imd_status = self.model._safe_signal_value("SDC", "SpSDCimd")
            
            # Determinar estat del SDC
            if sdc_bms_status > 0.5 and sdc_imd_status > 0.5:
                sdc_text = "SDC: ACTIVAT"
                sdc_color = COLORS["green"]
            elif sdc_bms_status > 0.5 and sdc_imd_status <= 0.5:
                sdc_text = "SDC: ERROR IMD"
                sdc_color = COLORS["red"]
            elif sdc_bms_status <= 0.5 and sdc_imd_status > 0.5:
                sdc_text = "SDC: ERROR BMS"
                sdc_color = COLORS["red"]
            else:
                sdc_text = "SDC: DESACTIVAT"
                sdc_color = COLORS["yellow"]
        
        # Obtenir estat actual del cotxe
        car_state_manager = get_car_state_manager()
        current_state = car_state_manager.get_current_state()
        
        self.voltage.config(text=f"Bateria: {voltage:.1f} V")
        self.temp.config(text=f"Temp Bateria: {temp:.1f} C")
        self.sdc_status.config(text=sdc_text, fg=sdc_color)
        
        # Actualitzar estat del vehicle amb colors i parpelleig
        t = now if now is not None else time.monotonic()
        
        if current_state == "INIT":
            # Verd fixe per INIT
            state_color = COLORS["green"]
            state_text = "INIT"
        elif current_state == "ACTIVE":
            # Vermell parpellejant a 2Hz per ACTIVE
            blink_on = int(t * 2.0) % 2 == 0
            state_color = COLORS["red"] if blink_on else "#1e1e1e" if self._dark_mode else "#DDD"
            state_text = "ACTIVE"
        elif current_state == "R2D":
            # Vermell parpellejant a 2Hz per R2D
            blink_on = int(t * 2.0) % 2 == 0
            state_color = COLORS["red"] if blink_on else "#1e1e1e" if self._dark_mode else "#DDD"
            state_text = "R2D"
        else:
            # Estat desconegut, verd per defecte
            state_color = COLORS["green"]
            state_text = "UNKNOWN"
        
        self.vehicle_state.config(text=state_text, fg=state_color)
        
        # Actualitzar colors en mode canvi
        if hasattr(self, 'vehicle_state'):
            if self._dark_mode:
                self.vehicle_state.configure(bg="#2a2a2a", fg=COLORS["green"])
                self.sdc_status.configure(bg="#2a2a2a", fg=sdc_color)
            else:
                self.vehicle_state.configure(bg="white", fg=COLORS["green"])
                self.sdc_status.configure(bg="white", fg=sdc_color)

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled
        if enabled:
            self.configure(bg="#1e1e1e")
            self.panel.configure(bg="#2a2a2a", highlightbackground="#3a3a3a")
            self.top.configure(bg="#2a2a2a")
            self.voltage.configure(bg="#2a2a2a", fg="#f2f2f2")
            self.temp.configure(bg="#2a2a2a", fg="#f2f2f2")
            self.sdc_status.configure(bg="#2a2a2a", fg="#f2f2f2")
            self.vehicle_state.configure(bg="#2a2a2a", fg=COLORS["green"])
        else:
            self.configure(bg="#DDD")
            self.panel.configure(bg="white", highlightbackground="#C8C8C8")
            self.top.configure(bg="white")
            self.voltage.configure(bg="white", fg="#1A1A1A")
            self.temp.configure(bg="white", fg="#1A1A1A")
            self.sdc_status.configure(bg="white", fg="#1A1A1A")
            self.vehicle_state.configure(bg="white", fg=COLORS["green"])
