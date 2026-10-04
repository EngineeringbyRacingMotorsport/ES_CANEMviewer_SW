import sqlite3
from .schema import TIMESTAMP_COLUMN, get_all, quote_ident
from .utils import unwrap
from cantools.database.can import Database, Message
from cantools.database.namedsignalvalue import NamedSignalValue
from cantools.typechecking import DecodeResultType
from io import BufferedIOBase, RawIOBase
from typing import *  # pyright: ignore[reportWildcardImportFromLibrary]

MIN_PACKET_SIZE: Final[int] = 2
MAX_PACKET_SIZE: Final[int] = 14


def read_file(path: str):
    _, can, conn = unwrap(get_all())
    with open(path, "rb") as f:
        while True:
            next = _read_packet(f)
            if next is None:
                break
            _upload_packet(can, conn, next)


## Store a decoded packet as a row of its message's table
def _upload_packet(
    can: Database,
    conn: sqlite3.Connection,
    info: tuple[int, int, bytes],
) -> None:
    id, timestamp, data = info
    parsed = _parse_message(can, id, data)
    if parsed is None:
        return
    msg, data = parsed

    if not isinstance(data, dict):
        raise TypeError(f"Container message {msg.name} is not supported")

    # Multiplexed messages only carry some of their signals, so name the columns
    columns: list[str] = [TIMESTAMP_COLUMN]
    values: list[int | float] = [timestamp]
    for name, value in data.items():
        if isinstance(value, NamedSignalValue):
            # Store the physical value behind the choice's label
            value = msg.get_signal_by_name(name).conversion.raw_to_scaled(
                value.value, decode_choices=False
            )
        elif isinstance(value, str):
            raise TypeError(f"Signal {name} of message {msg.name} has a string value")
        columns.append(name)
        values.append(value)

    conn.execute(
        f"INSERT INTO {quote_ident(msg.name)} ({', '.join(map(quote_ident, columns))}) "
        f"VALUES ({', '.join('?' * len(values))})",
        values,
    )


def _parse_message(
    db: Database, id: int, data: bytes
) -> tuple[Message, DecodeResultType] | None:
    msg: Message
    try:
        msg = db.get_message_by_frame_id(id)
    except KeyError:
        return None

    dec = msg.decode(data, allow_truncated=True)
    return (msg, dec)


## Parse Unsigned LEB128 Encoded Integral
def _parse_uleb128(b: memoryview, max_val: int = 0x1FFF_FFFF) -> tuple[int, memoryview]:
    result: int = 0
    shift: int = 0
    while True:
        byte = b[0]
        b = b[1:]
        result |= (byte & 0x7F) << shift
        shift += 7
        if result > max_val:
            raise ValueError("Invalid integral value")
        elif (byte & 0x80) == 0:
            break
    return (result, b)


## Read a packet from the specified memory view, advancing it past the packet
def _parse_packet(b: memoryview) -> tuple[int, int, bytes]:
    frame_id, b = _parse_uleb128(b)
    timestamp, b = _parse_uleb128(b, max_val=0xFFFF_FFFF)
    data_len: int = b[0]
    if data_len > 8:
        raise ValueError("Invalid packet data length")
    data: memoryview = b[1 : 1 + data_len]
    if len(data) != data_len:
        raise Exception("Unexpected end of stream")
    return (frame_id, timestamp, data.tobytes())


## Read Unsigned LEB128 Encoded Integral
def _read_uleb128(
    io: RawIOBase | BufferedIOBase, max_val: int = 0x1FFF_FFFF
) -> int | None:
    result: int = 0
    shift: int = 0
    buf = bytearray(1)

    count: int = io.readinto(buf)
    if count == 0:
        return None

    while True:
        byte = buf[0]
        result |= (byte & 0x7F) << shift
        shift += 7
        if result > max_val:
            raise ValueError("Invalid integral value")
        elif (byte & 0x80) == 0:
            break
        count = io.readinto(buf)
        if count == 0:
            raise Exception("Unexpected end of stream")

    return result


## Read a packet from the specified io reader, advancing it past the packet
def _read_packet(io: RawIOBase | BufferedIOBase) -> tuple[int, int, bytes] | None:
    frame_id: int | None = _read_uleb128(io)
    if frame_id is None:
        return None

    timestamp = unwrap(_read_uleb128(io, max_val=0xFFFF_FFFF))
    len_byte = io.read(1)
    if len(len_byte) == 0:
        raise Exception("Unexpected end of stream")

    data_len: int = len_byte[0]
    if data_len > 8:
        raise ValueError("Invalid packet data length")

    buf = bytearray(data_len)
    view = memoryview(buf)
    while len(view) > 0:
        count = io.readinto(view)
        if count == 0:
            raise Exception("Unexpected end of stream")
        else:
            view = view[count:]

    return (frame_id, timestamp, bytes(buf))
