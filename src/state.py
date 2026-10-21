from .schema import TIMESTAMP_COLUMN, Identifier, LimitSet, get_all
from .utils import quote_ident, unwrap
from enum import Enum


class State(Enum):
    OK = 0
    WARNING = 1
    CRITICAL = 2


class Phase(Enum):
    I = 0
    P = 1
    T = 2
    R = 3


## Latest value of each signal of the message, with its state under the mode's
## limits. Signals without a value yet are left out.
def get_latest_state(
    phase: Phase,
    message: Identifier,
) -> dict[str, tuple[int | float, State]]:
    schema, _, conn = unwrap(get_all())

    keys = list[Identifier]()
    limits = list[LimitSet | None]()
    for k, s in schema.Messages[message].Signals.items():
        keys.append(k)
        limits.append(getattr(s.Viewer.Limits, phase.name.lower()))

    # Each signal is looked up on its own, since multiplexed signals are only
    # present in some of the rows
    table = quote_ident(message)
    ts = quote_ident(TIMESTAMP_COLUMN)
    columns = ", ".join(
        f"(SELECT {quote_ident(k)} FROM {table} WHERE {quote_ident(k)} IS NOT NULL"
        f" ORDER BY {ts} DESC LIMIT 1)"
        for k in keys
    )
    row = conn.execute(f"SELECT {columns}").fetchone()

    res: dict[str, tuple[int | float, State]] = {}
    for key, limit, value in zip(keys, limits, row):
        if value is not None:
            res[key] = (value, _state_of(value, limit))
    return res


## Value of each signal of the message at the given time, linearly interpolated
## between the samples around it, with its state under the mode's limits. After
## the last sample the last value is kept; signals without a sample at or before
## the time are left out.
def get_state_at(
    phase: Phase, message: Identifier, timestamp: float
) -> dict[str, tuple[float, State]]:
    schema, _, conn = unwrap(get_all())
    table = quote_ident(message)
    ts = quote_ident(TIMESTAMP_COLUMN)

    res: dict[str, tuple[float, State]] = {}
    for key, signal in schema.Messages[message].Signals.items():
        # Looked up per signal, since multiplexed signals are only present in
        # some of the rows
        column = quote_ident(key)
        value = conn.execute(
            f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL AND {ts} <= ?"
            f" ORDER BY {ts} DESC LIMIT 1",
            (timestamp,),
        ).fetchone()

        if value is None:
            continue

        limit = getattr(signal.Viewer.Limits, phase.name.lower())
        res[key] = (value, _state_of(value, limit))
    return res


def _state_of(value: int | float, limit: LimitSet | None) -> State:
    if limit is None:
        return State.OK
    if (limit.CriticalLow is not None and value < limit.CriticalLow) or (
        limit.CriticalHigh is not None and value > limit.CriticalHigh
    ):
        return State.CRITICAL
    if (limit.WarningLow is not None and value < limit.WarningLow) or (
        limit.WarningHigh is not None and value > limit.WarningHigh
    ):
        return State.WARNING
    return State.OK
