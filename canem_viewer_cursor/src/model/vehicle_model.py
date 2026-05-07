from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple

from src.decoder.dbc_decoder import DBCDecoder


STATUS_PRIORITY = {"OK": 0, "WARNING": 1, "ERROR": 2, "TIMEOUT": 3}


@dataclass
class SignalConfig:
    min_valid: Optional[float] = None
    max_valid: Optional[float] = None
    timeout_s: float = 0.6
    freeze_window_s: float = 2.0
    freeze_eps: float = 1e-6


@dataclass
class SignalState:
    name: str
    unit: str = ""
    description: str = ""
    value: float = 0.0
    min: float = 0.0
    max: float = 0.0
    timestamp: float = 0.0
    status: str = "TIMEOUT"
    history: Deque[Tuple[float, float]] = field(default_factory=lambda: deque(maxlen=6000))
    cfg: SignalConfig = field(default_factory=SignalConfig)

    def update(self, ts: float, value: float) -> None:
        self.value = value
        self.timestamp = ts
        self.history.append((ts, value))
        cutoff = ts - 60.0
        while self.history and self.history[0][0] < cutoff:
            self.history.popleft()
        values = [v for t, v in self.history if t >= cutoff]
        if values:
            self.min = min(values)
            self.max = max(values)


@dataclass
class PCBState:
    name: str
    signals: Dict[str, SignalState] = field(default_factory=dict)
    status: str = "TIMEOUT"
    last_update_ts: float = 0.0


@dataclass
class VehicleState:
    pcbs: Dict[str, PCBState] = field(default_factory=dict)
    traction_on: bool = False
    battery_voltage: float = 0.0
    battery_temp: float = 0.0
    global_status: str = "TIMEOUT"
    critical_alerts: List[str] = field(default_factory=list)


class VehicleModel:
    def __init__(self, dbc_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self.vehicle = VehicleState()
        if dbc_path:
            self.initialize_from_dbc(dbc_path)

    def initialize_from_dbc(self, dbc_path: str) -> None:
        """Initialize all signals from DBC file with TIMEOUT status"""
        try:
            decoder = DBCDecoder(dbc_path)
            if not decoder.available:
                return
            
            with self._lock:
                for message in decoder.db.messages:
                    # Merge FrontECU_Main and FrontECU_Status into "FrontECU"
                    # Merge RearECU_Main and RearECU_Status into "RearECU"
                    if message.name == "FrontECU_Main":
                        pcb_name = "FrontECU"
                    elif message.name == "FrontECU_Status":
                        pcb_name = "FrontECU"
                    elif message.name == "RearECU_Main":
                        pcb_name = "RearECU"
                    elif message.name == "RearECU_Status":
                        pcb_name = "RearECU"
                    else:
                        pcb_name = message.name
                    
                    pcb = self.vehicle.pcbs.setdefault(pcb_name, PCBState(name=pcb_name))
                    
                    for signal in message.signals:
                        # Use original signal names from DBC (no prefixes)
                        signal_state = SignalState(
                            name=signal.name,  # Original name from DBC
                            unit=signal.unit or "",
                            description=signal.comment or "",
                            status="TIMEOUT",  # Initially all signals are in timeout
                            cfg=SignalConfig(timeout_s=0.8)
                        )
                        pcb.signals[signal.name] = signal_state
        except Exception:
            pass  # Silently fail if DBC can't be loaded

    def lock(self) -> threading.RLock:
        return self._lock

    def update_signal(
        self,
        pcb_name: str,
        signal_name: str,
        value: float,
        timestamp: Optional[float] = None,
        unit: str = "",
        description: str = "",
        config: Optional[SignalConfig] = None,
    ) -> SignalState:
        ts = timestamp if timestamp is not None else time.time()
        with self._lock:
            pcb = self.vehicle.pcbs.setdefault(pcb_name, PCBState(name=pcb_name))
            signal = pcb.signals.setdefault(
                signal_name,
                SignalState(
                    name=signal_name,
                    unit=unit,
                    description=description,
                    cfg=config or SignalConfig(),
                ),
            )
            if unit and not signal.unit:
                signal.unit = unit
            if description and not signal.description:
                signal.description = description
            signal.update(ts, value)
            pcb.last_update_ts = ts
            return signal

    def recompute_global_state(self) -> None:
        with self._lock:
            max_prio = 0
            alerts: List[str] = []
            for pcb in self.vehicle.pcbs.values():
                pcb_max = 0
                for signal in pcb.signals.values():
                    prio = STATUS_PRIORITY.get(signal.status, 0)
                    pcb_max = max(pcb_max, prio)
                    if signal.status in ("ERROR", "TIMEOUT"):
                        alerts.append(f"{pcb.name}.{signal.name}: {signal.status}")
                pcb.status = _status_from_priority(pcb_max)
                max_prio = max(max_prio, pcb_max)
            self.vehicle.global_status = _status_from_priority(max_prio)
            self.vehicle.critical_alerts = alerts[:5]

            self.vehicle.battery_voltage = self._safe_signal_value("BMS", "pack_voltage")
            self.vehicle.battery_temp = self._safe_signal_value("BMS", "pack_temp")
            self.vehicle.traction_on = self._safe_signal_value("VCU", "traction_enable") > 0.5

    def check_timeouts(self, now: Optional[float] = None) -> None:
        ts_now = now if now is not None else time.time()
        with self._lock:
            for pcb in self.vehicle.pcbs.values():
                for signal in pcb.signals.values():
                    if signal.timestamp <= 0:
                        signal.status = "TIMEOUT"
                    elif ts_now - signal.timestamp > signal.cfg.timeout_s:
                        signal.status = "TIMEOUT"

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "vehicle": {
                    "pcbs": {
                        pcb_name: {
                            "signals": {
                                sig_name: {
                                    "value": sig.value,
                                    "min": sig.min,
                                    "max": sig.max,
                                    "unit": sig.unit,
                                    "timestamp": sig.timestamp,
                                    "status": sig.status,
                                    "description": sig.description,
                                    "history": list(sig.history),
                                }
                                for sig_name, sig in pcb.signals.items()
                            }
                        }
                        for pcb_name, pcb in self.vehicle.pcbs.items()
                    },
                    "traction_on": self.vehicle.traction_on,
                    "battery_voltage": self.vehicle.battery_voltage,
                    "battery_temp": self.vehicle.battery_temp,
                    "global_status": self.vehicle.global_status,
                    "critical_alerts": list(self.vehicle.critical_alerts),
                }
            }

    def _safe_signal_value(self, pcb_name: str, signal_name: str) -> float:
        pcb = self.vehicle.pcbs.get(pcb_name)
        if not pcb:
            return 0.0
        sig = pcb.signals.get(signal_name)
        if not sig:
            return 0.0
        return sig.value


def _status_from_priority(prio: int) -> str:
    for name, level in STATUS_PRIORITY.items():
        if level == prio:
            return name
    return "OK"
