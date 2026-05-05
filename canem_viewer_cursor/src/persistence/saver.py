from __future__ import annotations

import json
import pickle
import threading
import time
from pathlib import Path
from queue import Empty, Queue

from src.model.vehicle_model import VehicleModel


class PersistenceWorker(threading.Thread):
    def __init__(self, model: VehicleModel, save_queue: Queue, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.model = model
        self.save_queue = save_queue
        self.stop_event = stop_event
        self.out_dir = Path("logs")
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> None:
        while not self.stop_event.is_set():
            try:
                req = self.save_queue.get(timeout=0.2)
            except Empty:
                continue
            if not isinstance(req, dict):
                continue
            fmt = req.get("format", "pickle")
            snap = self.model.snapshot()
            ts = time.strftime("%Y%m%d_%H%M%S")
            if fmt == "json":
                path = self.out_dir / f"telemetry_{ts}.json"
                path.write_text(json.dumps(snap, ensure_ascii=False, indent=2), encoding="utf-8")
            else:
                path = self.out_dir / f"telemetry_{ts}.pkl"
                with path.open("wb") as fp:
                    pickle.dump(snap, fp, protocol=pickle.HIGHEST_PROTOCOL)
