from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from src.model.vehicle_model import VehicleModel
from src.services.pipeline import TelemetryPipeline
from src.ui.tabs import ConfigurationTab, GeneralTab, SDCTab, TemperatureTab
from src.ui.widgets.footer_bar import FooterBar
from src.ui.widgets.logo import LogoWidget


class MainWindow(tk.Tk):
    def __init__(self, model: VehicleModel, pipeline: TelemetryPipeline) -> None:
        super().__init__()
        self.model = model
        self.pipeline = pipeline
        
        self.title("CANEM Viewer - EUSS Motorsport")
        self.geometry("1400x800")
        self.minsize(1400, 800)
        self.maxsize(1400, 800)
        self.resizable(False, False)
        self.configure(bg="#DDD")

        self.setup_styles()

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self.dynamic_frame = tk.Frame(self, bg="#DDD")
        self.dynamic_frame.grid(row=0, column=0, sticky="nsew")
        self.footer = FooterBar(self, model=self.model)
        self.footer.grid(row=1, column=0, sticky="ew")
        
        # Afegir logos
        self._setup_logos()
        
        self.notebook = ttk.Notebook(self.dynamic_frame)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(8, 8))

        self.tab_general = GeneralTab(self.notebook, model=self.model)
        self.tab_temps = TemperatureTab(self.notebook)
        self.tab_sdc = SDCTab(self.notebook, model=self.model)
        self.tab_config = ConfigurationTab(self.notebook)
        self._dark_mode_enabled = False
        self._demo_enabled = True

        self.notebook.add(self.tab_general, text="General")
        self.notebook.add(self.tab_temps, text="Temperatures")
        self.notebook.add(self.tab_sdc, text="SDC")
        self.notebook.add(self.tab_config, text="Configuració")

        # Aplicar mode inicial (light mode per defecte)
        self._set_dark_mode(False)

        # Configurar icona de la finestra
        self._set_window_icon()

        self.ui_refresh_ms = 250
        self.after(self.ui_refresh_ms, self._ui_tick)

    def _setup_logos(self) -> None:
        """Configura els logos a diferents ubicacions"""
        self.taskbar_logo = LogoWidget(self, with_text=False, size=(16, 16))

    def _set_window_icon(self) -> None:
        """Configura la icona de la finestra"""
        try:
            import os
            ico_path = "assets/logo_no_text.ico"
            if os.path.exists(ico_path):
                from PIL import Image, ImageTk
                img = Image.open(ico_path)
                if img.size != (32, 32):
                    img = img.resize((32, 32), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.iconphoto(False, photo)
                self.window_icon = photo
                return
        except Exception:
            pass
        
        # Fallback: icona verd sòlida
        try:
            green_icon = tk.PhotoImage(width=32, height=32)
            for x in range(32):
                for y in range(32):
                    green_icon.put("#22C55E", (x, y))
            self.iconphoto(False, green_icon)
            self.window_icon = green_icon
        except Exception:
            pass

    @staticmethod
    def setup_styles() -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#DDD", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Montserrat", 11, "bold"), background="#CCC")
        style.map(
            "TNotebook.Tab",
            background=[("selected", "white"), ("!selected", "#CCC")],
            foreground=[("selected", "#0a594d"), ("!selected", "black")],
        )

    def _ui_tick(self) -> None:
        self._apply_config_runtime()
        self.tab_general.update_ui()
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
        
        # Actualitzar colors dels logos
        bg_color = "#1e1e1e" if enabled else "#DDD"
        if hasattr(self, 'taskbar_logo'):
            self.taskbar_logo.update_background(bg_color)
        
        self.tab_general.set_dark_mode(enabled)
        self.tab_temps.set_dark_mode(enabled)
        self.tab_sdc.set_dark_mode(enabled)
        self.tab_config.set_dark_mode(enabled)
        self.footer.set_dark_mode(enabled)
