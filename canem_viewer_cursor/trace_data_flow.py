#!/usr/bin/env python3
"""
Complete data flow diagnostic tool.
Traces data from PCAN hardware → raw queue → decoder → model → UI
Identifies where data is lost in the pipeline.
"""
import sys
import time
import threading
import cantools
from queue import Queue, Empty
from src.can_layer.vector_interface import (
    auto_detect_interface,
    PCANUSBReader,
)
from src.decoder.dbc_decoder import DBCDecoder
from src.model.vehicle_model import VehicleModel
from src.services.pipeline import TelemetryPipeline

class DataFlowTracer:
    """Traces and logs data through each pipeline stage."""
    
    def __init__(self, duration: int = 15):
        self.duration = duration
        self.start_time = time.time()
        
        # Metrics per stage
        self.raw_count = 0  # Messages received by PCAN reader
        self.decoded_count = 0  # Messages decoded by DBCDecoder
        self.model_count = 0  # Signals updated in VehicleModel
        self.raw_by_id = {}  # {frame_id: count}
        self.decoded_by_msg = {}  # {message_name: count}
        self.model_by_pcb = {}  # {pcb_name: signal_count}
        self.lock = threading.Lock()
    
    def trace_raw(self, frame_id: int) -> None:
        """Log raw CAN frame receipt."""
        with self.lock:
            self.raw_count += 1
            if frame_id not in self.raw_by_id:
                self.raw_by_id[frame_id] = 0
            self.raw_by_id[frame_id] += 1
    
    def trace_decoded(self, msg_name: str) -> None:
        """Log decoded message."""
        with self.lock:
            self.decoded_count += 1
            if msg_name not in self.decoded_by_msg:
                self.decoded_by_msg[msg_name] = 0
            self.decoded_by_msg[msg_name] += 1
    
    def trace_model_update(self, pcb_name: str) -> None:
        """Log model update."""
        with self.lock:
            self.model_count += 1
            if pcb_name not in self.model_by_pcb:
                self.model_by_pcb[pcb_name] = 0
            self.model_by_pcb[pcb_name] += 1
    
    def report(self) -> None:
        """Print comprehensive trace report."""
        elapsed = time.time() - self.start_time
        print(f"\n{'='*100}")
        print(f"DATA FLOW TRACE REPORT ({elapsed:.1f}s)")
        print(f"{'='*100}\n")
        
        with self.lock:
            print(f"📥 RAW CAN RECEPTION (PCAN Hardware)")
            print(f"   Total frames received: {self.raw_count}")
            print(f"   Frame rate: {self.raw_count/elapsed:.1f} frames/sec")
            if self.raw_count > 0:
                print(f"   Unique IDs: {len(self.raw_by_id)}")
                print(f"   {'ID':<8} {'Count':<10} {'%':<8}")
                print(f"   {'-'*26}")
                for frame_id in sorted(self.raw_by_id.keys()):
                    count = self.raw_by_id[frame_id]
                    pct = (count / self.raw_count) * 100
                    print(f"   0x{frame_id:03X}   {count:<10} {pct:>6.1f}%")
            else:
                print(f"   ⚠️  NO DATA RECEIVED! Check PCAN connection.")
            
            print(f"\n📤 DECODED MESSAGES (DBCDecoder)")
            print(f"   Total messages decoded: {self.decoded_count}")
            if self.raw_count > 0 and self.decoded_count > 0:
                efficiency = (self.decoded_count / self.raw_count) * 100
                print(f"   Decoding efficiency: {efficiency:.1f}%")
            elif self.raw_count > 0:
                print(f"   ⚠️  DECODING FAILED! {self.raw_count} frames received but 0 decoded.")
            
            if self.decoded_count > 0:
                print(f"   Unique messages: {len(self.decoded_by_msg)}")
                print(f"   {'Message Name':<20} {'Count':<10} {'%':<8}")
                print(f"   {'-'*38}")
                for msg_name in sorted(self.decoded_by_msg.keys()):
                    count = self.decoded_by_msg[msg_name]
                    pct = (count / self.decoded_count) * 100
                    print(f"   {msg_name:<20} {count:<10} {pct:>6.1f}%")
            
            print(f"\n🎯 MODEL UPDATES (VehicleModel)")
            print(f"   Total signals updated: {self.model_count}")
            if self.decoded_count > 0 and self.model_count > 0:
                efficiency = (self.model_count / self.decoded_count) * 100
                print(f"   Model update efficiency: {efficiency:.1f}%")
            elif self.decoded_count > 0:
                print(f"   ⚠️  NO MODEL UPDATES! {self.decoded_count} messages decoded but 0 signals updated.")
            
            if self.model_count > 0:
                print(f"   PCBs updated: {len(self.model_by_pcb)}")
                print(f"   {'PCB Name':<15} {'Signal Count':<15} {'%':<8}")
                print(f"   {'-'*38}")
                for pcb_name in sorted(self.model_by_pcb.keys()):
                    count = self.model_by_pcb[pcb_name]
                    pct = (count / self.model_count) * 100
                    print(f"   {pcb_name:<15} {count:<15} {pct:>6.1f}%")
            
            # Analysis
            print(f"\n📊 FLOW ANALYSIS:")
            print(f"   Raw → Decoded: {self.raw_count} → {self.decoded_count}", end="")
            if self.raw_count > 0 and self.decoded_count == 0:
                print(f" ❌ CRITICAL: No decoding happening!")
            elif self.raw_count > self.decoded_count > 0:
                loss = self.raw_count - self.decoded_count
                print(f" ⚠️  Loss: {loss} frames ({(loss/self.raw_count)*100:.1f}%)")
            else:
                print(f" ✓ OK")
            
            print(f"   Decoded → Model: {self.decoded_count} → {self.model_count}", end="")
            if self.decoded_count > 0 and self.model_count == 0:
                print(f" ❌ CRITICAL: No model updates!")
            elif self.decoded_count > self.model_count > 0:
                loss = self.decoded_count - self.model_count
                print(f" ⚠️  Loss: {loss} signals ({(loss/self.decoded_count)*100:.1f}%)")
            else:
                print(f" ✓ OK")
        
        print(f"\n{'='*100}\n")


def test_data_flow(duration: int = 15):
    """Test complete data flow with instrumentation."""
    print(f"\n🔍 DATA FLOW TRACE - {duration}s test")
    print(f"{'='*100}\n")
    
    # Initialize
    tracer = DataFlowTracer(duration)
    
    # Detect interface
    print("Step 1️⃣  Detecting PCAN interface...")
    interface_name, config = auto_detect_interface()
    if interface_name != "pcan":
        print(f"⚠️  Warning: Expected PCAN but got {interface_name}")
    print(f"   Using {interface_name}: {config}\n")
    
    # Load DBC
    print("Step 2️⃣  Loading DBC file...")
    try:
        db = cantools.database.load_file("dbc/EM06CAN.dbc")
        print(f"   ✓ Loaded {len(db.messages)} messages from DBC\n")
    except Exception as e:
        print(f"   ❌ Failed to load DBC: {e}\n")
        return
    
    # Create decoder
    print("Step 3️⃣  Creating DBCDecoder...")
    decoder = DBCDecoder("dbc/EM06CAN.dbc")
    if not decoder.available:
        print(f"   ❌ Decoder not available\n")
        return
    print(f"   ✓ Decoder ready\n")
    
    # Create model
    print("Step 4️⃣  Creating VehicleModel...")
    model = VehicleModel(dbc_path="dbc/EM06CAN.dbc")
    print(f"   ✓ Model initialized with {len(model.vehicle.pcbs)} PCBs\n")
    
    # Test raw reception
    print("Step 5️⃣  Testing raw CAN reception (PCAN reader)...")
    print(f"   Starting PCAN reader for 5 seconds...\n")
    
    raw_queue = Queue(maxsize=5000)
    stop_event = threading.Event()
    reader = PCANUSBReader(
        output_queue=raw_queue,
        stop_event=stop_event,
        channel=config.get("channel", "PCAN_USBBUS1"),
        bitrate=config.get("bitrate", 250000),
    )
    reader.start()
    
    test_start = time.time()
    while time.time() - test_start < 5:
        try:
            frame = raw_queue.get(timeout=0.1)
            tracer.trace_raw(frame.arbitration_id)
        except Empty:
            pass
    
    stop_event.set()
    reader.join(timeout=2)
    
    print(f"   ✓ Raw reception test complete\n")
    
    if tracer.raw_count == 0:
        print(f"   ⚠️  NO CAN MESSAGES RECEIVED!")
        print(f"   Check: 1) PCAN hardware connected")
        print(f"          2) Correct bitrate (250000 bps)")
        print(f"          3) Bus traffic on PCAN")
        tracer.report()
        return
    
    # Test decoding
    print("Step 6️⃣  Testing DBC decoding...")
    print(f"   Processing first 100 raw frames...\n")
    
    raw_queue = Queue(maxsize=5000)
    stop_event = threading.Event()
    reader = PCANUSBReader(
        output_queue=raw_queue,
        stop_event=stop_event,
        channel=config.get("channel", "PCAN_USBBUS1"),
        bitrate=config.get("bitrate", 250000),
    )
    reader.start()
    
    decode_start = time.time()
    frames_processed = 0
    while frames_processed < 100 and time.time() - decode_start < 5:
        try:
            frame = raw_queue.get(timeout=0.1)
            decoded = decoder.decode(frame.arbitration_id, frame.data)
            if decoded:
                msg_def = db.get_message_by_frame_id(frame.arbitration_id)
                tracer.trace_decoded(msg_def.name)
                for pcb_name, sig_name, value, unit, desc in decoded:
                    tracer.trace_model_update(pcb_name)
            frames_processed += 1
        except Empty:
            pass
    
    stop_event.set()
    reader.join(timeout=2)
    
    print(f"   ✓ Decoding test complete\n")
    
    if tracer.decoded_count == 0:
        print(f"   ❌ CRITICAL: No messages decoded!")
        print(f"   Check: 1) DBC file has correct message IDs")
        print(f"          2) CAN messages match DBC structure")
        print(f"          3) Message frame IDs are recognized")
        tracer.report()
        return
    
    # Test full pipeline
    print("Step 7️⃣  Testing full pipeline integration...")
    print(f"   Running complete pipeline for {duration}s...\n")
    
    pipeline = TelemetryPipeline(
        model=model,
        dbc_path="dbc/EM06CAN.dbc",
        pcan_channel=config.get("channel", "PCAN_USBBUS1"),
        pcan_bitrate=config.get("bitrate", 250000),
        interface="pcan",
        no_vector=False,
        debug=False,
    )
    
    # Instrument pipeline
    original_trace_raw = pipeline.reader.run
    received_frames = []
    
    def instrumented_reader():
        """Wrapper to count frames."""
        while not pipeline.stop_event.is_set():
            try:
                frame = pipeline.raw_queue.get(timeout=0.01)
                if frame:
                    tracer.trace_raw(frame.arbitration_id)
            except:
                pass
    
    # Override decode loop to trace
    original_decode = pipeline._decode_loop
    def instrumented_decode():
        while not pipeline.stop_event.is_set():
            try:
                frame = pipeline.raw_queue.get(timeout=0.05)
                decoded = pipeline.decoder.decode(frame.arbitration_id, frame.data)
                if decoded:
                    msg_def = pipeline.decoder.db.get_message_by_frame_id(frame.arbitration_id)
                    tracer.trace_decoded(msg_def.name)
                    ts = getattr(frame, "timestamp", time.time())
                    for pcb_name, sig_name, value, unit, description in decoded:
                        try:
                            pipeline.decoded_queue.put_nowait((pcb_name, sig_name, value, unit, description, ts))
                        except:
                            pass
            except Empty:
                pass
    
    pipeline._decode_loop = instrumented_decode
    
    # Override model loop to trace
    original_model = pipeline._model_loop
    def instrumented_model():
        while not pipeline.stop_event.is_set():
            try:
                item = pipeline.decoded_queue.get(timeout=0.05)
                pcb_name, sig_name, value, unit, description, ts = pipeline._normalize_item(item)
                tracer.trace_model_update(pcb_name)
                cfg = pipeline._config_for(pcb_name, sig_name)
                sig = pipeline.model.update_signal(
                    pcb_name=pcb_name,
                    signal_name=sig_name,
                    value=value,
                    timestamp=ts,
                    unit=unit,
                    description=description,
                    config=cfg,
                )
            except Empty:
                pass
    
    pipeline._model_loop = instrumented_model
    
    # Run pipeline
    pipeline.start()
    time.sleep(duration)
    pipeline.stop()
    pipeline.reader.join(timeout=2)
    pipeline.decode_thread.join(timeout=2)
    pipeline.model_thread.join(timeout=2)
    pipeline.timeout_thread.join(timeout=2)
    
    # Final report
    tracer.report()


if __name__ == "__main__":
    duration = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    test_data_flow(duration)
