"""
Generates a simulated drive into a packet file, using the messages defined in the
signal metadata file. Each message with a CycleTime is sent at that period.

Run from the project root: python -m tools.gen_example [json_path] [out_path]

Recreates a datalogger log of a 10-minute session (10 ms ticks):
- 0..5 s: Idle, low voltage on
- 5..7 s: precharge, AIR- closed, DC link charging
- 7..10 s: TS active, AIR+ closed
- 10 s: ready-to-drive, button pressed with the brake on
- 11..570 s: laps of about 70 s (straights and corners)
- 570..580 s: slowing to a stop; at 580 s ready-to-drive is left (TS active)
- 590 s: TS off, AIRs open, DC link discharges, back to Idle
"""

import math
import random
import sys
from io import BufferedIOBase
from typing import Any

from src.schema import Schema, _create_database
from src.utils import read_text_file

DURATION_MS = 600_000
# Session timeline, in seconds
PRECHARGE_AT = 5.0
TS_ACTIVE_AT = 7.0
R2D_AT = 10.0
STOP_AT = 570.0
R2D_OFF_AT = 580.0
TS_OFF_AT = 590.0
# Target speed (km/h) along a lap, as (seconds into the lap it lasts until, speed)
LAP_ENDS = ((8, 90), (12, 40), (18, 70), (21, 30), (31, 100), (36, 45), (43, 75), (47, 35), (56, 85), (60, 40), (70, 60))
LAP_S = LAP_ENDS[-1][0]
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


def write_packet(out: BufferedIOBase, frame_id: int, timestamp_ms: int, data: bytes) -> None:
    if len(data) > 8:
        raise ValueError("Invalid packet data length")
    if timestamp_ms > 0xFFFF_FFFF:
        raise ValueError("Invalid packet timestamp")
    write_uleb128(out, frame_id)
    write_uleb128(out, timestamp_ms)
    out.write(bytes([len(data)]))
    out.write(data)


class Car:
    """Physical state of the simulated car at a given time."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.speed = 0.0  # km/h
        self.t_igbt = 32.0
        self.t_mot = 30.0
        self.used_ah = 0.0  # charge drawn from the battery
        self.dc_link = 0.0  # inverter side voltage, V
        self.inverter_register = 0

    def noise(self, amplitude: float) -> float:
        return self.rng.uniform(-amplitude, amplitude)

    def update(self, t: float, dt: float) -> None:
        self.t = t
        # Phase as the FrontECU would report it (Phase.I/P/T/R = 0..3)
        if t < PRECHARGE_AT or t >= TS_OFF_AT:
            self.phase = 0
        elif t < TS_ACTIVE_AT:
            self.phase = 1
        elif R2D_AT <= t < R2D_OFF_AT:
            self.phase = 3
        else:
            self.phase = 2
        self.precharging = self.phase == 1
        self.air_neg = self.phase >= 1
        self.hv = self.phase >= 2  # AIR+ closed
        self.r2d = self.phase == 3
        # Momentary buttons, held for half a second
        self.r2d_button = any(at <= t < at + 0.5 for at in (R2D_AT, R2D_OFF_AT))
        self.ts_off_button = TS_OFF_AT <= t < TS_OFF_AT + 0.5

        self.throttle, self.brake = self.driver(t)

        # Acceleration in m/s², converted to km/h
        drag = 0.2 + 0.0004 * self.speed**2
        self.speed += (self.throttle * 0.025 - self.brake * 0.2 - drag) * dt * 3.6
        self.speed = max(0.0, self.speed)

        self.current = max(0.0, self.throttle * 2.2 + self.noise(2.0)) if self.r2d else 0.0
        self.used_ah += self.current * dt / 3600
        # Pack voltage sags with the load and drops as the battery discharges
        self.pack = 400.0 - self.used_ah * 0.8 - self.current * 0.15
        if self.precharging:
            self.dc_link += (self.pack - self.dc_link) * dt / 0.4
        elif self.hv:
            self.dc_link = self.pack
        else:
            # Discharge circuit once the AIRs open
            self.dc_link -= self.dc_link * dt / 0.5
        self.t_igbt += (self.current * 0.01 - (self.t_igbt - 32.0) * 0.02) * dt
        self.t_mot += (self.current * 0.006 - (self.t_mot - 30.0) * 0.01) * dt

    def driver(self, t: float) -> tuple[float, float]:
        """Throttle (%) and brake pressure following the lap's target speed"""
        # Holding the brake while pressing the R2D button, to enter and to leave it
        if any(at <= t < at + 1.0 for at in (R2D_AT, R2D_OFF_AT)):
            return 0.0, 30.0
        if not self.r2d:
            return 0.0, 0.0
        if t >= STOP_AT:
            # Brake to a standstill and keep the brake on
            return 0.0, min(40.0, 10.0 + self.speed * 0.5)
        else:
            into_lap = (t - R2D_AT - 1.0) % LAP_S
            target = next(speed for end, speed in LAP_ENDS if into_lap < end)
        error = target - self.speed
        if error > 2.0:
            throttle, brake = 20.0 + error * 4.0 + self.noise(1.0), 0.0
        elif error < -4.0:
            throttle, brake = 0.0, -error * 0.8 + self.noise(0.5)
        else:
            throttle, brake = 8.0 + self.speed * 0.15 + self.noise(1.0), 0.0  # holding speed
        return min(100.0, max(0.0, throttle)), min(40.0, max(0.0, brake))

    def signals(self, name: str) -> dict[str, Any] | None:
        speed = round(self.speed)
        rpm = round(self.speed / 3.6 / (2 * math.pi * 0.23) * 60 * 4.4)
        b = int  # booleans encoded as 0/1
        voltage = round(self.dc_link)
        count = round(self.t * 10) % 256  # measurement counters

        match name:
            case "FrontECU_M1":
                return {
                    "FpDIGRpot": min(100.0, max(0.0, self.throttle + self.noise(0.5))),
                    "FpDIGLpot": min(100.0, max(0.0, self.throttle + self.noise(0.5))),
                    # Wheel speed sensors read a clean 0 at standstill
                    "FpDIGRvel": max(0, speed + self.rng.randint(-1, 1)) if speed else 0,
                    "FpDIGLvel": max(0, speed + self.rng.randint(-1, 1)) if speed else 0,
                    "FpANLbrake": max(0.0, self.brake + self.noise(0.3)),
                }
            case "FrontECU_M2":
                return {
                    "FpINTtsoff": b(self.ts_off_button),
                    "FpINTsbms": 0,
                    "FpINTr2d": b(self.r2d_button),
                    "FpINTmenu": 0,
                    "FpDIGmicrosd": 1,
                    "FpSTAphase": self.phase,
                    "FpSDCinertia": 1,
                    "FpSDCbots": 1,
                    "FpSDCcsdb": 1,
                    "FpERRapps": 0,
                    "FpDIGrefri": b(self.hv),
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
                    "RpSTAbrkledR": b(self.brake > 2.0),
                    "RpSTAbrkledG": 0,
                    "RpSTAbrkledB": 0,
                    "RpSIGlvs": round(24_800 - self.t * 0.8) + self.rng.randint(-150, 150),
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
                    "ApTHRhv": b(self.dc_link > 60.0),
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
                    "DpTHRhv": b(self.dc_link > 60.0),
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
                    "TpDIGsairn": b(self.air_neg),
                    "TpDIGipre": b(self.precharging),
                    "TpDIGiairp": b(self.hv),
                    "TpDIGiairn": b(self.air_neg),
                    "TpTHRhv": b(self.dc_link > 60.0),
                    "TpERRscs": 0,
                    "TpTHRdis": 0,
                    "TpLCH": 0,
                    "TpINTled": b(self.dc_link > 60.0),
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
    schema = Schema.model_validate_json(read_text_file(json_path))
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
                write_packet(out, msg.frame_id, tick_ms, data)
                count += 1

    print(f"Wrote {count} packets to {out_path}")


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else "EMXCAN.json",
        sys.argv[2] if len(sys.argv) > 2 else "example.cpf",
    )
