from __future__ import annotations

import threading
import time
from queue import Empty, Queue
from typing import Optional

from src.can_layer.vector_interface import MockCANReader, VectorCANReader
from src.decoder.dbc_decoder import DBCDecoder
from src.model.vehicle_model import SignalConfig, VehicleModel
from src.persistence.saver import PersistenceWorker
from src.validation.status_engine import validate_signal


class TelemetryPipeline:
    def __init__(
        self,
        model: VehicleModel,
        mode: str,
        dbc_path: str,
        vector_channel: int,
        vector_bitrate: int,
        vector_app_name: str,
    ) -> None:
        self.model = model
        self.mode = mode
        self.raw_queue: Queue = Queue(maxsize=5000)
        self.decoded_queue: Queue = Queue(maxsize=5000)
        self.save_queue: Queue = Queue(maxsize=20)
        self.stop_event = threading.Event()

        self.decoder = DBCDecoder(dbc_path)
        self.reader = self._build_reader(vector_channel, vector_bitrate, vector_app_name)
        self.decode_thread = threading.Thread(target=self._decode_loop, daemon=True)
        self.model_thread = threading.Thread(target=self._model_loop, daemon=True)
        self.timeout_thread = threading.Thread(target=self._timeout_loop, daemon=True)
        self.persistence_thread = PersistenceWorker(model=self.model, save_queue=self.save_queue, stop_event=self.stop_event)

    def _build_reader(self, channel: int, bitrate: int, app_name: str):
        if self.mode == "vector":
            return VectorCANReader(
                output_queue=self.raw_queue,
                stop_event=self.stop_event,
                channel=channel,
                bitrate=bitrate,
                app_name=app_name,
            )
        return MockCANReader(output_queue=self.raw_queue, stop_event=self.stop_event)

    def start(self) -> None:
        self.reader.start()
        self.decode_thread.start()
        self.model_thread.start()
        self.timeout_thread.start()
        self.persistence_thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def request_save(self, fmt: str) -> None:
        try:
            self.save_queue.put_nowait({"format": fmt})
        except Exception:
            pass

    def _decode_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.raw_queue.get(timeout=0.05)
            except Empty:
                continue

            if self.mode == "mock":
                try:
                    self.decoded_queue.put_nowait(item)
                except Exception:
                    pass
                continue

            frame = item
            decoded = self.decoder.decode(frame.arbitration_id, frame.data)
            ts = frame.timestamp if getattr(frame, "timestamp", None) else time.time()
            for pcb_name, sig_name, value, unit, description in decoded:
                try:
                    self.decoded_queue.put_nowait((pcb_name, sig_name, value, unit, description, ts))
                except Exception:
                    pass

    def _model_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.decoded_queue.get(timeout=0.05)
            except Empty:
                continue

            pcb_name, sig_name, value, unit, description, ts = self._normalize_item(item)
            cfg = self._config_for(pcb_name, sig_name)
            sig = self.model.update_signal(
                pcb_name=pcb_name,
                signal_name=sig_name,
                value=value,
                timestamp=ts,
                unit=unit,
                description=description,
                config=cfg,
            )
            sig.status = validate_signal(sig, now=ts)
            self.model.recompute_global_state()

    def _timeout_loop(self) -> None:
        while not self.stop_event.is_set():
            now = time.time()
            self.model.check_timeouts(now=now)
            self.model.recompute_global_state()
            time.sleep(0.1)

    @staticmethod
    def _normalize_item(item: tuple) -> tuple[str, str, float, str, str, float]:
        if len(item) == 6:
            return item
        if len(item) == 5:
            pcb, sig, val, unit, desc = item
            return pcb, sig, float(val), unit, desc, time.time()
        if len(item) == 4:
            pcb, sig, val, ts = item
            return pcb, sig, float(val), "", "", float(ts)
        if len(item) == 3:
            pcb, sig, val = item
            return pcb, sig, float(val), "", "", time.time()
        raise ValueError("Unexpected decoded item format")

    @staticmethod
    def _config_for(pcb: str, sig: str) -> SignalConfig:
        key = f"{pcb}.{sig}"
        presets = {
            "BMS.pack_voltage": SignalConfig(min_valid=450.0, max_valid=600.0, timeout_s=0.5),
            "BMS.pack_temp": SignalConfig(min_valid=-10.0, max_valid=65.0, timeout_s=0.5),
            "INV.motor_temp": SignalConfig(min_valid=-20.0, max_valid=120.0, timeout_s=0.5),
            "IMU.lat_acc": SignalConfig(min_valid=-5.0, max_valid=5.0, timeout_s=0.5),
            "VCU.traction_enable": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
        }
        return presets.get(key, SignalConfig(timeout_s=0.8))
