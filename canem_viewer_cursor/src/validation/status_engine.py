from __future__ import annotations

import time

from src.model.vehicle_model import SignalState


def validate_signal(signal: SignalState, now: float | None = None) -> str:
    ts_now = now if now is not None else time.time()

    if signal.timestamp <= 0 or ts_now - signal.timestamp > signal.cfg.timeout_s:
        return "TIMEOUT"

    if signal.cfg.min_valid is not None and signal.value < signal.cfg.min_valid:
        return "ERROR"
    if signal.cfg.max_valid is not None and signal.value > signal.cfg.max_valid:
        return "ERROR"

    if _is_frozen(signal, ts_now):
        return "WARNING"

    return "OK"


def _is_frozen(signal: SignalState, now: float) -> bool:
    cutoff = now - signal.cfg.freeze_window_s
    samples = [v for t, v in signal.history if t >= cutoff]
    if len(samples) < 3:
        return False
    return (max(samples) - min(samples)) <= signal.cfg.freeze_eps
