from .schema import TIMESTAMP_COLUMN, Identifier, LimitSet, get_all
from .utils import quote_ident, unwrap
from collections.abc import Iterable
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


PHASE_MESSAGE = "FrontECU_M2"
PHASE_SIGNAL = "FpSTAphase"


## Phase sent by the FrontECU, the latest one or the one at the given time.
## None before the first frame, or for a value that isn't a known phase.
def get_phase(timestamp: float | None = None) -> Phase | None:
    _, _, conn = unwrap(get_all())
    ts = quote_ident(TIMESTAMP_COLUMN)
    where, params = (f"WHERE {ts} <= ?", (timestamp,)) if timestamp is not None else ("", ())
    row = conn.execute(
        f"SELECT {quote_ident(PHASE_SIGNAL)} FROM {quote_ident(PHASE_MESSAGE)} {where}"
        f" ORDER BY {ts} DESC LIMIT 1",
        params,
    ).fetchone()
    if row is None or row[0] not in Phase._value2member_map_:
        return None
    return Phase(row[0])


## When the phase sent by the FrontECU changed, as (time in ms, phase), oldest
## first; None for a value that isn't a known phase
def get_phase_changes() -> list[tuple[int, Phase | None]]:
    _, _, conn = unwrap(get_all())
    ts = quote_ident(TIMESTAMP_COLUMN)
    changes: list[tuple[int, Phase | None]] = []
    for t, value in conn.execute(
        f"SELECT {ts}, {quote_ident(PHASE_SIGNAL)} FROM {quote_ident(PHASE_MESSAGE)} ORDER BY {ts}"
    ):
        phase = Phase(value) if value in Phase._value2member_map_ else None
        if not changes or changes[-1][1] != phase:
            changes.append((t, phase))
    return changes


## Latest value of each signal of the message, at or before `until` (ms) when
## given, with its state under the mode's limits. Signals without a value yet are
## left out.
def get_latest_state(
    phase: Phase,
    message: Identifier,
    until: int | None = None,
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
    order = _latest_first(keys)
    before, params = _until(until)
    columns = ", ".join(
        f"(SELECT {quote_ident(k)} FROM {table} WHERE {quote_ident(k)} IS NOT NULL{before}"
        f" ORDER BY {order} LIMIT 1)"
        for k in keys
    )
    row = conn.execute(f"SELECT {columns}", params * len(keys)).fetchone()

    res: dict[str, tuple[int | float, State]] = {}
    for key, limit, value in zip(keys, limits, row):
        if value is not None:
            res[key] = (value, _state_of(value, limit))
    return res


## Value of each signal of the message at the given time (in ms, as stored),
## taken from its latest sample at or before it, with its state under the mode's
## limits. Signals without a sample at or before the time are left out.
def get_state_at(
    phase: Phase, message: Identifier, timestamp: float
) -> dict[str, tuple[int | float, State]]:
    schema, _, conn = unwrap(get_all())
    signals = schema.Messages[message].Signals
    table = quote_ident(message)
    ts = quote_ident(TIMESTAMP_COLUMN)
    order = _latest_first(signals)

    res: dict[str, tuple[int | float, State]] = {}
    for key, signal in signals.items():
        # Looked up per signal, since multiplexed signals are only present in
        # some of the rows
        column = quote_ident(key)
        row = conn.execute(
            f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL AND {ts} <= ?"
            f" ORDER BY {order} LIMIT 1",
            (timestamp,),
        ).fetchone()

        if row is None:
            continue
        value = row[0]

        limit = getattr(signal.Viewer.Limits, phase.name.lower())
        res[key] = (value, _state_of(value, limit))
    return res


## Time (ms) of the latest sample of each signal of the message, at or before
## `until` when given. Signals without a sample yet are left out.
def get_latest_times(message: Identifier, until: int | None = None) -> dict[str, int]:
    schema, _, conn = unwrap(get_all())
    keys = list(schema.Messages[message].Signals)
    if not keys:
        return {}
    table = quote_ident(message)
    ts = quote_ident(TIMESTAMP_COLUMN)
    before, params = _until(until)
    columns = ", ".join(
        f"(SELECT MAX({ts}) FROM {table} WHERE {quote_ident(k)} IS NOT NULL{before})" for k in keys
    )
    row = conn.execute(f"SELECT {columns}", params * len(keys)).fetchone()
    return {k: t for k, t in zip(keys, row) if t is not None}


## Time (ms) of the newest frame of any message, None before the first one
def get_newest_time() -> int | None:
    schema, _, conn = unwrap(get_all())
    if not schema.Messages:
        return None
    ts = quote_ident(TIMESTAMP_COLUMN)
    columns = ", ".join(f"(SELECT MAX({ts}) FROM {quote_ident(m)})" for m in schema.Messages)
    return max((t for t in conn.execute(f"SELECT {columns}").fetchone() if t is not None), default=None)


## Time (ms) of the oldest frame of any message, None before the first one
def get_oldest_time() -> int | None:
    schema, _, conn = unwrap(get_all())
    if not schema.Messages:
        return None
    ts = quote_ident(TIMESTAMP_COLUMN)
    columns = ", ".join(f"(SELECT MIN({ts}) FROM {quote_ident(m)})" for m in schema.Messages)
    return min((t for t in conn.execute(f"SELECT {columns}").fetchone() if t is not None), default=None)


## Last samples of a signal, at or before `until` when given, as (time in ms,
## value), oldest first
def get_last_samples(
    message: Identifier, signal: Identifier, count: int, until: int | None = None
) -> list[tuple[int, int | float]]:
    schema, _, conn = unwrap(get_all())
    column = quote_ident(signal)
    before, params = _until(until)
    rows = conn.execute(
        f"SELECT {quote_ident(TIMESTAMP_COLUMN)}, {column} FROM {quote_ident(message)}"
        f" WHERE {column} IS NOT NULL{before}"
        f" ORDER BY {_latest_first(schema.Messages[message].Signals)} LIMIT ?",
        (*params, count),
    ).fetchall()
    return rows[::-1]


## Samples of a signal from `start` to `end` (ms, both included), oldest first,
## plus the last one before `start`, so a line reaches the window's left edge
def get_samples_between(
    message: Identifier, signal: Identifier, start: int, end: int
) -> list[tuple[int, int | float]]:
    schema, _, conn = unwrap(get_all())
    column = quote_ident(signal)
    table = quote_ident(message)
    ts = quote_ident(TIMESTAMP_COLUMN)
    order = _latest_first(schema.Messages[message].Signals)
    rows = conn.execute(
        f"SELECT {ts}, {column} FROM {table}"
        f" WHERE {column} IS NOT NULL AND {ts} BETWEEN ? AND ?"
        f" ORDER BY {order.replace('DESC', 'ASC')}",
        (start, end),
    ).fetchall()
    before = conn.execute(
        f"SELECT {ts}, {column} FROM {table} WHERE {column} IS NOT NULL AND {ts} < ?"
        f" ORDER BY {order} LIMIT 1",
        (start,),
    ).fetchone()
    return ([before] if before else []) + rows


def _until(until: int | None) -> tuple[str, tuple[int, ...]]:
    ts = quote_ident(TIMESTAMP_COLUMN)
    return (f" AND {ts} <= ?", (until,)) if until is not None else ("", ())


## Newest sample first. Timestamps are rounded to ms, so samples can share one;
## rows are stored as they arrive, so the row id breaks the tie. A signal may
## take one of the row id's names, in which case another one is used.
def _latest_first(signals: Iterable[str]) -> str:
    ts = quote_ident(TIMESTAMP_COLUMN)
    taken = {name.lower() for name in signals}
    rowid = next((n for n in ("rowid", "_rowid_", "oid") if n not in taken), None)
    return f"{ts} DESC" if rowid is None else f"{ts} DESC, {rowid} DESC"


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
