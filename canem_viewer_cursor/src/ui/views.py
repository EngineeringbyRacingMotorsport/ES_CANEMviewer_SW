from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.model.vehicle_model import VehicleModel
from src.ui.theme import COLORS, FONT_BODY, FONT_H1, FONT_H2, status_color
from src.ui.widgets.realtime_plot import RealtimePlot


class OverviewView(tk.Frame):
    def __init__(self, parent: tk.Widget, model: VehicleModel, on_open_pcb) -> None:
        super().__init__(parent, bg=COLORS["bg_main"])
        self.model = model
        self.on_open_pcb = on_open_pcb
        self.cards: dict[str, dict[str, tk.Widget]] = {}
        self.default_pcbs = [
            "FRONT ECU",
            "REAR ECU",
            "HVAB",
            "HVDB",
            "TSAL GREEN",
            "SDC RESET",
            "BSPD",
            "BMS",
            "IMD",
            "INVERTER",
        ]
        tk.Label(self, text="Vehicle Overview", font=FONT_H1, bg=COLORS["bg_main"], fg=COLORS["text"]).pack(
            anchor="w", padx=12, pady=10
        )
        self.body = tk.Frame(self, bg=COLORS["bg_main"])
        self.body.pack(fill="both", expand=True, padx=12, pady=6)

    def refresh(self) -> None:
        with self.model.lock():
            model_pcbs = {name: pcb for name, pcb in self.model.vehicle.pcbs.items()}

        pcb_names = list(self.default_pcbs)
        for extra_name in model_pcbs.keys():
            if extra_name not in pcb_names:
                pcb_names.append(extra_name)

        active_names = set(pcb_names)
        for i, pcb_name in enumerate(pcb_names):
            pcb = model_pcbs.get(pcb_name)
            if pcb_name not in self.cards:
                self.cards[pcb_name] = self._create_card(pcb_name)
            card_info = self.cards[pcb_name]
            card = card_info["frame"]
            card.grid(row=i, column=0, sticky="ew", padx=6, pady=4)

            status = pcb.status if pcb else "TIMEOUT"
            status_label: tk.Label = card_info["status"]  # type: ignore[assignment]
            status_label.config(text=f"Status: {status}", fg=status_color(status))

            signals_frame: tk.Frame = card_info["signals_frame"]  # type: ignore[assignment]
            for child in signals_frame.winfo_children():
                child.destroy()
            if pcb and pcb.signals:
                for sig in list(pcb.signals.values())[:8]:
                    row = tk.Frame(signals_frame, bg=COLORS["bg_panel"])
                    row.pack(fill="x", padx=(20, 0))
                    badge = tk.Label(
                        row,
                        text="  ",
                        bg=status_color(sig.status),
                        width=2,
                        height=1,
                    )
                    badge.pack(side="left", padx=(0, 8), pady=1)
                    text = f"{sig.name}: {sig.value:.3f} {sig.unit} ({sig.status})"
                    tk.Label(
                        row,
                        text=text,
                        font=FONT_BODY,
                        bg=COLORS["bg_panel"],
                        fg=COLORS["text"],
                        anchor="w",
                    ).pack(side="left", fill="x")
            else:
                row = tk.Frame(signals_frame, bg=COLORS["bg_panel"])
                row.pack(fill="x", padx=(20, 0))
                tk.Label(
                    row,
                    text="  ",
                    bg=COLORS["timeout"],
                    width=2,
                    height=1,
                ).pack(side="left", padx=(0, 8), pady=1)
                tk.Label(
                    row,
                    text="No signals yet",
                    font=FONT_BODY,
                    bg=COLORS["bg_panel"],
                    fg=COLORS["muted"],
                    anchor="w",
                ).pack(side="left", fill="x")

        removed = [name for name in list(self.cards.keys()) if name not in active_names]
        for name in removed:
            frame = self.cards[name]["frame"]
            frame.destroy()
            del self.cards[name]

    def _create_card(self, pcb_name: str) -> dict[str, tk.Widget]:
        card = tk.Frame(self.body, bg=COLORS["bg_panel"], padx=10, pady=8)
        title_button = ttk.Button(card, text=pcb_name, command=lambda n=pcb_name: self.on_open_pcb(n))
        title_button.pack(anchor="w")
        status = tk.Label(card, text="Status: TIMEOUT", font=FONT_BODY, bg=COLORS["bg_panel"], fg=COLORS["timeout"])
        status.pack(anchor="w")
        signals_frame = tk.Frame(card, bg=COLORS["bg_panel"])
        signals_frame.pack(fill="x", pady=(4, 0))
        return {"frame": card, "status": status, "signals_frame": signals_frame}


class PCBView(tk.Frame):
    def __init__(self, parent: tk.Widget, model: VehicleModel, pcb_name: str, on_open_signal, on_back) -> None:
        super().__init__(parent, bg=COLORS["bg_main"])
        self.model = model
        self.pcb_name = pcb_name
        self.on_open_signal = on_open_signal
        self.filter_var = tk.StringVar()
        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=12, pady=10)
        ttk.Button(top, text="< Back", command=on_back).pack(side="left")
        tk.Label(top, text=f"PCB: {pcb_name}", font=FONT_H1, bg=COLORS["bg_main"], fg=COLORS["text"]).pack(side="left", padx=10)
        ttk.Entry(top, textvariable=self.filter_var, width=35).pack(side="right")

        self.tree = ttk.Treeview(self, columns=("value", "status", "timestamp"), show="headings", height=20)
        self.tree.heading("value", text="Value")
        self.tree.heading("status", text="Status")
        self.tree.heading("timestamp", text="Timestamp")
        self.tree.pack(fill="both", expand=True, padx=12, pady=8)
        self.tree.bind("<Double-1>", self._on_open_signal)

    def refresh(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        filter_text = self.filter_var.get().lower().strip()
        with self.model.lock():
            pcb = self.model.vehicle.pcbs.get(self.pcb_name)
            if not pcb:
                return
            signals = list(pcb.signals.values())
        for signal in signals:
            if filter_text and filter_text not in signal.name.lower():
                continue
            self.tree.insert("", "end", iid=signal.name, values=(f"{signal.value:.3f} {signal.unit}", signal.status, f"{signal.timestamp:.3f}"))

    def _on_open_signal(self, _event) -> None:
        selected = self.tree.selection()
        if selected:
            self.on_open_signal(self.pcb_name, selected[0])


class SignalView(tk.Frame):
    def __init__(self, parent: tk.Widget, model: VehicleModel, pcb_name: str, signal_name: str, on_back) -> None:
        super().__init__(parent, bg=COLORS["bg_main"])
        self.model = model
        self.pcb_name = pcb_name
        self.signal_name = signal_name

        top = tk.Frame(self, bg=COLORS["bg_main"])
        top.pack(fill="x", padx=12, pady=10)
        ttk.Button(top, text="< Back", command=on_back).pack(side="left")
        tk.Label(top, text=f"Signal: {pcb_name}.{signal_name}", font=FONT_H1, bg=COLORS["bg_main"], fg=COLORS["text"]).pack(side="left", padx=10)

        self.meta = tk.Label(self, font=FONT_BODY, bg=COLORS["bg_main"], fg=COLORS["text"], justify="left")
        self.meta.pack(anchor="w", padx=12)

        self.plot = RealtimePlot(self, model=self.model, pcb_name=pcb_name, signal_name=signal_name, height=320)
        self.plot.pack(fill="both", expand=True, padx=12, pady=12)

    def refresh(self) -> None:
        with self.model.lock():
            pcb = self.model.vehicle.pcbs.get(self.pcb_name)
            if not pcb:
                return
            signal = pcb.signals.get(self.signal_name)
            if not signal:
                return
            meta = (
                f"Value: {signal.value:.4f} {signal.unit}\n"
                f"Status: {signal.status}\n"
                f"Window Min/Max (60s): {signal.min:.4f} / {signal.max:.4f}\n"
                f"Timestamp: {signal.timestamp:.3f}\n"
                f"Description: {signal.description or '-'}"
            )
        self.meta.config(text=meta, fg=status_color(signal.status))
        self.plot.refresh()
