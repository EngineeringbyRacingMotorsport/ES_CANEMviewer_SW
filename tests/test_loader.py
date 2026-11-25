"""
Checks that datalogger files load the way the app needs, using altered copies
of example.cpf (make it with tools.gen_example first).

Run from the project root: python -m tests.test_loader
"""

import io
import os
import sqlite3
import tempfile
from src.can import _read_packet, read_recording
from src.schema import get_all, load_database, new_connection, quote_ident
from src.state import get_newest_time
from tools.gen_example import write_packet


def frame_count() -> int:
    schema, _, conn = get_all()
    return sum(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(m)}").fetchone()[0] for m in schema.Messages)


def load(path: str):
    get_all("EMXCAN.json")  # a fresh, empty database
    return read_recording(path)


def main() -> None:
    data = open("example.cpf", "rb").read()
    reader = io.BytesIO(data)
    packets = []
    while (packet := _read_packet(reader)) is not None:
        packets.append(packet)
    n = len(packets)

    with tempfile.TemporaryDirectory() as folder:

        def write(name: str, items) -> str:
            path = os.path.join(folder, name)
            with open(path, "wb") as f:
                for frame_id, ms, payload in items:
                    write_packet(f, frame_id, ms, payload)
            return path

        assert load("example.cpf") == (n, 0, [], None)

        # Cut off mid-frame, as when the logger loses power: the rest is kept
        path = os.path.join(folder, "cut.cpf")
        open(path, "wb").write(data[:-5])
        loaded = load(path)
        assert loaded.frames == n - 1 and loaded.stopped and "Unexpected end" in loaded.stopped

        # An inverter register missing from the DBC and an unknown id are skipped
        loaded = load(write("unknown.cpf", [(0x103, 0, bytes(8)), (0x7AB, 0, bytes(8))] + packets))
        assert loaded == (n, 2, [], None)

        # The logger's clock starting at 50 s and restarting at 0 halfway: one
        # timeline from 0, the second piece 10 ms after the first
        half = n // 2
        first_end = packets[half - 1][1] - packets[0][1]
        loaded = load(write(
            "restart.cpf",
            [(f, ms + 50_000, d) for f, ms, d in packets[:half]]
            + [(f, ms - packets[half][1], d) for f, ms, d in packets[half:]],
        ))
        assert loaded.restarts == [first_end + 10] and loaded.frames == n
        assert get_newest_time() == first_end + 10 + packets[-1][1] - packets[half][1]

        # Frames logged a few ms out of order aren't restarts
        loaded = load(write("jitter.cpf", [(f, max(0, ms - (5 if i % 100 == 1 else 0)), d) for i, (f, ms, d) in enumerate(packets)]))
        assert loaded.restarts == []

        # A saved database loads again; one with other tables is refused
        load("example.cpf")
        path = os.path.join(folder, "saved.sqlite")
        open(path, "wb").write(get_all()[2].serialize())
        assert load_database(path).execute('SELECT COUNT(*) FROM "FrontECU_M2"').fetchone()[0] == 6000
        other = sqlite3.connect(":memory:")
        other.execute('CREATE TABLE "FrontECU_M2" (x)')
        path = os.path.join(folder, "other.sqlite")
        open(path, "wb").write(other.serialize())
        try:
            load_database(path)
            raise AssertionError("a database with other tables was loaded")
        except ValueError:
            pass

        # Loading into a new database leaves the one in use alone
        get_all("EMXCAN.json")
        conn = new_connection()
        read_recording("example.cpf", conn)
        assert frame_count() == 0
        assert conn.execute('SELECT COUNT(*) FROM "FrontECU_M2"').fetchone()[0] == 6000

    print("OK")


if __name__ == "__main__":
    main()
