from __future__ import annotations

import time

from src.model.vehicle_model import SignalState
from src.validation.car_state_manager import CarStateManager


# Global CarStateManager instance
_car_state_manager = CarStateManager()


def get_car_state_manager() -> CarStateManager:
    """Retorna la instància global del CarStateManager"""
    return _car_state_manager


def set_car_state_manager(manager: CarStateManager) -> None:
    """Estableix la instància del CarStateManager"""
    global _car_state_manager
    _car_state_manager = manager


def validate_signal(signal: SignalState, now: float | None = None) -> str:
    ts_now = now if now is not None else time.time()

    if signal.timestamp <= 0 or ts_now - signal.timestamp > signal.cfg.timeout_s:
        return "TIMEOUT"

    # Check if it's a digital signal (min=0, max=1)
    is_digital = (signal.cfg.min_valid == 0 and signal.cfg.max_valid == 1)
    
    if is_digital:
        # Validar senyal digital amb CarStateManager
        return _car_state_manager.validate_digital_signal(signal.name, signal.value)
    else:
        # Analog signals: check range
        if signal.cfg.min_valid is not None and signal.value < signal.cfg.min_valid:
            return "ERROR"
        if signal.cfg.max_valid is not None and signal.value > signal.cfg.max_valid:
            return "ERROR"

    return "OK"


def _is_frozen(signal: SignalState, now: float) -> bool:
    cutoff = now - signal.cfg.freeze_window_s
    samples = [v for t, v in signal.history if t >= cutoff]
    if len(samples) < 3:
        return False
    return (max(samples) - min(samples)) <= signal.cfg.freeze_eps
