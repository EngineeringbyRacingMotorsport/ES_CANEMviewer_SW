from __future__ import annotations

import json
import math
import time
from collections import deque
from queue import Empty
from typing import Optional, Tuple

import tkinter as tk
from tkinter import ttk

from src.model.vehicle_model import PCBState, VehicleModel
from src.validation.car_state_manager import get_car_state_manager

DARK_BG = "#1e1e1e"
CARD_BG = "#2a2a2a"
CARD_BORDER = "#3a3a3a"
TEXT_MAIN = "#f2f2f2"
TEXT_MUTED = "#bdbdbd"


class GeneralTab(tk.Frame):
    def __init__(self, parent: tk.Widget, model: VehicleModel):
        super().__init__(parent, bg=DARK_BG)
        self.model = model
        self.main_container = tk.Frame(self, bg=DARK_BG)
        self.main_container.pack(fill="both", expand=True)

        self.current_view = "grid"
        self.active_placa: str | None = None
        self.active_signal: str | None = None
        self.grid_bodies: dict[str, tk.Frame] = {}
        self._grid_widget_rows: dict[str, list[dict[str, tk.Label]]] = {}
        self.detail_table_body: tk.Frame | None = None
        self.detail_rows_widgets: list[dict[str, tk.Widget]] = []
        self.detail_signal_info: dict[str, tk.Widget] = {}
        self._grid_rows_cache: dict[str, list[tuple[str, str, str, str]]] = {}
        self._detail_rows_cache: list[tuple[str, str, str, str]] = []
        self._plot_refresh_interval_s = 0.5
        self._last_plot_draw_s = 0.0
        self._last_plot_signal: str | None = None
        self._last_plot_canvas_size: tuple[int, int] = (0, 0)
        self._dark_mode = True

        self.show_grid_view()

    def show_grid_view(self) -> None:
        self.current_view = "grid"
        self.active_placa = None
        self.active_signal = None
        self.detail_table_body = None
        self.detail_rows_widgets = []
        self.detail_signal_info = {}
        self._detail_rows_cache = []
        self._last_plot_draw_s = 0.0
        self._last_plot_signal = None
        self._last_plot_canvas_size = (0, 0)

        for widget in self.main_container.winfo_children():
            widget.destroy()

        self.grid_bodies = {}
        self._grid_widget_rows = {}
        
        # Get PCBs from model (initialized from DBC)
        with self.model.lock():
            pcb_names = list(self.model.vehicle.pcbs.keys())
        
        if not pcb_names:
            # Fallback to default titles if no PCBs loaded
            pcb_names = ["NO DATA"]
        
        num_cols = min(5, len(pcb_names))
        num_rows = (len(pcb_names) + num_cols - 1) // num_cols

        for col in range(num_cols):
            self.main_container.columnconfigure(col, weight=1)
        for row in range(num_rows):
            self.main_container.rowconfigure(row, weight=1)

        for i, title in enumerate(pcb_names):
            row, col = i // num_cols, i % num_cols
            container = tk.Frame(self.main_container, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
            container.grid(row=row, column=col, sticky="nsew", padx=1, pady=1)

            header = tk.Button(
                container,
                text=title,
                command=lambda t=title: self.show_detail_view(t),
                bg="#0a594d",
                fg="white",
                font=("Arial", 10, "bold"),
                relief="flat",
                cursor="hand2",
                activebackground="#084239",
            )
            header.pack(fill="x")

            body = tk.Frame(container, bg=CARD_BG)
            body.pack(fill="both", expand=True, padx=6, pady=4)
            self.grid_bodies[title] = body
            self._grid_widget_rows[title] = []
            self._grid_rows_cache[title] = []

    def show_detail_view(self, title: str) -> None:
        self.current_view = "detail"
        self.active_placa = title
        self.active_signal = None
        self._last_plot_draw_s = 0.0
        self._last_plot_signal = None
        self._last_plot_canvas_size = (0, 0)

        # Determinem la paleta de colors segons el mode
        bg_main = DARK_BG if self._dark_mode else "#f0f0f0"
        bg_card = CARD_BG if self._dark_mode else "#ffffff"
        fg_text = TEXT_MAIN if self._dark_mode else "#1a1a1a"
        fg_muted = TEXT_MUTED if self._dark_mode else "#666666"
        border_color = CARD_BORDER if self._dark_mode else "#d0d0d0"
        header_bg = "#0a594d" # Color corporatiu, es manté igual

        for widget in self.main_container.winfo_children():
            widget.destroy()

        # Reset de la configuració del grid per a la vista de detall
        for i in range(5):
            self.main_container.columnconfigure(i, weight=0, minsize=0)
            self.main_container.rowconfigure(i, weight=0, minsize=0)

        self.main_container.columnconfigure(0, weight=1)
        self.main_container.rowconfigure(1, weight=1)

        # --- CAPÇALERA ---
        header = tk.Frame(self.main_container, bg=header_bg, height=60)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        tk.Button(
            header,
            text="← TORNAR",
            command=self.show_grid_view,
            bg=header_bg,
            fg="white",
            font=("Arial", 10, "bold"),
            relief="flat",
            cursor="hand2",
            activebackground="#084239",
        ).pack(side="left", padx=20)

        tk.Label(
            header,
            text=f"DETALL DEL SISTEMA: {title}",
            font=("Arial", 14, "bold"),
            bg=header_bg,
            fg="white",
        ).pack(side="left", expand=True, padx=(0, 100))

        # --- CONTINGUT PRINCIPAL ---
        content = tk.Frame(self.main_container, bg=bg_main)
        content.grid(row=1, column=0, sticky="nsew", padx=20, pady=20)
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=0)  # Panell esquerre sense expandir
        content.grid_columnconfigure(1, weight=1)  # Panell dret ocupa tota la resta

        # Panell Esquerre (Llista de senyals) amb scrollbar
        left_panel = tk.Frame(content, bg=bg_card, highlightbackground=border_color, highlightthickness=1)
        left_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left_panel.grid_rowconfigure(0, weight=1)
        left_panel.grid_columnconfigure(0, weight=1)  # Canvas ocupa tot l'espai
        left_panel.grid_columnconfigure(1, weight=0, minsize=15)  # Scrollbar amb amplada fixa

        # Crear scrollbar amb amplada fixa
        scrollbar = tk.Scrollbar(left_panel, orient="vertical", width=15)
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Configurar el canvas per fer scroll
        canvas = tk.Canvas(left_panel, bg=bg_card, highlightthickness=0, yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        scrollbar.config(command=canvas.yview)
        
        self.detail_table_body = tk.Frame(canvas, bg=bg_card)
        canvas_window = canvas.create_window((0, 0), window=self.detail_table_body, anchor="nw", width=canvas.winfo_width() - scrollbar.winfo_width())
        
        self.detail_rows_widgets = []

        # Configurar el scroll per actualitzar-se quan canviï el contingut
        def configure_scroll_region(e=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # Actualitzar l'amplada de la finestra per ocupar tot l'espai
            if canvas.winfo_width() > 1:
                canvas.itemconfig(canvas_window, width=canvas.winfo_width() - scrollbar.winfo_width())
        
        self.detail_table_body.bind("<Configure>", configure_scroll_region)
        canvas.bind("<Configure>", configure_scroll_region)

        # Panell Dret (Detalls i Gràfica)
        right_panel = tk.Frame(content, bg=bg_card, highlightbackground=border_color, highlightthickness=1)
        right_panel.grid(row=0, column=1, sticky="nsew")
        right_panel.grid_rowconfigure(0, weight=0)  # Secció superior (info + config)
        right_panel.grid_rowconfigure(1, weight=2)  # Gràfica (més espai)
        right_panel.grid_columnconfigure(0, weight=1)

        # Secció superior (info + configuració)
        top_section = tk.Frame(right_panel, bg=bg_card)
        top_section.grid(row=0, column=0, sticky="nsew", padx=12, pady=(10, 6))
        top_section.grid_columnconfigure(0, weight=1)  # Columna info
        top_section.grid_columnconfigure(1, weight=0)  # Columna configuració

        # Columna esquerra: Informació de la dada (una única columna)
        info_frame = tk.Frame(top_section, bg=bg_card)
        info_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        
        # Títol del senyal
        name_label = tk.Label(info_frame, bg=bg_card, fg="#4dd0ba", font=("Segoe UI", 16, "bold"), anchor="w")
        name_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
        
        # Informació en columna única
        code_label = tk.Label(info_frame, bg=bg_card, fg=fg_text, font=("Segoe UI", 10), anchor="w")
        code_label.grid(row=1, column=0, sticky="w", pady=(0, 2))
        
        minmax_label = tk.Label(info_frame, bg=bg_card, fg=fg_text, font=("Segoe UI", 10), anchor="w")
        minmax_label.grid(row=2, column=0, sticky="w", pady=(0, 2))
        
        desc_label = tk.Label(info_frame, bg=bg_card, fg=fg_muted, font=("Segoe UI", 10), 
                             anchor="nw", justify="left", wraplength=400)
        desc_label.grid(row=3, column=0, sticky="w", pady=(0, 0))

        # Columna dreta: Configuració dels estats
        config_frame = tk.Frame(top_section, bg=bg_card, highlightbackground=border_color, highlightthickness=1)
        self.signal_config_frame = config_frame
        config_frame.grid(row=0, column=1, sticky="ne")
        
        # Títol de configuració
        config_title = tk.Label(config_frame, bg=bg_card, fg="#4dd0ba", font=("Segoe UI", 10, "bold"), text="Configuració d'Estats")
        config_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=(6, 6), pady=(4, 4))
        
        # Frame per estats
        values_frame = tk.Frame(config_frame, bg=bg_card)
        values_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=(6, 6), pady=(0, 4))
        
        # Capçaleres
        tk.Label(values_frame, bg=bg_card, fg=fg_text, font=("Segoe UI", 9, "bold"), text="Estat").grid(row=0, column=0, padx=2, pady=2)
        tk.Label(values_frame, bg=bg_card, fg=fg_text, font=("Segoe UI", 9, "bold"), text="Mode").grid(row=0, column=1, padx=2, pady=2)
        
        # Configuració per estat
        self.signal_config_widgets = {}
        self._create_signal_config_widgets(values_frame)
        
        # Botó de guardar
        save_button = tk.Button(config_frame, text="Guardar", bg="#4dd0ba", fg="white", font=("Segoe UI", 9, "bold"),
                               command=self._save_all_signal_config, width=10)
        save_button.grid(row=2, column=0, columnspan=2, sticky="ew", padx=(6, 6), pady=(4, 6))

        # Canvas per a la gràfica (part inferior)
        plot_bg = "#222222" if self._dark_mode else "#ffffff"
        plot_canvas = tk.Canvas(
            right_panel, 
            bg=plot_bg, 
            highlightbackground=border_color, 
            highlightthickness=1
        )
        plot_canvas.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self.detail_signal_info = {
            "name": name_label,
            "code": code_label,
            "minmax": minmax_label,
            "desc": desc_label,
            "plot": plot_canvas,
        }

    def update_ui(self) -> None:
        if self.current_view == "grid":
            self._update_grid()
        else:
            self._update_detail()

    def _update_grid(self) -> None:
        with self.model.lock():
            pcbs = self.model.vehicle.pcbs
            for title in list(self.grid_bodies.keys()):
                body = self.grid_bodies.get(title)
                if body is None:
                    continue
                pcb = pcbs.get(title)
                rows = self._build_grid_rows(pcb)
                self._sync_grid_rows(title, body, rows, self._grid_rows_cache.get(title, []))
                self._grid_rows_cache[title] = rows

    def _update_detail(self) -> None:
        if self.active_placa is None or self.detail_table_body is None:
            return
        with self.model.lock():
            pcb = self.model.vehicle.pcbs.get(self.active_placa)
            rows = self._build_detail_rows(pcb)
        self._sync_detail_rows(self.detail_table_body, rows, self._detail_rows_cache)
        self._detail_rows_cache = rows
        self._refresh_signal_panel(pcb)

    def _build_grid_rows(self, pcb: PCBState | None) -> list[tuple[str, str, str, str]]:
        if pcb is None:
            return [("No signals", "-", "-", "TIMEOUT")]
        
        # Define priority order: TIMEOUT (3) > ERROR (2) > WARNING (1) > OK (0)
        PRIORITY_ORDER = {"TIMEOUT": 3, "ERROR": 2, "WARNING": 1, "OK": 0}
        
        # Group signals by status and sort alphabetically within each group
        status_groups = {"TIMEOUT": [], "ERROR": [], "WARNING": [], "OK": []}
        for signal in pcb.signals.values():
            status_groups[signal.status].append(signal)
        
        # Sort signals alphabetically within each status group
        for status in status_groups:
            status_groups[status].sort(key=lambda s: s.name.lower())
        
        # Build ordered list by priority
        ordered_signals = []
        for status in ["TIMEOUT", "ERROR", "WARNING", "OK"]:
            ordered_signals.extend(status_groups[status])
        
        # Limit to available space (show max 9 signals in grid view)
        max_signals = 9
        rows: list[tuple[str, str, str, str]] = []
        
        for signal in ordered_signals[:max_signals]:
            # Show "--" for timeout signals instead of actual value
            if signal.status == "TIMEOUT":
                value = "--"
            else:
                value = f"{signal.value:.2f}"
            rows.append((signal.name, value, signal.unit, signal.status))
        
        if not rows:
            rows.append(("No signals", "-", "-", "TIMEOUT"))
        return rows

    def _build_detail_rows(self, pcb: PCBState | None) -> list[tuple[str, str, str, str]]:
        if pcb is None:
            return [("NO_DATA", "-", "-", "TIMEOUT")]
        
        # Define priority order: TIMEOUT (3) > ERROR (2) > WARNING (1) > OK (0)
        # Group signals by status and sort alphabetically within each group
        status_groups = {"TIMEOUT": [], "ERROR": [], "WARNING": [], "OK": []}
        for signal in pcb.signals.values():
            status_groups[signal.status].append(signal)
        
        # Sort signals alphabetically within each status group
        for status in status_groups:
            status_groups[status].sort(key=lambda s: s.name.lower())
        
        # Build ordered list by priority
        ordered_signals = []
        for status in ["TIMEOUT", "ERROR", "WARNING", "OK"]:
            ordered_signals.extend(status_groups[status])
        
        rows: list[tuple[str, str, str, str]] = []
        for signal in ordered_signals:
            # Show "--" for timeout signals instead of actual value
            if signal.status == "TIMEOUT":
                value = "--"
            else:
                value = f"{signal.value:.5f}"
            rows.append((signal.name, value, signal.unit, signal.status))
        
        return rows or [("NO_DATA", "-", "-", "TIMEOUT")]

    def _sync_grid_rows(
        self,
        title: str,
        body: tk.Frame,
        rows: list[tuple[str, str, str, str]],
        previous_rows: list[tuple[str, str, str, str]],
    ) -> None:
        widgets = self._grid_widget_rows[title]

        # Definim els colors base segons el mode actual
        # TEXT_MAIN sol ser blanc/gris clar en dark mode, així que posem un contrast per light mode
        base_bg = "#303030" if self._dark_mode else "#f5f5f5"
        base_fg = TEXT_MAIN if self._dark_mode else "#1a1a1a"

        # 1. Eliminar widgets sobrants si la llista de senyals s'ha reduït
        while len(widgets) > len(rows):
            row_widgets = widgets.pop()
            row_widgets["frame"].destroy()

        # 2. Crear nous widgets si hi ha més senyals que abans
        while len(widgets) < len(rows):
            frame = tk.Frame(body, bg=base_bg)
            frame.pack(fill="x", pady=1)
            
            name = tk.Label(frame, anchor="w", bg=base_bg, fg=base_fg, font=("Segoe UI", 10, "bold"))
            name.pack(side="left", fill="x", expand=True, padx=(6, 6), pady=2)
            
            value = tk.Label(frame, anchor="e", width=7, bg=base_bg, fg=base_fg, font=("Segoe UI", 10))
            value.pack(side="left", padx=(0, 6), pady=2)
            
            unit = tk.Label(frame, anchor="w", width=5, bg=base_bg, fg=base_fg, font=("Segoe UI", 10))
            unit.pack(side="left", padx=(0, 6), pady=2)
            
            widgets.append({"frame": frame, "name": name, "value": value, "unit": unit})

        # 3. Actualitzar contingut i estils (colors) de cada fila
        for i, row in enumerate(rows):
            signal_name, value, unit, status = row
            bg = self._status_bg(status)
            row_widgets = widgets[i]
            
            # Forcem l'actualització de colors de text per si s'ha canviat el mode
            # i l'actualització de fons segons l'estat (OK, WARN, ERROR)
            row_widgets["frame"].config(bg=bg)
            
            row_widgets["name"].config(
                text=signal_name, 
                bg=bg, 
                fg=base_fg
            )
            row_widgets["value"].config(
                text=value, 
                bg=bg, 
                fg=base_fg
            )
            row_widgets["unit"].config(
                text=unit, 
                bg=bg, 
                fg=base_fg
            )

        for i, row in enumerate(rows):
            old = previous_rows[i] if i < len(previous_rows) else None
            if old == row:
                continue
            signal_name, value, unit, status = row
            bg = self._status_bg(status)
            row_widgets = widgets[i]
            row_widgets["frame"].config(bg=bg)
            row_widgets["name"].config(text=signal_name, bg=bg)
            row_widgets["value"].config(text=value, bg=bg)
            row_widgets["unit"].config(text=unit, bg=bg)

    def _sync_detail_rows(
        self,
        body: tk.Frame,
        rows: list[tuple[str, str, str, str]],
        previous_rows: list[tuple[str, str, str, str]],
    ) -> None:
        base_fg = TEXT_MAIN if self._dark_mode else "#1a1a1a"
        base_bg = "#303030" if self._dark_mode else "#f5f5f5"
        border_color = "#4a4a4a" if self._dark_mode else "#d0d0d0"

        while len(self.detail_rows_widgets) > len(rows):
            row_widgets = self.detail_rows_widgets.pop()
            row_widgets["frame"].destroy()

        while len(self.detail_rows_widgets) < len(rows):
            frame = tk.Frame(
                body,
                bg=base_bg,
                highlightbackground=border_color,
                highlightthickness=1,
            )
            frame.pack(fill="x", pady=1)
            name = tk.Label(frame, anchor="w", bg=base_bg, fg=base_fg, font=("Segoe UI", 10, "bold"))
            name.pack(side="left", fill="x", expand=True, padx=(6, 6), pady=2)
            value = tk.Label(frame, anchor="e", width=8, bg=base_bg, fg=base_fg, font=("Segoe UI", 10))
            value.pack(side="left", padx=(0, 6), pady=2)
            unit = tk.Label(frame, anchor="w", width=7, bg=base_bg, fg=base_fg, font=("Segoe UI", 10))
            unit.pack(side="left", padx=(0, 6), pady=2)
            self.detail_rows_widgets.append({"frame": frame, "name": name, "value": value, "unit": unit})

        for i, row in enumerate(rows):
            signal_name, value, unit, status = row
            bg = self._status_bg(status)
            is_selected = (signal_name == self.active_signal)
            
            # Color de selecció: Verd fosc en dark, Verd corporatiu en light
            selected_border = "#4dd0ba" if self._dark_mode else "#0a594d"
            current_border = selected_border if is_selected else border_color
            
            row_widgets = self.detail_rows_widgets[i]
            
            # Apliquem els canvis de color de fons, vora i text
            row_widgets["frame"].config(
                bg=bg, 
                highlightbackground=current_border, 
                highlightthickness=2 if is_selected else 1
            )
            row_widgets["name"].config(text=signal_name, bg=bg, fg=base_fg)
            row_widgets["value"].config(text=value, bg=bg, fg=base_fg)
            row_widgets["unit"].config(text=unit, bg=bg, fg=base_fg)
            
            # Mantenim el bind per a la selecció
            for widget in (row_widgets["frame"], row_widgets["name"], row_widgets["value"], row_widgets["unit"]):
                widget.bind("<Button-1>", lambda _e, s=signal_name: self._set_active_signal(s))

        if (self.active_signal is None or all(r[0] != self.active_signal for r in rows)) and rows:
            self._set_active_signal(rows[0][0])

    def _set_active_signal(self, signal_name: str) -> None:
        if self.active_signal != signal_name:
            self.active_signal = signal_name
            # Force row restyle in next tick.
            self._detail_rows_cache = []

    def _create_signal_config_widgets(self, parent_frame: tk.Frame) -> None:
        """Crea els widgets per configurar valors OK/ERROR per estat"""
        car_state_manager = get_car_state_manager()
        states = car_state_manager.get_all_states()
        
        # Determinar colors segons el mode
        bg_card = CARD_BG if self._dark_mode else "#ffffff"
        fg_text = TEXT_MAIN if self._dark_mode else "#1a1a1a"
        
        # Crear widgets per cada estat
        for i, (state_name, state_desc) in enumerate(states.items(), start=1):
            # Nom de l'estat
            state_label = tk.Label(parent_frame, bg=bg_card, fg=fg_text, font=("Segoe UI", 9), text=state_name)
            state_label.grid(row=i, column=0, sticky="w", padx=2, pady=2)
            
            # Menú desplegable per configuració
            config_var = tk.StringVar(value="DIRECT")
            config_menu = ttk.Combobox(parent_frame, textvariable=config_var, values=["DIRECT", "INVERTED"], 
                                      state="readonly", width=12, font=("Segoe UI", 9))
            config_menu.grid(row=i, column=1, sticky="w", padx=2, pady=2)
            
            self.signal_config_widgets[state_name] = {
                "state_label": state_label,
                "config_var": config_var,
                "config_menu": config_menu
            }
    
    def _save_all_signal_config(self) -> None:
        """Guarda la configuració del senyal per tots els estats"""
        if not self.active_signal:
            return
        
        try:
            # Actualitzar configuració JSON
            car_state_manager = get_car_state_manager()
            
            # Obtenir configuració actual
            signal_config = car_state_manager.get_signal_config(self.active_signal)
            if signal_config and signal_config.get("logic") == "state_dependent":
                # Actualitzar valors per cada estat
                if "car_states" not in signal_config:
                    signal_config["car_states"] = {}
                
                for state_name, widgets in self.signal_config_widgets.items():
                    config_value = widgets["config_var"].get()
                    
                    if state_name not in signal_config["car_states"]:
                        signal_config["car_states"][state_name] = {}
                    
                    # Convertir DIRECT/INVERTED a valors OK/ERROR
                    if config_value == "DIRECT":
                        signal_config["car_states"][state_name]["ok_values"] = [1]
                        signal_config["car_states"][state_name]["error_values"] = [0]
                        signal_config["car_states"][state_name]["description"] = f"Senyal {self.active_signal} en estat {state_name} (DIRECT)"
                    else:  # INVERTED
                        signal_config["car_states"][state_name]["ok_values"] = [0]
                        signal_config["car_states"][state_name]["error_values"] = [1]
                        signal_config["car_states"][state_name]["description"] = f"Senyal {self.active_signal} en estat {state_name} (INVERTED)"
                
                # Guardar al fitxer JSON
                self._save_config_to_file(car_state_manager.config)
                
                # Mostrar confirmació
                print(f"Configuració guardada per {self.active_signal} a tots els estats")
        
        except Exception as e:
            print(f"Error guardant configuració: {e}")
    
    def _save_config_to_file(self, config: dict) -> None:
        """Guarda la configuració al fitxer JSON"""
        import json
        try:
            with open("config/digital_signals.json", "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardant fitxer de configuració: {e}")
    
    def _update_signal_config_ui(self, signal_name: str, signal) -> None:
        """Actualitza la UI de configuració per al senyal seleccionat"""
        car_state_manager = get_car_state_manager()
        signal_config = car_state_manager.get_signal_config(signal_name)
        
        # Amostrar o amagar el panell de configuració
        is_digital = (signal.cfg.min_valid == 0 and signal.cfg.max_valid == 1)
        
        if is_digital and signal_config:
            # Mostrar configuració
            self.signal_config_frame.grid()
            
            # Actualitzar valors per cada estat
            for state_name, widgets in self.signal_config_widgets.items():
                state_config = signal_config.get("car_states", {}).get(state_name, {})
                
                ok_values = state_config.get("ok_values", [1])
                error_values = state_config.get("error_values", [0])
                
                # Determinar si és DIRECT o INVERTED
                if ok_values == [1] and error_values == [0]:
                    config_value = "DIRECT"
                elif ok_values == [0] and error_values == [1]:
                    config_value = "INVERTED"
                else:
                    # Valors personalitzats, usar DIRECT per defecte
                    config_value = "DIRECT"
                
                widgets["config_var"].set(config_value)
        else:
            # Amagar configuració per senyals no digitals
            self.signal_config_frame.grid_remove()

    def _refresh_signal_panel(self, pcb: PCBState | None) -> None:
        if pcb is None or self.active_signal is None:
            return
        signal = pcb.signals.get(self.active_signal)
        if signal is None or not self.detail_signal_info:
            return

        name_label = self.detail_signal_info["name"]
        code_label = self.detail_signal_info["code"]
        minmax_label = self.detail_signal_info["minmax"]
        desc_label = self.detail_signal_info["desc"]
        plot_canvas = self.detail_signal_info["plot"]
        if not isinstance(plot_canvas, tk.Canvas):
            return

        if isinstance(name_label, tk.Label):
            name_label.config(text=signal.name)
        if isinstance(code_label, tk.Label):
            code_label.config(text=f"Codi DBC: {signal.name}")
        if isinstance(minmax_label, tk.Label):
            minmax_label.config(text=f"Min (60s): {signal.min:.3f}    Max (60s): {signal.max:.3f}")
        if isinstance(desc_label, tk.Label):
            desc_label.config(text=f"Descripció: {signal.description or 'Sense descripció'}")
        
        # Actualitzar UI de configuració
        self._update_signal_config_ui(signal.name, signal)
        
        now = time.monotonic()
        canvas_size = (plot_canvas.winfo_width(), plot_canvas.winfo_height())
        must_redraw = (
            self._last_plot_signal != signal.name
            or (now - self._last_plot_draw_s) >= self._plot_refresh_interval_s
            or self._last_plot_canvas_size != canvas_size
        )
        if must_redraw:
            self._draw_signal_plot(
                plot_canvas,
                signal.history,
                min_valid=signal.cfg.min_valid,
                max_valid=signal.cfg.max_valid,
            )
            self._last_plot_draw_s = now
            self._last_plot_signal = signal.name
            self._last_plot_canvas_size = canvas_size

    @staticmethod
    def _draw_signal_plot(canvas: tk.Canvas, history, min_valid: float | None, max_valid: float | None) -> None:
        canvas.delete("all")
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        now = time.time()
        points = [(t, v) for t, v in history if t >= now - 60.0]
        if len(points) < 2:
            canvas.create_text(
                width // 2, height // 2, text="Esperant dades del senyal...", fill="#666666", font=("Arial", 11)
            )
            return

        step = max(1, len(points) // 400)
        points = points[::step]
        values = [v for _, v in points]
        vmin = min(values)
        vmax = max(values)
        if abs(vmax - vmin) < 1e-9:
            vmax = vmin + 1.0

        coords: list[float] = []
        for ts, value in points:
            x = ((ts - (now - 60.0)) / 60.0) * (width - 20) + 10
            y = height - 10 - ((value - vmin) / (vmax - vmin) * (height - 20))
            coords.extend([x, y])

        plot_top = 8
        plot_bottom = height - 8
        plot_left = 8
        plot_right = width - 8
        plot_height = max(1, plot_bottom - plot_top)

        canvas.create_rectangle(plot_left, plot_top, plot_right, plot_bottom, outline="#D0D0D0")

        def y_from_value(value: float) -> float:
            return plot_bottom - ((value - vmin) / (vmax - vmin) * plot_height)

        if min_valid is not None:
            y_min_limit = y_from_value(min_valid)
            if plot_top <= y_min_limit <= plot_bottom:
                canvas.create_line(plot_left, y_min_limit, plot_right, y_min_limit, fill="#D32F2F", width=1, dash=(4, 3))
                canvas.create_text(
                    plot_right - 6,
                    y_min_limit - 2,
                    anchor="se",
                    text=f"MIN DBC {min_valid:.3f}",
                    fill="#D32F2F",
                    font=("Arial", 8, "bold"),
                )

        if max_valid is not None:
            y_max_limit = y_from_value(max_valid)
            if plot_top <= y_max_limit <= plot_bottom:
                canvas.create_line(plot_left, y_max_limit, plot_right, y_max_limit, fill="#D32F2F", width=1, dash=(4, 3))
                canvas.create_text(
                    plot_right - 6,
                    y_max_limit - 2,
                    anchor="se",
                    text=f"MAX DBC {max_valid:.3f}",
                    fill="#D32F2F",
                    font=("Arial", 8, "bold"),
                )

        canvas.create_line(*coords, fill="#0a594d", width=2, smooth=False)
        canvas.create_text(14, 12, anchor="nw", text=f"{vmax:.3f}", fill="#666666", font=("Arial", 9))
        canvas.create_text(14, height - 12, anchor="sw", text=f"{vmin:.3f}", fill="#666666", font=("Arial", 9))

    def _status_bg(self, status: str) -> str:
        if status == "OK":
            return "#1f4d2f" if self._dark_mode else "#d8f5df"
        if status == "WARNING":
            return "#665c1f" if self._dark_mode else "#fff4c2"
        if status == "ERROR":
            return "#6b2a2a" if self._dark_mode else "#ffd6d6"
        return "#4a4a4a" if self._dark_mode else "#e6e6e6"

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled
        
        # Actualitzem colors de fons principals
        bg_color = DARK_BG if enabled else "#f0f0f0"
        self.configure(bg=bg_color)
        self.main_container.configure(bg=bg_color)
        
        # Forcem el re-dibuix de la vista actual netejant les caches
        self._grid_rows_cache = {}
        self._detail_rows_cache = []
        
        if self.current_view == "detail" and self.active_placa:
            self.show_detail_view(self.active_placa)
        else:
            self.show_grid_view()


class SDCTab(tk.Frame):
    def __init__(self, parent: tk.Widget, model: VehicleModel):
        super().__init__(parent, bg=DARK_BG)
        self.model = model
        tk.Label(self, text="SHUTDOWN CIRCUIT", font=("Montserrat", 14, "bold"), bg=DARK_BG, fg="#67d7c5").pack(pady=12)
        self.canvas = tk.Canvas(self, bg=DARK_BG, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.canvas.bind("<Configure>", self._on_resize)

        self.components = ["LVMS", "BSPD", "IMD", "AMS", "TSMS", "HV INTERLOCK", "BOTS", "INERTIA", "COCKPIT"]
        self.demo_enabled = True
        self._dark_mode = True
        self.component_items: dict[str, tuple[int, int, int]] = {}
        self.component_status: dict[str, str] = {}
        self.sdc_state_items: tuple[int, int] | None = None
        self._diagram_size: tuple[int, int] = (0, 0)
        self._demo_cycle_idx = -1
        self._draw_diagram()

    def update_ui(self) -> None:
        live_found = False
        changed = False
        for component in self.components:
            new_status = self._state_for_component(component)
            if new_status != "NO_DATA":
                live_found = True
            if self.component_status.get(component) != new_status:
                self.component_status[component] = new_status
                changed = True

        # Fake test values when no live CAN information is available.
        if not live_found and self.demo_enabled:
            demo_idx = int(time.monotonic()) % len(self.components)
            if demo_idx != self._demo_cycle_idx:
                self._demo_cycle_idx = demo_idx
                for idx, component in enumerate(self.components):
                    if idx == demo_idx:
                        self.component_status[component] = "OPEN"       # 0 -> red
                    elif idx == (demo_idx - 1) % len(self.components):
                        self.component_status[component] = "NO_DATA"    # timeout -> gray
                    else:
                        self.component_status[component] = "CLOSED"     # 1 -> blue
                changed = True

        if changed:
            self._apply_status_colors()
            self._apply_sdc_global_state()

    def set_demo_enabled(self, enabled: bool) -> None:
        self.demo_enabled = enabled

    def _on_resize(self, _event: tk.Event) -> None:
        size = (self.canvas.winfo_width(), self.canvas.winfo_height())
        if size != self._diagram_size:
            self._draw_diagram()

    def _draw_diagram(self) -> None:
        self.canvas.delete("all")
        self.component_items = {}
        self.component_status = {name: "NO_DATA" for name in self.components}
        self._demo_cycle_idx = -1
        w = max(900, self.canvas.winfo_width())
        h = max(420, self.canvas.winfo_height())
        self._diagram_size = (w, h)

        margin_x = 70
        top_y = 160
        box_w = 105
        box_h = 56
        spacing = (w - (2 * margin_x) - (box_w * len(self.components))) / max(1, len(self.components) - 1)
        line_color = "#d0d0d0" if self._dark_mode else "#222222"
        text_color = "#f0f0f0" if self._dark_mode else "#1f1f1f"

        state_rect = self.canvas.create_rectangle(w - 280, 24, w - 24, 72, outline=line_color, width=1, fill="#E8E8E8")
        state_text = self.canvas.create_text(
            w - 152,
            48,
            text="SDC: SENSE INFO",
            fill=text_color,
            font=("Arial", 10, "bold"),
        )
        self.sdc_state_items = (state_rect, state_text)

        for i, name in enumerate(self.components):
            x1 = margin_x + i * (box_w + spacing)
            y1 = top_y
            x2 = x1 + box_w
            y2 = y1 + box_h
            rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline=line_color, width=2, fill="#F2F2F2")
            text_id = self.canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=name, fill=text_color, font=("Arial", 9, "bold"))
            dot_id = self.canvas.create_oval(x2 - 16, y1 + 8, x2 - 8, y1 + 16, outline="", fill="#8A8A8A")
            self.component_items[name] = (rect_id, text_id, dot_id)
            if i < len(self.components) - 1:
                nx1 = margin_x + (i + 1) * (box_w + spacing)
                self.canvas.create_line(x2, y1 + box_h / 2, nx1, y1 + box_h / 2, fill=line_color, width=3)

        self._apply_status_colors()
        self._apply_sdc_global_state()

    def _state_for_component(self, component: str) -> str:
        token = component.lower().replace(" ", "").replace("_", "")
        latest_signal = None
        latest_ts = -1.0
        with self.model.lock():
            for pcb in self.model.vehicle.pcbs.values():
                for signal_name, signal in pcb.signals.items():
                    key = f"{pcb.name}{signal_name}".lower().replace(" ", "").replace("_", "")
                    if token in key:
                        if signal.timestamp > latest_ts:
                            latest_signal = signal
                            latest_ts = signal.timestamp
        if latest_signal is None or latest_signal.status == "TIMEOUT":
            return "NO_DATA"
        # CAN signal convention: 1 = closed (blue), 0 = open (red).
        return "CLOSED" if int(round(latest_signal.value)) == 1 else "OPEN"

    def _apply_status_colors(self) -> None:
        palette = {
            "CLOSED": ("#CFE2FF", "#5B89D6"),
            "OPEN": ("#F5C0C0", "#D98A8A"),
            "NO_DATA": ("#E8E8E8", "#BCBCBC"),
        }
        for component, (rect_id, text_id, dot_id) in self.component_items.items():
            status = self.component_status.get(component, "NO_DATA")
            fill, _label_fill = palette.get(status, palette["NO_DATA"])
            self.canvas.itemconfigure(rect_id, fill=fill)
            self.canvas.itemconfigure(text_id, fill="#1f1f1f")
            if status == "OPEN":
                dot_color = "#D32F2F"
            elif status == "CLOSED":
                dot_color = "#1E64C8"
            else:
                dot_color = "#8A8A8A"
            self.canvas.itemconfigure(dot_id, fill=dot_color)

    def _apply_sdc_global_state(self) -> None:
        if not self.sdc_state_items:
            return
        rect_id, text_id = self.sdc_state_items
        values = list(self.component_status.values())
        if values and all(state == "CLOSED" for state in values):
            text = "SDC: ACTIU"
            fill = "#CFE2FF"
        elif any(state == "OPEN" for state in values):
            text = "SDC: ERROR (PUNT OBERT)"
            fill = "#F5C0C0"
        else:
            text = "SDC: SENSE INFO"
            fill = "#E8E8E8"
        self.canvas.itemconfigure(rect_id, fill=fill)
        self.canvas.itemconfigure(text_id, text=text)

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled
        bg = DARK_BG if enabled else "#f0f0f0"
        fg = "#67d7c5" if enabled else "#0a594d"
        self.configure(bg=bg)
        for w in self.winfo_children():
            if isinstance(w, tk.Label):
                w.configure(bg=bg, fg=fg)
        self.canvas.configure(bg=bg)
        self._draw_diagram()


class TemperatureTab(tk.Frame):
    def __init__(self, parent: tk.Widget):
        super().__init__(parent, bg=DARK_BG)
        container = tk.Frame(self, bg=DARK_BG)
        container.pack(expand=True)
        tk.Label(container, text="TEMPERATURES", font=("Montserrat", 14, "bold"), bg=DARK_BG, fg="#67d7c5").pack(
            pady=20
        )

    def update_ui(self) -> None:
        return

    def set_dark_mode(self, enabled: bool) -> None:
        bg = DARK_BG if enabled else "#f0f0f0"
        fg = "#67d7c5" if enabled else "#0a594d"
        self.configure(bg=bg)
        for child in self.winfo_children():
            child.configure(bg=bg)
            for sub in child.winfo_children():
                if isinstance(sub, tk.Label):
                    sub.configure(bg=bg, fg=fg)


class SensorTab(tk.Frame):
    def __init__(self, parent: tk.Widget, model: VehicleModel):
        super().__init__(parent, bg=DARK_BG)
        self.model = model
        self.demo_enabled = True
        self._dark_mode = True
        self._demo_phase = 0.0
        self._motor_flash = False
        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        self.left = tk.Frame(self, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(10, 6), pady=10)
        self.right = tk.Frame(self, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        self.right.grid(row=0, column=1, sticky="nsew", padx=(6, 10), pady=10)
        self.left.grid_columnconfigure(0, weight=1)
        self.left.grid_columnconfigure(1, weight=1)
        self.right.grid_columnconfigure(0, weight=1)
        self.right.grid_rowconfigure(0, weight=1)
        self.right.grid_rowconfigure(1, weight=1)

        self.location_trees: dict[str, ttk.Treeview] = {}
        for idx, loc in enumerate(["RL", "RR", "FL", "FR"]):
            r, c = idx // 2, idx % 2
            holder = self._build_tree_container(self.left, loc)
            holder.grid(row=r, column=c, sticky="nsew", padx=8, pady=8)
            self.location_trees[loc] = holder.tree  # type: ignore[attr-defined]

        self.temp_holder = self._build_tree_container(self.right, "Temperatures")
        self.temp_holder.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))
        self.pedal_holder = self._build_tree_container(self.right, "Pedals i Fre")
        self.pedal_holder.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 8))

        self.bars: dict[str, tuple[tk.Canvas, int, int, bool]] = {}
        self._add_section_bars(self.temp_holder, [("cool_in", "T. Inv In", False), ("cool_out", "T. Inv Out", False), ("motor_temp", "T. Motor", False)])
        self._add_section_bars(self.pedal_holder, [("acc1", "Accel 1 (%)", False), ("acc2", "Accel 2 (%)", False), ("brake_pct", "Fre (%)", False), ("brake_bar", "Pressió Fre (bar)", False)])

        self._set_tree_theme(True)

    def update_ui(self) -> None:
        data = self._collect_data()
        for loc in ["RL", "RR", "FL", "FR"]:
            vel_key = f"wheel_{loc.lower()}"
            susp_key = f"susp_{loc.lower()}"
            rows = [
                ("Velocitat", f"{data[vel_key]:.1f} km/h", self._bar_text(data[vel_key], 0, 80, centered=False)),
                ("Suspensió", f"{data[susp_key]:.1f} %", self._bar_text(data[susp_key], 0, 100, centered=True)),
            ]
            self._fill_tree(self.location_trees[loc], rows)

        self._fill_tree(
            self.temp_holder.tree,  # type: ignore[attr-defined]
            [
                ("Inv In", f"{data['cool_in']:.1f} C", self._bar_text(data["cool_in"], 0, 90, centered=False)),
                ("Inv Out", f"{data['cool_out']:.1f} C", self._bar_text(data["cool_out"], 0, 90, centered=False)),
                ("Motor", f"{data['motor_temp']:.1f} C", self._bar_text(data["motor_temp"], 0, 120, centered=False)),
            ],
        )
        self._fill_tree(
            self.pedal_holder.tree,  # type: ignore[attr-defined]
            [
                ("Accel 1", f"{data['acc1']:.1f} %", self._bar_text(data["acc1"], 0, 100, centered=False)),
                ("Accel 2", f"{data['acc2']:.1f} %", self._bar_text(data["acc2"], 0, 100, centered=False)),
                ("Fre %", f"{data['brake_pct']:.1f} %", self._bar_text(data["brake_pct"], 0, 100, centered=False)),
                ("Fre bar", f"{data['brake_pressure']:.1f} bar", self._bar_text(data["brake_pressure"], 0, 80, centered=False)),
            ],
        )

        self._update_bar("cool_in", data["cool_in"], 0, 90, "#5aa9ff")
        self._update_bar("cool_out", data["cool_out"], 0, 90, "#5aa9ff")
        motor_color = self._motor_temp_color(data["motor_temp"])
        self._update_bar("motor_temp", data["motor_temp"], 0, 120, motor_color)
        self._update_bar("acc1", data["acc1"], 0, 100, "#57d68d")
        self._update_bar("acc2", data["acc2"], 0, 100, "#57d68d")
        self._update_bar("brake_pct", data["brake_pct"], 0, 100, "#ff5b5b")
        self._update_bar("brake_bar", data["brake_pressure"], 0, 80, "#ff8a8a")

    def _build_tree_container(self, parent: tk.Widget, title: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        tk.Label(frame, text=title, bg=CARD_BG, fg="#67d7c5", font=("Roboto", 10, "bold")).pack(anchor="w", padx=8, pady=(6, 4))
        tree = ttk.Treeview(frame, columns=("loc", "value", "bar"), show="headings", height=4)
        tree.heading("loc", text="Camp")
        tree.heading("value", text="Valor")
        tree.heading("bar", text="Barra")
        tree.column("loc", width=70, anchor="w")
        tree.column("value", width=85, anchor="e")
        tree.column("bar", width=90, anchor="w")
        tree.pack(fill="x", padx=6, pady=(0, 6))
        frame.tree = tree  # type: ignore[attr-defined]
        return frame

    @staticmethod
    def _fill_tree(tree: ttk.Treeview, rows: list[tuple[str, str, str]]) -> None:
        for iid in tree.get_children():
            tree.delete(iid)
        for loc, val, bar in rows:
            tree.insert("", "end", values=(loc, val, bar))

    def _add_section_bars(self, holder: tk.Frame, specs: list[tuple[str, str, bool]]) -> None:
        bars_panel = tk.Frame(holder, bg=CARD_BG)
        bars_panel.pack(fill="x", padx=6, pady=(0, 6))
        for row, (key, label, centered) in enumerate(specs):
            tk.Label(bars_panel, text=label, bg=CARD_BG, fg=TEXT_MAIN, font=("Roboto", 9)).grid(row=row, column=0, sticky="w", pady=3)
            c = tk.Canvas(bars_panel, width=170, height=14, bg=CARD_BG, highlightthickness=0)
            c.grid(row=row, column=1, sticky="e", pady=3, padx=(8, 0))
            bg = c.create_rectangle(2, 2, 168, 12, outline="#555555", fill="#1a1a1a")
            fill = c.create_rectangle(3, 3, 3, 11, outline="", fill="#57d68d")
            if centered:
                c.create_line(85, 1, 85, 13, fill="#8a8a8a", dash=(2, 2))
            self.bars[key] = (c, bg, fill, centered)

    def _update_bar(self, key: str, value: float, vmin: float, vmax: float, color: str) -> None:
        c, bg, fill, centered = self.bars[key]
        x1, y1, x2, y2 = c.coords(bg)
        ratio = 0.0 if vmax <= vmin else max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
        if centered:
            mid = (x1 + x2) / 2
            delta = ratio - 0.5
            if delta >= 0:
                c.coords(fill, mid, y1 + 1, mid + (x2 - mid - 1) * (delta / 0.5), y2 - 1)
            else:
                c.coords(fill, mid + (mid - x1 - 1) * (delta / 0.5), y1 + 1, mid, y2 - 1)
        else:
            c.coords(fill, x1 + 1, y1 + 1, x1 + 1 + (x2 - x1 - 2) * ratio, y2 - 1)
        c.itemconfigure(fill, fill=color)

    def _collect_data(self) -> dict[str, float]:
        keys = {"wheel_fl":[("FRONT ECU","wheel_speed_fl"),("DYNAMICS","vel_fl")],"wheel_fr":[("FRONT ECU","wheel_speed_fr"),("DYNAMICS","vel_fr")],"wheel_rl":[("REAR ECU","wheel_speed_rl"),("DYNAMICS","vel_rl")],"wheel_rr":[("REAR ECU","wheel_speed_rr"),("DYNAMICS","vel_rr")],"cool_in":[("INVERTER","coolant_temp_in"),("INV","coolant_in")],"cool_out":[("INVERTER","coolant_temp_out"),("INV","coolant_out")],"motor_temp":[("INVERTER","motor_temp"),("INV","motor_temp")],"brake_pressure":[("BSPD","brake_pressure"),("FRONT ECU","brake_pressure")],"brake_pct":[("BSPD","brake_pct"),("FRONT ECU","brake_pct")],"acc1":[("FRONT ECU","accel_sensor_1"),("VCU","accel_1")],"acc2":[("FRONT ECU","accel_sensor_2"),("VCU","accel_2")],"susp_fl":[("FRONT ECU","susp_fl"),("DYNAMICS","susp_fl")],"susp_fr":[("FRONT ECU","susp_fr"),("DYNAMICS","susp_fr")],"susp_rl":[("REAR ECU","susp_rl"),("DYNAMICS","susp_rl")],"susp_rr":[("REAR ECU","susp_rr"),("DYNAMICS","susp_rr")]}
        out: dict[str, float] = {}
        with self.model.lock():
            for k, aliases in keys.items():
                v = None
                for pcb, sig in aliases:
                    p = self.model.vehicle.pcbs.get(pcb)
                    if p and sig in p.signals:
                        v = p.signals[sig].value
                        break
                out[k] = float(v) if v is not None else float("nan")
        self._demo_phase += 0.25
        demo = {"wheel_fl":36 + 4*math.sin(self._demo_phase*0.3),"wheel_fr":35 + 5*math.sin(self._demo_phase*0.31+0.2),"wheel_rl":34 + 5*math.sin(self._demo_phase*0.28+0.4),"wheel_rr":35 + 4*math.sin(self._demo_phase*0.3+0.1),"cool_in":38 + 2*math.sin(self._demo_phase*0.07),"cool_out":44 + 2*math.sin(self._demo_phase*0.08),"motor_temp":56 + 3*math.sin(self._demo_phase*0.06),"brake_pressure":20 + 15*math.sin(self._demo_phase*0.09),"brake_pct":50 + 45*math.sin(self._demo_phase*0.09),"acc1":50 + 45*math.sin(self._demo_phase*0.11),"acc2":50 + 45*math.sin(self._demo_phase*0.12+0.2),"susp_fl":46 + 8*math.sin(self._demo_phase*0.25),"susp_fr":49 + 7*math.sin(self._demo_phase*0.26+0.3),"susp_rl":51 + 6*math.sin(self._demo_phase*0.24+0.5),"susp_rr":48 + 7*math.sin(self._demo_phase*0.23+0.1)}
        for k, v in out.items():
            if v != v:
                out[k] = demo[k] if self.demo_enabled else 0.0
        out["avg_speed"] = (out["wheel_fl"] + out["wheel_fr"] + out["wheel_rl"] + out["wheel_rr"]) / 4.0
        out["avg_temp"] = (out["cool_in"] + out["cool_out"] + out["motor_temp"]) / 3.0
        return out

    def _motor_temp_color(self, t: float) -> str:
        if t < 75:
            return TEXT_MAIN if self._dark_mode else "#1a1a1a"
        if t < 95:
            return "#ffd166"
        self._motor_flash = not self._motor_flash
        return "#ff4d4d" if self._motor_flash else "#772222"

    def set_demo_enabled(self, enabled: bool) -> None:
        self.demo_enabled = enabled

    def set_dark_mode(self, enabled: bool) -> None:
        self._dark_mode = enabled
        bg = DARK_BG if enabled else "#f0f0f0"
        card = CARD_BG if enabled else "white"
        self.configure(bg=bg)
        self.left.configure(bg=card, highlightbackground=CARD_BORDER if enabled else "#d0d0d0")
        self.right.configure(bg=card, highlightbackground=CARD_BORDER if enabled else "#d0d0d0")
        for frame in [self.left, self.right]:
            for child in frame.winfo_children():
                if isinstance(child, tk.Frame):
                    child.configure(bg=card, highlightbackground=CARD_BORDER if enabled else "#d0d0d0")
                    for sub in child.winfo_children():
                        if isinstance(sub, tk.Label):
                            sub.configure(bg=card, fg=TEXT_MAIN if enabled else "#1a1a1a")
                        elif isinstance(sub, tk.Canvas):
                            sub.configure(bg=card)
        self._set_tree_theme(enabled)

    def _set_tree_theme(self, enabled: bool) -> None:
        style = ttk.Style()
        if enabled:
            style.configure("Sensor.Treeview", background="#2f2f2f", fieldbackground="#2f2f2f", foreground="#f2f2f2")
            style.configure("Sensor.Treeview.Heading", background="#3a3a3a", foreground="#d8d8d8")
        else:
            style.configure("Sensor.Treeview", background="white", fieldbackground="white", foreground="#1a1a1a")
            style.configure("Sensor.Treeview.Heading", background="#e0e0e0", foreground="#1a1a1a")
        for holder in [*self.location_trees.values(), self.temp_holder.tree, self.pedal_holder.tree]:  # type: ignore[attr-defined]
            holder.configure(style="Sensor.Treeview")

    @staticmethod
    def _bar_text(value: float, vmin: float, vmax: float, centered: bool) -> str:
        n = 10
        if vmax <= vmin:
            return "-" * n
        ratio = max(0.0, min(1.0, (value - vmin) / (vmax - vmin)))
        if centered:
            mid = n // 2
            delta = ratio - 0.5
            cells = [" "] * n
            cells[mid] = "|"
            span = int(abs(delta) * 2 * mid)
            if delta >= 0:
                for i in range(mid + 1, min(n, mid + 1 + span)):
                    cells[i] = "\u2588"
            else:
                for i in range(max(0, mid - span), mid):
                    cells[i] = "\u2588"
            return "".join(cells)
        filled = int(ratio * n)
        return "\u2588" * filled + "\u2591" * (n - filled)


class ConfigurationTab(tk.Frame):
    def __init__(self, parent: tk.Widget):
        super().__init__(parent, bg=DARK_BG)
        self.panel = tk.Frame(self, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
        self.panel.pack(fill="both", expand=True, padx=20, pady=20)

        tk.Label(self.panel, text="CONFIGURACIÓ", bg=CARD_BG, fg="#78f2dd", font=("Montserrat", 16, "bold")).pack(
            anchor="w", padx=18, pady=(16, 8)
        )
        tk.Label(
            self.panel,
            text="Paràmetres d'aspecte i operació de l'aplicació de telemetria.",
            bg=CARD_BG,
            fg=TEXT_MUTED,
            font=("Roboto", 10),
        ).pack(anchor="w", padx=18, pady=(0, 16))

        self.dark_mode_var = tk.BooleanVar(value=True)
        self.demo_var = tk.BooleanVar(value=True)
        self.refresh_var = tk.IntVar(value=250)

        tk.Checkbutton(
            self.panel,
            text="Dark Mode actiu",
            variable=self.dark_mode_var,
            bg=CARD_BG,
            fg=TEXT_MAIN,
            activebackground=CARD_BG,
            activeforeground=TEXT_MAIN,
            selectcolor=DARK_BG,
            font=("Roboto", 11),
        ).pack(anchor="w", padx=18, pady=6)
        tk.Checkbutton(
            self.panel,
            text="Valors demo quan no hi ha CAN",
            variable=self.demo_var,
            bg=CARD_BG,
            fg=TEXT_MAIN,
            activebackground=CARD_BG,
            activeforeground=TEXT_MAIN,
            selectcolor=DARK_BG,
            font=("Roboto", 11),
        ).pack(anchor="w", padx=18, pady=6)
        tk.Label(self.panel, text="Refresc UI (ms)", bg=CARD_BG, fg=TEXT_MAIN, font=("Roboto", 11)).pack(
            anchor="w", padx=18, pady=(14, 4)
        )
        tk.Scale(
            self.panel,
            from_=100,
            to=1000,
            orient="horizontal",
            resolution=50,
            variable=self.refresh_var,
            bg=CARD_BG,
            fg=TEXT_MAIN,
            highlightthickness=0,
            troughcolor="#383838",
            activebackground="#67d7c5",
            length=320,
        ).pack(anchor="w", padx=18)

    def update_ui(self) -> None:
        return

    def set_dark_mode(self, enabled: bool) -> None:
        bg = DARK_BG if enabled else "#f0f0f0"
        panel_bg = CARD_BG if enabled else "white"
        fg = TEXT_MAIN if enabled else "#1a1a1a"
        self.configure(bg=bg)
        self.panel.configure(bg=panel_bg, highlightbackground=CARD_BORDER if enabled else "#d0d0d0")
        for w in self.panel.winfo_children():
            if isinstance(w, (tk.Label, tk.Checkbutton, tk.Scale)):
                try:
                    w.configure(bg=panel_bg, fg=fg)
                except Exception:
                    pass
