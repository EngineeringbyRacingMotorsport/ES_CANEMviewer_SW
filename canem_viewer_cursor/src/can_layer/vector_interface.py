from __future__ import annotations

import random
import threading
import time
from queue import Queue
from typing import Optional, Tuple


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
            msg = bus.recv(timeout=0.05)
            if msg is None:
                continue

            try:
                self.output_queue.put_nowait(msg)
            except Exception:
                pass
        
        bus.shutdown()


class PCANUSBReader(threading.Thread):
    def __init__(
        self,
        output_queue: Queue,
        stop_event: threading.Event,
        channel: str = "PCAN_USBBUS1",
        bitrate: int = 250000,
    ) -> None:
        super().__init__(daemon=True)
        self.output_queue = output_queue
        self.stop_event = stop_event
        self.channel = channel
        self.bitrate = bitrate

    def run(self) -> None:
        import can

        try:
            bus = can.interface.Bus(
                bustype="pcan",
                channel=self.channel,
                bitrate=self.bitrate,
            )
        except Exception as e:
            print(f"PCANUSBReader: Error creant bus: {e}")
            return

        while not self.stop_event.is_set():
            msg = bus.recv(timeout=0.05)
            if msg is None:
                continue

            try:
                self.output_queue.put_nowait(msg)
            except Exception:
                pass
        
        bus.shutdown()


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
                
                # TSAL (ID 1280) - REMOVED to avoid interference with real CAN data
                # If real CAN data is being received, demo data should not be generated
                
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


def detect_vector_available(channel: int = 0, app_name: str = "CANalyzer") -> bool:
    """
    Detecta si el hardware Vector està disponible i accessible.
    
    Args:
        channel: Canal Vector a provar (per defecte: 0)
        app_name: Nom de l'aplicació Vector
        
    Returns:
        True si Vector és accessible, False en altres casos
    """
    try:
        import can
        bus = can.interface.Bus(
            bustype="vector",
            channel=channel,
            bitrate=250000,
            app_name=app_name,
        )
        bus.shutdown()
        print("✓ Vector hardware detectat i disponible")
        return True
    except Exception as e:
        print(f"✗ Vector no disponible: {e}")
        return False


def detect_pcan_available(channel: str = "PCAN_USBBUS1") -> bool:
    """
    Detecta si el hardware PCAN-USB està disponible i accessible.
    
    Args:
        channel: Canal PCAN a provar (per defecte: PCAN_USBBUS1)
        
    Returns:
        True si PCAN és accessible, False en altres casos
    """
    try:
        import can
        print(f"  Intentant connectar a {channel}...")
        bus = can.interface.Bus(
            bustype="pcan",
            channel=channel,
            bitrate=250000,
        )
        bus.shutdown()
        print("✓ PCAN-USB hardware detectat i disponible")
        return True
    except Exception as e:
        print(f"✗ PCAN no disponible en {channel}: {type(e).__name__}: {e}")
        return False


def list_pcan_channels() -> list:
    """
    Llista tots els canals PCAN disponibles al sistema.
    
    Returns:
        Llista de canals PCAN disponibles
    """
    possible_channels = [
        "PCAN_USBBUS1",
        "PCAN_USBBUS2",
        "PCAN_USBBUS3",
        "PCAN_USBBUS4",
        "PCAN_USBBUS5",
        "PCAN_USBBUS6",
        "PCAN_USBBUS7",
        "PCAN_USBBUS8",
    ]
    
    available = []
    for channel in possible_channels:
        try:
            import can
            bus = can.interface.Bus(
                bustype="pcan",
                channel=channel,
                bitrate=250000,
                timeout=0.5,
            )
            bus.shutdown()
            available.append(channel)
        except Exception:
            pass
    
    return available


def auto_detect_interface(
    vector_channel: int = 0,
    vector_app_name: str = "CANalyzer",
    pcan_channel: str = "PCAN_USBBUS1",
) -> Tuple[str, dict]:
    """
    Detecta automàticament quin interface CAN està disponible.
    Prioritat: PCAN > Vector > Cap hardware
    
    Args:
        vector_channel: Canal Vector a provar
        vector_app_name: Nom aplicació Vector
        pcan_channel: Canal PCAN a provar
        
    Returns:
        Tupla (interface, config) on:
        - interface: "pcan", "vector" o "none"
        - config: diccionari amb paràmetres de configuració
    """
    print("\n" + "=" * 60)
    print("DETECCIÓ AUTOMÀTICA D'INTERFACES CAN")
    print("=" * 60)
    
    # Provar PCAN primer
    print("\n[1/2] Provant PCAN-USB...")
    if detect_pcan_available(pcan_channel):
        return "pcan", {
            "pcan_channel": pcan_channel,
            "pcan_bitrate": 250000,
        }
    
    # Provar Vector
    print("\n[2/2] Provant Vector...")
    if detect_vector_available(vector_channel, vector_app_name):
        return "vector", {
            "vector_channel": vector_channel,
            "vector_bitrate": 250000,
            "vector_app_name": vector_app_name,
        }
    
    # Cap hardware disponible
    print("\n✗ Cap hardware CAN detectat. Executant en mode sense hardware...")
    print("=" * 60 + "\n")
    return "none", {}
