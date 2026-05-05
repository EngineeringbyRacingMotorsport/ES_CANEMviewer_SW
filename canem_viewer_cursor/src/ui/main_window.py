from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from src.model.vehicle_model import VehicleModel
from src.services.pipeline import TelemetryPipeline
from src.ui.tabs import ConfigurationTab, GeneralTab, SDCTab, SensorTab, TemperatureTab
from src.ui.widgets.footer_bar import FooterBar


class MainWindow(tk.Tk):
    def __init__(self, model: VehicleModel, pipeline: TelemetryPipeline) -> None:
        super().__init__()
        self.model = model
        self.pipeline = pipeline
        self.title("CANEM Viewer - Formula Student EV")
        self.geometry("1400x800")
        self.minsize(1400, 800)
        self.maxsize(1400, 800)
        self.resizable(False, False)
        self.configure(bg="#1e1e1e")

        self.setup_styles()

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self.dynamic_frame = tk.Frame(self, bg="#1e1e1e")
        self.dynamic_frame.grid(row=0, column=0, sticky="nsew")
        self.footer = FooterBar(self, model=self.model)
        self.footer.grid(row=1, column=0, sticky="ew")

        self.notebook = ttk.Notebook(self.dynamic_frame)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(8, 8))

        self.tab_general = GeneralTab(self.notebook, model=self.model)
        self.tab_temps = TemperatureTab(self.notebook)
        self.tab_sdc = SDCTab(self.notebook, model=self.model)
        self.tab_sensor = SensorTab(self.notebook, model=self.model)
        self.tab_config = ConfigurationTab(self.notebook)
        self._dark_mode_enabled = True
        self._demo_enabled = True

        self.notebook.add(self.tab_general, text="General")
        self.notebook.add(self.tab_sensor, text="Sensòrica")
        self.notebook.add(self.tab_temps, text="Temperatures")
        self.notebook.add(self.tab_sdc, text="SDC")
        self.notebook.add(self.tab_config, text="Configuració")

        self.ui_refresh_ms = 250
        self.after(self.ui_refresh_ms, self._ui_tick)

    @staticmethod
    def setup_styles() -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#1e1e1e", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Montserrat", 11, "bold"), background="#2f2f2f")
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#1f1f1f"), ("!selected", "#2f2f2f")],
            foreground=[("selected", "#67d7c5"), ("!selected", "#d7d7d7")],
        )

    def _ui_tick(self) -> None:
        self._apply_config_runtime()
        self.tab_general.update_ui()
        self.tab_sensor.update_ui()
        self.tab_temps.update_ui()
        self.tab_sdc.update_ui()
        self.tab_config.update_ui()
        self.footer.refresh(now=time.monotonic())
        self.after(self.ui_refresh_ms, self._ui_tick)

    def _apply_config_runtime(self) -> None:
        new_refresh = int(self.tab_config.refresh_var.get())
        if new_refresh != self.ui_refresh_ms:
            self.ui_refresh_ms = new_refresh

        new_demo = bool(self.tab_config.demo_var.get())
        if new_demo != self._demo_enabled:
            self._demo_enabled = new_demo
            self.tab_sensor.set_demo_enabled(new_demo)
            self.tab_sdc.set_demo_enabled(new_demo)

        new_dark = bool(self.tab_config.dark_mode_var.get())
        if new_dark != self._dark_mode_enabled:
            self._dark_mode_enabled = new_dark
            self._set_dark_mode(new_dark)

    def _set_dark_mode(self, enabled: bool) -> None:
        if enabled:
            self.configure(bg="#1e1e1e")
            self.dynamic_frame.configure(bg="#1e1e1e")
            style = ttk.Style()
            style.configure("TNotebook", background="#1e1e1e")
            style.configure("TNotebook.Tab", background="#2f2f2f")
            style.map(
                "TNotebook.Tab",
                background=[("selected", "#1f1f1f"), ("!selected", "#2f2f2f")],
                foreground=[("selected", "#67d7c5"), ("!selected", "#d7d7d7")],
            )
        else:
            self.configure(bg="#DDD")
            self.dynamic_frame.configure(bg="#DDD")
            style = ttk.Style()
            style.configure("TNotebook", background="#DDD")
            style.configure("TNotebook.Tab", background="#CCC")
            style.map(
                "TNotebook.Tab",
                background=[("selected", "white"), ("!selected", "#CCC")],
                foreground=[("selected", "#0a594d"), ("!selected", "black")],
            )
        self.tab_general.set_dark_mode(enabled)
        self.tab_sensor.set_dark_mode(enabled)
        self.tab_temps.set_dark_mode(enabled)
        self.tab_sdc.set_dark_mode(enabled)
        self.tab_config.set_dark_mode(enabled)
        self.footer.set_dark_mode(enabled)
