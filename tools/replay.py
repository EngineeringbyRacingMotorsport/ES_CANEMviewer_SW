"""
Replays a recording onto a Vector virtual CAN channel, at its original timing
and over and over, so the app can be tried without the car: connect it to the
other virtual channel ("vector · 0") while this runs.

Run from the project root:
    python -m tools.replay [recording]      (default: example.cpf)

Only virtual channels are used, so frames can never end up on a real bus.
Stop with Ctrl+C.
"""

import can
import os
import sys
import time
from collections.abc import Iterator
from src.can import _read_packet, detect_channels

VIRTUAL = 1  # XL_HWTYPE_VIRTUAL


## Frames of a recording as (seconds since the first frame, message)
def frames(path: str) -> Iterator[tuple[float, can.Message]]:
    if os.path.splitext(path)[1].lower() == ".cpf":
        with open(path, "rb") as f:
            while (packet := _read_packet(f)) is not None:
                frame_id, ms, data = packet
                yield ms / 1000, can.Message(
                    arbitration_id=frame_id, data=data, is_extended_id=frame_id > 0x7FF
                )
        return

    first: float | None = None
    with can.LogReader(path) as reader:
        for msg in reader:
            if msg.is_error_frame or msg.is_remote_frame:
                continue
            first = msg.timestamp if first is None else first
            yield msg.timestamp - first, msg


def main(path: str) -> int:
    virtual = [c for c in detect_channels() if c.get("hw_type") == VIRTUAL]
    if len(virtual) < 2:
        print(
            "Two Vector virtual channels are needed (Windows, with the Vector XL"
            " Driver Library installed)",
            file=sys.stderr,
        )
        return 1

    # Send on the last one, so the app can take the first
    config = virtual[-1]
    with can.Bus(interface="vector", channel=config["channel"], serial=config["serial"]) as bus:
        print(f"Replaying {path} on vector channel {config['channel']}, Ctrl+C to stop")
        try:
            while True:
                start = time.perf_counter()
                count = 0
                for offset, msg in frames(path):
                    delay = start + offset - time.perf_counter()
                    if delay > 0:
                        time.sleep(delay)
                    bus.send(msg)
                    count += 1
                print(f"Sent {count} frames, starting again")
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "example.cpf"))
