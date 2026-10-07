import asyncio
import queue
import sqlite3
import threading
from .schema import TIMESTAMP_COLUMN, get_all, quote_ident
from .utils import unwrap
from cantools.database.can import Database, Message
from cantools.database.namedsignalvalue import NamedSignalValue
from cantools.typechecking import DecodeResultType
from io import BufferedIOBase, RawIOBase
from typing import *  # pyright: ignore[reportWildcardImportFromLibrary]

MIN_PACKET_SIZE: Final[int] = 3
MAX_PACKET_SIZE: Final[int] = 19


def read_file(path: str):
    _, can, conn = unwrap(get_all())
    with open(path, "rb") as f:
        while True:
            next = _read_packet(f)
            if next is None:
                break
            _upload_packet(can, conn, next)


class UdpReceiver:
    """
    Receives packets over UDP on an asyncio event loop running in a background
    thread. They are stored in the database by flush(), which is meant to be
    called on a timer from the thread that owns the connection.
    """

    def __init__(
        self, can: Database, conn: sqlite3.Connection, port: int, host: str = "0.0.0.0"
    ) -> None:
        self.can = can
        self.conn = conn
        self.address = (host, port)
        self.received: int = 0  # packets stored
        self.last_error: Exception | None = None
        # Each counter is only written by one thread
        self._malformed: int = 0  # receiving thread
        self._unknown: int = 0  # flush()
        self._queue: queue.SimpleQueue[tuple[int, int, bytes]] = queue.SimpleQueue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._thread: threading.Thread | None = None

    @property
    def dropped(self) -> int:
        """Malformed datagrams, and packets that couldn't be stored"""
        return self._malformed + self._unknown

    @property
    def pending(self) -> int:
        """Packets received but not stored yet"""
        return self._queue.qsize()

    @property
    def port(self) -> int:
        """Port the socket is bound to, useful when constructed with port 0"""
        return unwrap(self._transport).get_extra_info("sockname")[1]

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("Receiver already started")

        # Bind here, so that errors like a port in use are raised to the caller
        loop = asyncio.new_event_loop()
        try:
            transport, protocol = loop.run_until_complete(
                loop.create_datagram_endpoint(
                    lambda: _DatagramProtocol(self), local_addr=self.address
                )
            )
        except:
            loop.close()
            raise

        self._loop = loop
        self._transport = transport
        self._thread = threading.Thread(
            target=self._run, args=(loop, protocol), name="UdpReceiver", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._thread is None:
            return
        # Closing the transport ends _run once the socket is closed
        unwrap(self._loop).call_soon_threadsafe(unwrap(self._transport).close)
        self._thread.join()
        self._thread = None
        self._loop = None
        self._transport = None

    def __enter__(self) -> "UdpReceiver":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    ## Store the received packets, returning how many were stored
    def flush(self, max_packets: int = 10_000) -> int:
        stored = 0
        with self.conn:
            for _ in range(max_packets):
                try:
                    packet = self._queue.get_nowait()
                except queue.Empty:
                    break

                try:
                    if _upload_packet(self.can, self.conn, packet):
                        stored += 1
                    else:
                        self._unknown += 1
                except Exception as e:
                    # A bad packet mustn't roll back the rest of the batch
                    self._unknown += 1
                    self.last_error = e

        self.received += stored
        return stored

    @staticmethod
    def _run(loop: asyncio.AbstractEventLoop, protocol: "_DatagramProtocol") -> None:
        try:
            loop.run_until_complete(protocol.closed)
        finally:
            loop.close()

    ## Called on the receiving thread for every datagram
    def _receive(self, datagram: bytes) -> None:
        # A datagram may hold several packets; keep the ones before an error
        rest = memoryview(datagram)
        try:
            while len(rest) > 0:
                packet, rest = _parse_packet(rest)
                self._queue.put(packet)
        except ValueError as e:
            self._malformed += 1
            self.last_error = e


class _DatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, receiver: UdpReceiver) -> None:
        self.receiver = receiver
        self.closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    @override
    def datagram_received(self, data: bytes, addr: tuple[str | Any, int]) -> None:
        self.receiver._receive(data)

    @override
    def error_received(self, exc: Exception) -> None:
        self.receiver.last_error = exc

    @override
    def connection_lost(self, exc: Exception | None) -> None:
        if exc is not None:
            self.receiver.last_error = exc
        if not self.closed.done():
            self.closed.set_result(None)


## Store a decoded packet as a row of its message's table, returning whether
## its message is in the database
def _upload_packet(
    can: Database,
    conn: sqlite3.Connection,
    info: tuple[int, int, bytes],
) -> bool:
    id, timestamp, data = info
    parsed = _parse_message(can, id, data)
    if parsed is None:
        return False
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

    return True


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
        if len(b) == 0:
            raise ValueError("Unexpected end of packet")
        byte = b[0]
        b = b[1:]
        result |= (byte & 0x7F) << shift
        shift += 7
        if result > max_val:
            raise ValueError("Invalid integral value")
        elif (byte & 0x80) == 0:
            break
    return (result, b)


## Read a packet from the specified memory view, returning it and the rest of the view
def _parse_packet(b: memoryview) -> tuple[tuple[int, int, bytes], memoryview]:
    frame_id, b = _parse_uleb128(b)
    timestamp, b = _parse_uleb128(b, max_val=0xFFFF_FFFF)
    if len(b) == 0:
        raise ValueError("Unexpected end of packet")
    data_len: int = b[0]
    if data_len > 8:
        raise ValueError("Invalid packet data length")
    data: memoryview = b[1 : 1 + data_len]
    if len(data) != data_len:
        raise ValueError("Unexpected end of packet")
    return ((frame_id, timestamp, data.tobytes()), b[1 + data_len :])


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
