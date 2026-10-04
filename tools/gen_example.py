"""
Generates a simulated drive into a packet file, using the messages defined in the
signal metadata file. Each message with a CycleTime is sent at that period.

Run from the project root: python -m tools.gen_example [json_path] [out_path]

Timeline (20 s, 10 ms ticks):
- 0..2 s: precharge, AIRs close, ready-to-drive
- 2..12 s: acceleration
- 12..16 s: braking
- 16..20 s: standstill
"""

import math
import random
import sys
from io import BufferedIOBase
from typing import Any

from src.schema import Schema, _create_database
from src.utils import read_file

DURATION_MS = 20_000
TICK_MS = 10

# Inverter registers sent in turn by InverterTX, selected by RegID
INVERTER_REGISTERS = (48, 72, 73, 74, 138, 143, 160)


def write_uleb128(out: BufferedIOBase, value: int) -> None:
    while True:
        byte = value & 0x7F
        value >>= 7
        if value != 0:
            out.write(bytes([byte | 0x80]))
        else:
            out.write(bytes([byte]))
            return


def write_packet(out: BufferedIOBase, frame_id: int, data: bytes) -> None:
    if len(data) > 8:
        raise ValueError("Invalid packet data length")
    write_uleb128(out, frame_id)
    out.write(bytes([len(data)]))
    out.write(data)


class Car:
    """Physical state of the simulated car at a given time."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.speed = 0.0  # km/h
        self.t_igbt = 32.0
        self.t_mot = 30.0
        self.inverter_register = 0

    def noise(self, amplitude: float) -> float:
        return self.rng.uniform(-amplitude, amplitude)

    def update(self, t: float, dt: float) -> None:
        self.t = t
        self.precharging = t < 1.0
        self.hv = t >= 1.0
        self.r2d = t >= 2.0
        self.accel = 2.0 <= t < 12.0
        self.braking = 12.0 <= t < 16.0

        # Throttle ramps up, then eases off towards the end of the acceleration
        self.throttle = 0.0
        if self.accel:
            self.throttle = min(95.0, 30.0 + 15.0 * (t - 2.0)) - max(
                0.0, (t - 10.0) * 20
            )
        self.brake = 0.0
        if self.braking:
            self.brake = 25.0 + 10.0 * math.sin((t - 12.0) * math.pi / 4.0)

        # Acceleration in m/s², converted to km/h
        drag = 0.2 + 0.0004 * self.speed**2
        self.speed += (self.throttle * 0.025 - self.brake * 0.2 - drag) * dt * 3.6
        self.speed = max(0.0, self.speed)

        self.current = self.throttle * 2.2 + self.noise(2.0) if self.hv else 0.0
        self.t_igbt += (self.current * 0.01 - (self.t_igbt - 32.0) * 0.02) * dt
        self.t_mot += (self.current * 0.006 - (self.t_mot - 30.0) * 0.01) * dt

    def signals(self, name: str) -> dict[str, Any] | None:
        speed = round(self.speed)
        rpm = round(self.speed / 3.6 / (2 * math.pi * 0.23) * 60 * 4.4)
        b = int  # booleans encoded as 0/1
        voltage = round(398 - self.current * 0.15) if self.hv else 0
        count = round(self.t * 10) % 256  # measurement counters

        match name:
            case "FrontECU_M1":
                return {
                    "FpDIGRpot": max(0.0, self.throttle + self.noise(0.5)),
                    "FpDIGLpot": max(0.0, self.throttle + self.noise(0.5)),
                    "FpDIGRvel": max(0, speed + self.rng.randint(-1, 1)),
                    "FpDIGLvel": max(0, speed + self.rng.randint(-1, 1)),
                    "FpANLbrake": max(0.0, self.brake + self.noise(0.3)),
                }
            case "FrontECU_M2":
                return {
                    "FpINTtsoff": 0,
                    "FpINTsbms": 0,
                    "FpINTr2d": b(self.r2d),
                    "FpINTmenu": 0,
                    "FpDIGmicrosd": 1,
                    "FpSDCinertia": 1,
                    "FpSDCbots": 1,
                    "FpSDCcsdb": 1,
                    "FpERRapps": 0,
                    "FpDIGrefri": b(self.r2d),
                    "FpDIGr2d": b(self.r2d),
                    "FpDIGvel": speed,
                    "FpSHU": 310 + self.rng.randint(-15, 15),
                }
            case "RearECU_M1":
                return {
                    "RpSHU": 290 + self.rng.randint(-15, 15),
                    "RpSDChvd": 1,
                    "RpSDCtsms": 1,
                    "RpSDClsdb": 1,
                    "RpSDCrsdb": 1,
                    "RpSTAbrkledR": b(self.braking),
                    "RpSTAbrkledG": 0,
                    "RpSTAbrkledB": 0,
                    "RpSIGlvs": 24_800 + self.rng.randint(-150, 150),
                }
            case "RearECU_M2":
                return {
                    "IpRPM": rpm,
                    "IpI": max(0, round(self.current)),
                    "IpV": voltage,
                    "IpPar": max(0, round(self.throttle * 1.4)),
                }
            case "RearECU_M3":
                return {
                    "IpT_IGBT": round(self.t_igbt),
                    "IpT_Mot": round(self.t_mot),
                    "IpErrL1": 0,
                    "IpErrH1": 0,
                    "IpErrL2": 0,
                    "IpErrH2": 0,
                }
            case "InverterRX":
                return {"FpANLRpot": round(self.throttle / 100 * 32767)}
            case "InverterTX":
                register = INVERTER_REGISTERS[self.inverter_register]
                self.inverter_register = (self.inverter_register + 1) % len(
                    INVERTER_REGISTERS
                )
                match register:
                    case 48:
                        return {"RegID": register, "iRPM": rpm}
                    case 72:
                        return {"RegID": register, "iIout": max(0, round(self.current))}
                    case 73:
                        return {"RegID": register, "iTmot": round(self.t_mot)}
                    case 74:
                        return {"RegID": register, "iTinv": round(self.t_igbt)}
                    case 138:
                        return {"RegID": register, "iVout": voltage}
                    case 143:
                        return {"RegID": register, "iErr": 0, "iWarn": 0}
                    case _:
                        return {
                            "RegID": register,
                            "iPar": max(0, round(self.throttle * 1.4)),
                        }
            case "IMD_Info_General":
                return {
                    "imdRisocorrect": 50_000,
                    "imdRisostatus": 0,
                    "imdMeascount": count,
                    "imdWarningsalarms": 0,
                    "imdDeviceactivi": 1,
                }
            case "IMD_Info_IsolationDetail":
                return {
                    "imdRisoneg": 50_000 + self.rng.randint(-500, 500),
                    "imdRisopos": 50_000 + self.rng.randint(-500, 500),
                    "imdRisooriginal": 50_000,
                    "imdIsomeascount": count,
                    "imdIquality": 100,
                }
            case "IMD_Info_Voltage":
                return {
                    "imdHVnegerth": -voltage / 2 + self.noise(0.5),
                    "imdHVposearth": voltage / 2 + self.noise(0.5),
                    "imdHVsystvolt": voltage + self.noise(0.5),
                }
            case "IMD_Info_ITSystem":
                return {
                    "imdCapacityValue": 0.5 + self.noise(0.05),
                    "imdCapmeascount": count,
                    "imdUnbalancedvalue": self.rng.randint(0, 2),
                    "imdUnbalmeascount": count,
                }
            case "HVAB":
                return {
                    "ApTHRhv": b(self.hv),
                    "ApSHU": 180 + self.rng.randint(-10, 10),
                }
            case "HVDB":
                return {
                    "BpTHRbrake": b(self.brake > 5.0),
                    "BpTHRcurrent": b(self.current > 150.0),
                    "BpERRplaus": 0,
                    "BpERRtimer": 0,
                    "BpSDC": 1,
                    "DpSDC": 1,
                    "DpTHRhv": b(self.hv),
                    "DpLCHdischarge": 0,
                    "DpSDCintlck1": 1,
                    "DpSDCintlck2": 1,
                    "BpSHU": 150 + self.rng.randint(-10, 10),
                    "DpSHU": 140 + self.rng.randint(-10, 10),
                }
            case "TSALGreen":
                return {
                    "TpDIGspre": b(self.precharging),
                    "TpDIGsairp": b(self.hv),
                    "TpDIGsairn": 1,
                    "TpDIGipre": b(self.precharging),
                    "TpDIGiairp": b(self.hv),
                    "TpDIGiairn": 1,
                    "TpTHRhv": b(self.hv),
                    "TpERRscs": 0,
                    "TpTHRdis": 0,
                    "TpLCH": 0,
                    "TpINTled": b(self.hv),
                }
            case "SDCReset":
                return {
                    "SpERRbms": 0,
                    "SpERRimd": 0,
                    "SpLCHebms": 0,
                    "SpLCHeimd": 0,
                    "SpINTresbut": 0,
                    "SpSDCbms": 1,
                    "SpSDCimd": 1,
                    "SpSHU": 120 + self.rng.randint(-10, 10),
                }
            case _:
                # Messages the car doesn't simulate
                return None


def main(json_path: str, out_path: str) -> None:
    schema = Schema.model_validate_json(read_file(json_path))
    db = _create_database(schema)
    periods = {
        name: message.CycleTime
        for name, message in schema.Messages.items()
        if message.CycleTime is not None
    }

    car = Car(random.Random(0))
    count = 0
    with open(out_path, "wb") as out:
        for tick_ms in range(0, DURATION_MS, TICK_MS):
            car.update(tick_ms / 1000, TICK_MS / 1000)
            for name, period in periods.items():
                if tick_ms % period != 0:
                    continue
                msg = db.get_message_by_name(name)
                signals = car.signals(name)
                if signals is not None:
                    data = msg.encode(signals)
                else:
                    data = bytes(car.rng.getrandbits(8) for _ in range(msg.length))
                write_packet(out, msg.frame_id, data)
                count += 1

    print(f"Wrote {count} packets to {out_path}")


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else "EMXCAN.json",
        sys.argv[2] if len(sys.argv) > 2 else "example.cpf",
    )
