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

        try:
            bus = can.interface.Bus(
                bustype="vector",
                channel=self.channel,
                bitrate=self.bitrate,
                app_name=self.app_name,
            )
        except Exception as e:
            print(f"VectorCANReader: Error creant bus: {e}")
            return

        while not self.stop_event.is_set():
            msg = bus.recv(timeout=0.05)  # Canviat a 50ms
            if msg is None:
                continue
            
            try:
                self.output_queue.put_nowait(msg)
            except Exception:
                pass


class NoVectorReader(threading.Thread):
    def __init__(self, output_queue: Queue, stop_event: threading.Event) -> None:
        super().__init__(daemon=True)
        self.output_queue = output_queue
        self.stop_event = stop_event

    def run(self) -> None:
        # This reader doesn't send any data - just waits for stop event
        while not self.stop_event.is_set():
            time.sleep(0.1)


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
                # FrontECU Main (ID 256)
                ("FrontECU", "FpANLvaccu", 12.0 + 2.0 * _sin(t, 0.2), "V", "Accumulator voltage"),
                ("FrontECU", "FpANLtaccu", 25.0 + 10.0 * _sin(t, 0.1), "degC", "Accumulator temperature"),
                ("FrontECU", "FpDIGvel", 50.0 + 30.0 * _sin(t, 0.5), "km/h", "Vehicle speed"),
                ("FrontECU", "FpANLRpot", 75.0 + 20.0 * _sin(t, 0.3), "%", "Right accelerator pedal"),
                ("FrontECU", "FpANLLpot", 75.0 + 20.0 * _sin(t, 0.3), "%", "Left accelerator pedal"),
                ("FrontECU", "FpANLbrake", 5.0 + 3.0 * _sin(t, 0.4), "MPa", "Brake pressure"),
                
                # FrontECU Status (ID 257)
                ("FrontECU", "FpINTebms", 1.0 if int(t) % 20 < 18 else 0.0, "", "BMS error flag"),
                ("FrontECU", "FpINTeimd", 1.0 if int(t) % 25 < 23 else 0.0, "", "IMD error flag"),
                ("FrontECU", "FpINTtsoff", 0.0, "", "TS OFF flag"),
                ("FrontECU", "FpINTsbms", 1.0, "", "BMS shutdown flag"),
                ("FrontECU", "FpINTpre", 1.0 if int(t) % 30 < 25 else 0.0, "", "Precharge flag"),
                
                # RearECU Main (ID 512)
                ("RearECU", "RpSIGItempM", 35.0 + 8.0 * _sin(t, 0.2), "degC", "Motor inverter temperature"),
                ("RearECU", "RpSIGOtempM", 40.0 + 6.0 * _sin(t, 0.15), "degC", "Motor out temperature"),
                ("RearECU", "RpSIGItempI", 32.0 + 5.0 * _sin(t, 0.25), "degC", "Inverter in temperature"),
                ("RearECU", "RpSIGOtempI", 38.0 + 4.0 * _sin(t, 0.18), "degC", "Inverter out temperature"),
                ("RearECU", "RpSIGRspeed", 45.0 + 25.0 * _sin(t, 0.6), "km/h", "Right wheel speed"),
                ("RearECU", "RpSIGLspeed", 45.0 + 25.0 * _sin(t, 0.6), "km/h", "Left wheel speed"),
                ("RearECU", "RpSIGlvs", 13.2 + 0.5 * _sin(t, 0.1), "V", "Low voltage system"),
                
                # RearECU Status (ID 513)
                ("RearECU", "RpSDChvd", 1.0, "", "HV disable flag"),
                ("RearECU", "RpSTAbrkledR", 1.0 if int(t) % 10 < 8 else 0.0, "", "Brake LED red"),
                ("RearECU", "RpSTArefriaccu", 1.0 if int(t) % 15 < 12 else 0.0, "", "Accumulator cooling"),
                
                # HVDB (ID 1024)
                ("HVDB", "BpTHRbrake", 1.0 if int(t) % 5 < 4 else 0.0, "", "Brake plausibility"),
                ("HVDB", "BpTHRcurrent", 1.0 if int(t) % 8 < 7 else 0.0, "", "Current plausibility"),
                ("HVDB", "BpSDC", 1.0, "", "SDC status"),
                
                # HVAB (ID 768)
                ("HVAB", "ApTHRhv", 1.0, "", "HV threshold"),
                ("HVAB", "ApSHU", 1500.0 + 200.0 * _sin(t, 0.3), "mA", "HVAB current"),
                
                # TSAL (ID 1280)
                ("TSAL", "TpDIGspre", 1.0 if int(t) % 12 < 10 else 0.0, "", "Precharge relay"),
                ("TSAL", "TpDIGsairp", 1.0 if int(t) % 20 < 18 else 0.0, "", "Air positive relay"),
                ("TSAL", "TpDIGsairn", 1.0 if int(t) % 20 < 18 else 0.0, "", "Air negative relay"),
                ("TSAL", "TpTHRhv", 1.0, "", "TSAL HV threshold"),
                
                # SDC (ID 1536)
                ("SDC", "SpERRbms", 0.0, "", "SDC BMS error"),
                ("SDC", "SpERRimd", 0.0, "", "SDC IMD error"),
                ("SDC", "SpSDCbms", 1.0, "", "SDC BMS status"),
                ("SDC", "SpSDCimd", 1.0, "", "SDC IMD status"),
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
