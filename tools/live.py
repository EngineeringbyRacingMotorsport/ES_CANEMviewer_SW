"""
Shows the signals received live from a CAN adapter (Vector, PCAN-USB, ...).

Run from the project root:
    python -m tools.live --list
    python -m tools.live [--interface pcan] [--channel PCAN_USBBUS1] [--bitrate 500000]
                         [--message BMS_Status] [--mode I] [--json EMXCAN.json]
                         [--save drive.sqlite]

Without --channel, the only connected adapter is used. Without --bitrate,
Vector adapters keep the one they have, so the channel can be shared with
CANalyzer, and PCAN adapters use 500 kbit/s. Each second, the frames received per message are printed, followed by
the latest value and state of each signal of --message. Stop with Ctrl+C;
--save then writes the received data, which tools.plot can open.
"""

import argparse
import sys
import time
from can.typechecking import Channel
from src.can import CanBusReceiver, detect_channels, supported_interfaces
from src.schema import get_all, quote_ident
from src.state import Mode, get_latest_state
from src.utils import unwrap

# What each interface needs installed, for when it can't be opened
DRIVERS = {
    "vector": "the Vector XL Driver Library (and the channel is assigned in Vector Hardware Config)",
    "pcan": "PCAN-Basic (Windows) or PCBUSB from mac-can.com (macOS)",
    "socketcan": "the interface is up (sudo ip link set can0 up type can bitrate 500000)",
}


def main() -> int:
    interfaces = supported_interfaces()
    parser = argparse.ArgumentParser(
        description="Show the signals received live from a CAN adapter."
    )
    parser.add_argument(
        "--list", action="store_true", help="list the connected adapters"
    )
    parser.add_argument("--interface", choices=interfaces, help="python-can interface")
    parser.add_argument(
        "--channel", help="e.g. 0 (vector), PCAN_USBBUS1 (pcan), can0 (socketcan)"
    )
    parser.add_argument("--bitrate", type=int, help="e.g. 500000")
    parser.add_argument("--message", help="message whose signals to show")
    parser.add_argument("--mode", choices=[m.name for m in Mode], default=Mode.I.name)
    parser.add_argument("--json", default="EMXCAN.json", help="signal metadata file")
    parser.add_argument("--save", help="SQLite file to write the received data to")
    args = parser.parse_args()

    if args.list:
        channels = detect_channels()
        if not channels:
            print(f"No adapters found (looked for: {', '.join(interfaces)})")
        for config in channels:
            print(", ".join(f"{k}={v}" for k, v in config.items()))
        return 0

    picked = pick_channel(args.interface, args.channel)
    if picked is None:
        return 1
    interface, channel = picked

    schema, can, conn = unwrap(get_all(args.json))
    if args.message is not None and args.message not in schema.Messages:
        print(f"Unknown message {args.message}", file=sys.stderr)
        return 1

    receiver = CanBusReceiver(can, conn, interface, channel, args.bitrate)
    try:
        receiver.start()
    except Exception as e:
        print(f"Couldn't open {interface} channel {channel}: {e}", file=sys.stderr)
        if interface in DRIVERS:
            print(f"Check that {DRIVERS[interface]} is installed", file=sys.stderr)
        return 1

    print(f"Listening on {interface} channel {channel}, Ctrl+C to stop")
    try:
        while receiver.running:
            time.sleep(1)
            receiver.flush()
            show(receiver, args.message, Mode[args.mode])
        print(f"Receiving stopped: {receiver.last_error}", file=sys.stderr)
    except KeyboardInterrupt:
        pass
    finally:
        receiver.stop()
        receiver.flush()
        if args.save is not None:
            with open(args.save, "wb") as f:
                f.write(conn.serialize())
            print(f"Saved {receiver.received} frames to {args.save}")
    return 0 if receiver.last_error is None else 1


## Interface and channel to open, from the arguments or the connected adapters
def pick_channel(
    interface: str | None, channel: str | None
) -> tuple[str, Channel] | None:
    if channel is not None:
        # Vector channels are indexes
        return (
            interface or supported_interfaces()[0],
            int(channel) if channel.isdigit() else channel,
        )

    channels = [
        c for c in detect_channels() if interface is None or c["interface"] == interface
    ]
    if len(channels) == 1:
        return (channels[0]["interface"], channels[0]["channel"])
    if not channels:
        print("No adapters found, pass --interface and --channel", file=sys.stderr)
    else:
        print("Several adapters found, pick one with --channel:", file=sys.stderr)
        for c in channels:
            print(
                f"  --interface {c['interface']} --channel {c['channel']}",
                file=sys.stderr,
            )
    return None


def show(receiver: CanBusReceiver, message: str | None, mode: Mode) -> None:
    schema, _, conn = unwrap(get_all())
    print(f"\n{receiver.received} frames stored, {receiver.dropped} dropped")
    if receiver.last_error is not None:
        print(f"Last error: {receiver.last_error}")

    for name in schema.Messages:
        count = conn.execute(f"SELECT COUNT(*) FROM {quote_ident(name)}").fetchone()[0]
        if count:
            print(f"  {name}: {count}")

    if message is not None:
        for signal, (value, state) in get_latest_state(mode, message).items():
            print(f"    {signal} = {value} ({state.name})")


if __name__ == "__main__":
    sys.exit(main())
