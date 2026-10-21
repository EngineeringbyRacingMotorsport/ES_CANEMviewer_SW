# Storage/Transmission Packet

- Arbitration ID
    - LEB128 Encoded Unsigned Integral
        - Max Value: 0x1FFF_FFFF
- Timestamp
    - LEB128 Encoded Unsigned Integral
        - Max Value: 0xFFFFFFFF
- Length
    - 8 Bit Unsigned Integral
- Data
    - Max length: 8 bytes

Min Packet Size: 1 + 1 + 1 + 0 = 3
Max Packet Size: 5 + 5 + 1 + 8 = 19

# Live CAN

Frames are read from a USB-CAN adapter through [python-can](https://python-can.readthedocs.io)
by `CanBusReceiver` (`src/can.py`). To check the connection, run `just live`
(or `./tasks.sh live`, `.\tasks.ps1 live`):

```
just live --list                                  # connected adapters
just live --message BMS_Status                    # only adapter, show a message
just live --interface vector --channel 0 --bitrate 500000 --save drive.sqlite
```

Without `--bitrate`, Vector adapters keep the bitrate they have, so the
channel can be shared with CANalyzer while it's open; PCAN adapters default to
500 kbit/s. The saved file can be
opened with `just plot`, which also opens CANalyzer (`.blf`, `.asc`), PCAN-View
(`.trc`) and candump (`.log`) logs.

| OS      | Vector VN1610                                                                         | PCAN-USB                                                    |
| ------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| Windows | `--interface vector --channel 0`, with the Vector XL Driver Library installed (1)     | `--interface pcan --channel PCAN_USBBUS1`, with PCAN-Basic  |
| macOS   | Not supported by Vector                                                               | `--interface pcan --channel PCAN_USBBUS1`, with PCBUSB (2)  |
| Linux   | Not supported by Vector                                                               | `--interface socketcan --channel can0` (3)                  |

1. The channel is the one assigned to the application in Vector Hardware
   Config, which is CANalyzer's by default.
2. The PCBUSB library from [mac-can.com](https://www.mac-can.com).
3. The kernel driver is built in; bring the interface up first with
   `sudo ip link set can0 up type can bitrate 500000`.
