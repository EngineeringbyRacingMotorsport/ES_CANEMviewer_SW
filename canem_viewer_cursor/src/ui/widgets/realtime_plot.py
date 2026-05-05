from __future__ import annotations

import time
import tkinter as tk
from typing import List, Tuple

from src.model.vehicle_model import VehicleModel
from src.ui.theme import COLORS


class RealtimePlot(tk.Canvas):
    def __init__(self, parent: tk.Widget, model: VehicleModel, pcb_name: str, signal_name: str, **kwargs) -> None:
        super().__init__(parent, bg=COLORS["bg_panel"], highlightthickness=0, **kwargs)
        self.model = model
        self.pcb_name = pcb_name
        self.signal_name = signal_name

    def refresh(self) -> None:
        self.delete("all")
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        now = time.time()
        with self.model.lock():
            pcb = self.model.vehicle.pcbs.get(self.pcb_name)
            if not pcb or self.signal_name not in pcb.signals:
                return
            points = [(t, v) for t, v in pcb.signals[self.signal_name].history if t >= now - 60.0]

        if len(points) < 2:
            return
        step = max(1, len(points) // 300)
        points = points[::step]
        values = [v for _, v in points]
        ymin = min(values)
        ymax = max(values)
        if abs(ymax - ymin) < 1e-9:
            ymax += 1.0
            ymin -= 1.0

        coords: List[float] = []
        for t, v in points:
            x = ((t - (now - 60.0)) / 60.0) * width
            y = height - ((v - ymin) / (ymax - ymin) * height)
            coords.extend([x, y])
        self.create_line(*coords, fill="#58d1c9", width=2, smooth=True)
        self.create_text(8, 8, anchor="nw", text=f"{ymin:.2f}", fill=COLORS["muted"])
        self.create_text(8, height - 8, anchor="sw", text=f"{ymax:.2f}", fill=COLORS["muted"])
