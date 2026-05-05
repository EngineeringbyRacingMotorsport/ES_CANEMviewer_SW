from __future__ import annotations

import random
import threading
import time
from queue import Queue


class VectorCANReader(threading.Thread):
    def __init__(
        self,
        output_queue: Queue,
        stop_event: threading.Event,
        channel: int,
        bitrate: int,
        app_name: str,
    ) -> None:
        super().__init__(daemon=True)
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.channel = channel
        self.bitrate = bitrate
        self.app_name = app_name

    def run(self) -> None:
        import can

        bus = can.interface.Bus(
            bustype="vector",
            channel=self.channel,
            bitrate=self.bitrate,
            app_name=self.app_name,
        )
        while not self.stop_event.is_set():
            msg = bus.recv(timeout=0.02)
            if msg is None:
                continue
            try:
                self.output_queue.put_nowait(msg)
            except Exception:
                pass


class MockCANReader(threading.Thread):
    def __init__(self, output_queue: Queue, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.t0 = time.time()

    def run(self) -> None:
        while not self.stop_event.is_set():
            t = time.time() - self.t0
            frames = [
                ("BMS", "pack_voltage", 520.0 + 8.0 * _sin(t, 0.2), "V", "Battery pack voltage"),
                ("BMS", "pack_temp", 34.0 + 5.0 * _sin(t, 0.1), "degC", "Battery pack temperature"),
                ("VCU", "traction_enable", 1.0 if int(t) % 30 < 25 else 0.0, "", "Traction state"),
                ("IMU", "lat_acc", 0.4 * _sin(t, 1.5), "g", "Lateral acceleration"),
                ("INV", "motor_temp", 55.0 + 10.0 * _sin(t, 0.4), "degC", "Inverter temperature"),
            ]
            ts = time.time()
            for item in frames:
                try:
                    self.output_queue.put_nowait((*item, ts))
                except Exception:
                    pass
            time.sleep(0.05)


def _sin(x: float, freq: float) -> float:
    import math

    return math.sin(2.0 * math.pi * freq * x) + random.uniform(-0.02, 0.02)
