from __future__ import annotations

import threading
import time
from queue import Empty, Queue
from typing import Optional

from src.can_layer.vector_interface import VectorCANReader, PCANUSBReader, NoVectorReader
from src.decoder.dbc_decoder import DBCDecoder
from src.model.vehicle_model import SignalState, SignalConfig
from src.validation.status_engine import validate_signal, get_car_state_manager
from src.persistence.saver import PersistenceWorker


class TelemetryPipeline:
    def __init__(
        self,
        model: VehicleModel,
        dbc_path: str,
        vector_channel: int = 0,
        vector_bitrate: int = 250000,
        vector_app_name: str = "CANalyzer",
        pcan_channel: str = "PCAN_USBBUS1",
        pcan_bitrate: int = 250000,
        interface: str = "vector",
        no_vector: bool = False,
        debug: bool = False,
    ) -> None:
        self.model = model
        self.no_vector = no_vector
        self.interface = interface
        self.debug = debug
        self.raw_queue: Queue = Queue(maxsize=5000)
        self.decoded_queue: Queue = Queue(maxsize=5000)
        self.save_queue: Queue = Queue(maxsize=20)
        self.stop_event = threading.Event()
        self._message_counts = {}  # For debug tracking

        self.decoder = DBCDecoder(dbc_path)
        self.reader = self._build_reader(
            vector_channel, vector_bitrate, vector_app_name,
            pcan_channel, pcan_bitrate
        )
        self.decode_thread = threading.Thread(target=self._decode_loop, daemon=True)
        self.model_thread = threading.Thread(target=self._model_loop, daemon=True)
        self.timeout_thread = threading.Thread(target=self._timeout_loop, daemon=True)
        self.persistence_thread = PersistenceWorker(model=self.model, save_queue=self.save_queue, stop_event=self.stop_event)

    def _build_reader(self, vector_channel: int, vector_bitrate: int, vector_app_name: str, 
                      pcan_channel: str, pcan_bitrate: int):
        if self.no_vector:
            # Create a dummy reader that doesn't try to connect to hardware
            return NoVectorReader(output_queue=self.raw_queue, stop_event=self.stop_event)
        
        if self.interface == "pcan":
            return PCANUSBReader(
                output_queue=self.raw_queue,
                stop_event=self.stop_event,
                channel=pcan_channel,
                bitrate=pcan_bitrate,
            )
        else:  # Default to vector
            return VectorCANReader(
                output_queue=self.raw_queue,
                stop_event=self.stop_event,
                channel=vector_channel,
                bitrate=vector_bitrate,
                app_name=vector_app_name,
            )

    def start(self) -> None:
        self.reader.start()
        self.decode_thread.start()
        self.model_thread.start()
        self.timeout_thread.start()
        self.persistence_thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def request_save(self, fmt: str) -> None:
        try:
            self.save_queue.put_nowait({"format": fmt})
        except Exception:
            pass

    def _decode_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.raw_queue.get(timeout=0.05)
            except Empty:
                continue

            frame = item
            decoded = self.decoder.decode(frame.arbitration_id, frame.data)
            ts = frame.timestamp if getattr(frame, "timestamp", None) else time.time()
            
            if self.debug and decoded:
                msg_id = f"0x{frame.arbitration_id:03X}"
                if msg_id not in self._message_counts:
                    self._message_counts[msg_id] = 0
                self._message_counts[msg_id] += 1
                if self._message_counts[msg_id] % 100 == 1:  # Log every 100th message
                    sig_preview = ", ".join([f"{s[1]}={s[2]:.2f}" for s in decoded[:3]])
                    print(f"[DECODE] {msg_id}: {sig_preview} (msg #{self._message_counts[msg_id]})")
            
            for pcb_name, sig_name, value, unit, description in decoded:
                try:
                    self.decoded_queue.put_nowait((pcb_name, sig_name, value, unit, description, ts))
                except Exception:
                    pass

    def _model_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                item = self.decoded_queue.get(timeout=0.05)
            except Empty:
                continue

            pcb_name, sig_name, value, unit, description, ts = self._normalize_item(item)
            
            cfg = self._config_for(pcb_name, sig_name)
            sig = self.model.update_signal(
                pcb_name=pcb_name,
                signal_name=sig_name,
                value=value,
                timestamp=ts,
                unit=unit,
                description=description,
                config=cfg,
            )
            sig.status = validate_signal(sig, now=ts)
            self.model.recompute_global_state()

    def _timeout_loop(self) -> None:
        while not self.stop_event.is_set():
            now = time.time()
            self.model.check_timeouts(now=now)
            
            # Actualitzar estat del cotxe
            car_state_manager = get_car_state_manager()
            car_state_manager.update_state(self.model)
            
            self.model.recompute_global_state()
            time.sleep(1.0)  # Canviat a 1000ms (1s) per comprovació de timeouts

    @staticmethod
    def _normalize_item(item: tuple) -> tuple[str, str, float, str, str, float]:
        if len(item) == 6:
            return item
        if len(item) == 5:
            pcb, sig, val, unit, desc = item
            return pcb, sig, float(val), unit, desc, time.time()
        if len(item) == 4:
            pcb, sig, val, ts = item
            return pcb, sig, float(val), "", "", float(ts)
        if len(item) == 3:
            pcb, sig, val = item
            return pcb, sig, float(val), "", "", time.time()
        raise ValueError("Unexpected decoded item format")

    @staticmethod
    def _config_for(pcb: str, sig: str) -> SignalConfig:
        key = f"{pcb}.{sig}"
        presets = {
            # FrontECU_M1 signals
            "FrontECU.FpDIGRpot": SignalConfig(min_valid=0.0, max_valid=100.0, timeout_s=0.5),
            "FrontECU.FpDIGLpot": SignalConfig(min_valid=0.0, max_valid=100.0, timeout_s=0.5),
            "FrontECU.FpDIGRvel": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            "FrontECU.FpDIGLvel": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            "FrontECU.FpANLbrake": SignalConfig(min_valid=0.0, max_valid=70.0, timeout_s=0.5),
            
            # FrontECU_M2 signals
            "FrontECU.FpINTtsoff": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpINTsbms": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpINTr2d": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpINTmenu": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpDIGmicrosd": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpSDCinertia": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpSDCbots": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpSDCcsdb": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpERRapps": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpDIGrefri": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpDIGr2d": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "FrontECU.FpDIGvel": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            "FrontECU.FpSHU": SignalConfig(min_valid=0.0, max_valid=5000.0, timeout_s=0.5),
            
            # RearECU_M1 signals
            "RearECU.RpSHU": SignalConfig(min_valid=0.0, max_valid=5000.0, timeout_s=0.5),
            "RearECU.RpSDChvd": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "RearECU.RpSDCtsms": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "RearECU.RpSDClsdb": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "RearECU.RpSDCrsdb": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "RearECU.RpSTAbrkledR": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "RearECU.RpSTAbrkledG": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "RearECU.RpSTAbrkledB": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "RearECU.RpSIGlvs": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            
            # RearECU_M2 signals
            "RearECU.IpV": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            "RearECU.IpRPM": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            "RearECU.IpPar": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            "RearECU.IpI": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            
            # RearECU_M3 signals
            "RearECU.IpT_Mot": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            "RearECU.IpT_IGBT": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            "RearECU.IpErrL2": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            "RearECU.IpErrL1": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            "RearECU.IpErrH2": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            "RearECU.IpErrH1": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            
            # Inverter signals
            "Inverter.iWarn": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            "Inverter.iVout": SignalConfig(min_valid=0.0, max_valid=4000.0, timeout_s=0.5),
            "Inverter.iTmot": SignalConfig(min_valid=0.0, max_valid=32767.0, timeout_s=0.5),
            "Inverter.iTinv": SignalConfig(min_valid=0.0, max_valid=32767.0, timeout_s=0.5),
            "Inverter.iRPM": SignalConfig(min_valid=0.0, max_valid=32767.0, timeout_s=0.5),
            "Inverter.iPar": SignalConfig(min_valid=-32768.0, max_valid=32767.0, timeout_s=0.5),
            "Inverter.iIout": SignalConfig(min_valid=0.0, max_valid=2000.0, timeout_s=0.5),
            "Inverter.iErr": SignalConfig(min_valid=0.0, max_valid=65535.0, timeout_s=0.5),
            "Inverter.RegID": SignalConfig(min_valid=0.0, max_valid=255.0, timeout_s=0.5),
            
            # HVDB signals
            "HVDB.BpTHRbrake": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.BpTHRcurrent": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.BpERRplaus": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.BpERRtimer": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.BpSDC": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.DpSDC": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.DpTHRhv": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.DpLCHdischarge": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.DpSDCintlck1": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.DpSDCintlck2": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVDB.BpSHU": SignalConfig(min_valid=0.0, max_valid=5000.0, timeout_s=0.5),
            "HVDB.DpSHU": SignalConfig(min_valid=0.0, max_valid=5000.0, timeout_s=0.5),
            
            # HVAB signals
            "HVAB.ApTHRhv": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "HVAB.ApSHU": SignalConfig(min_valid=0.0, max_valid=5000.0, timeout_s=0.5),
            
            # TSAL signals
            "TSAL.TpDIGspre": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpDIGsairp": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpDIGsairn": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpDIGipre": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpDIGiairp": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpDIGiairn": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpTHRhv": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpERRscs": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpTHRdis": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpLCH": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "TSAL.TpINTled": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            
            # SDC signals
            "SDC.SpERRbms": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "SDC.SpERRimd": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "SDC.SpLCHebms": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "SDC.SpLCHeimd": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "SDC.SpINTresbut": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "SDC.SpSDCbms": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "SDC.SpSDCimd": SignalConfig(min_valid=0.0, max_valid=1.0, timeout_s=0.5),
            "SDC.SpSHU": SignalConfig(min_valid=0.0, max_valid=5000.0, timeout_s=0.5),
        }
        return presets.get(key, SignalConfig(timeout_s=0.8))
