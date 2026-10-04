import cantools
import socket
from abc import ABC, abstractmethod
from cantools.typechecking import DecodeResultType
from io import BufferedIOBase, BufferedReader, FileIO, RawIOBase
from typing import *  # pyright: ignore[reportWildcardImportFromLibrary]

MIN_PACKET_SIZE: Final[int] = 2
MAX_PACKET_SIZE: Final[int] = 14


class CanSource(ABC):
    @abstractmethod
    def next(self) -> tuple[int, memoryview] | None: ...


class CanSourceIO(CanSource):
    io: RawIOBase | BufferedIOBase

    def __init__(self, io: RawIOBase | BufferedIOBase | str) -> None:
        self.io = BufferedReader(FileIO(io)) if isinstance(io, str) else io

    @override
    def next(self) -> tuple[int, memoryview] | None:
        return read_packet(self.io)


class CanSourceUDP(CanSource):
    sock: socket.socket

    def __init__(self, port: int = 0) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", port))

    @override
    def next(self) -> tuple[int, memoryview] | None:
        buf = self.sock.recv(MAX_PACKET_SIZE)
        if len(buf) == 0:
            return None
        return parse_packet(memoryview(buf))


class CanReader:
    source: CanSource
    db: cantools.database.can.Database

    def __init__(
        self, source: CanSource | str, db: cantools.database.can.Database | str
    ) -> None:
        self.source = CanSourceIO(source) if isinstance(source, str) else source
        if isinstance(db, str):
            database = cantools.database.load_file(db, database_format="dbc")
            if isinstance(database, cantools.database.can.Database):
                self.db = database
            else:
                raise TypeError("Unsupported database type")
        else:
            self.db = db

    def next(
        self,
    ) -> tuple[cantools.database.can.Message, DecodeResultType] | None:
        while True:
            data = self.source.next()
            if data is None:
                return
            (frame_id, payload) = data

            msg: cantools.database.can.Message
            try:
                msg = self.db.get_message_by_frame_id(frame_id)
            except KeyError:
                continue

            dec = msg.decode(payload.tobytes(), allow_truncated=True)
            return (msg, dec)

    def __iter__(
        self,
    ) -> Generator[tuple[cantools.database.can.Message, DecodeResultType]]:
        while True:
            data = self.next()
            if data is None:
                return
            yield data


## Parse Unsigned LEB128 Encoded Integral
def parse_uleb128(b: memoryview, max_val: int = 0x1FFF_FFFF) -> tuple[int, memoryview]:
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
def parse_packet(b: memoryview) -> tuple[int, memoryview]:
    frame_id, b = parse_uleb128(b)
    data_len: int = b[0]
    if data_len > 8:
        raise ValueError("Invalid packet data length")
    data: memoryview = b[1 : 1 + data_len]
    if len(data) != data_len:
        raise Exception("Unexpected end of stream")
    b = b[1 + data_len :]
    return (frame_id, data)


## Read Unsigned LEB128 Encoded Integral
def read_uleb128(
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
def read_packet(io: RawIOBase | BufferedIOBase) -> tuple[int, memoryview] | None:
    frame_id: int | None = read_uleb128(io)
    if frame_id is None:
        return None

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

    return (frame_id, memoryview(buf))
