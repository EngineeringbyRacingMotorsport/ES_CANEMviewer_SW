#!/usr/bin/env python3
"""
Capture real CAN frames and test decode on them directly.
"""
import sys
import time
import threading
import cantools
from queue import Queue, Empty
from src.can_layer.vector_interface import auto_detect_interface, PCANUSBReader

print("\n" + "="*100)
print("RAW FRAME CAPTURE & MANUAL DECODE TEST")
print("="*100 + "\n")

# Load DBC
db = cantools.database.load_file("dbc/EM06CAN.dbc")
print(f"DBC loaded: {len(db.messages)} messages\n")

# Detect interface
interface_name, config = auto_detect_interface()
print(f"Listening on {interface_name} for 10 seconds...\n")

# Capture frames
raw_queue = Queue()
stop_event = threading.Event()

reader = PCANUSBReader(
    output_queue=raw_queue,
    stop_event=stop_event,
    channel=config.get("channel", "PCAN_USBBUS1"),
    bitrate=config.get("bitrate", 250000),
)

reader.start()

# Store first few samples of each ID
samples = {}
start = time.time()

while time.time() - start < 10:
    try:
        frame = raw_queue.get(timeout=0.1)
        msg_id = frame.arbitration_id
        
        if msg_id not in samples:
            samples[msg_id] = []
        
        if len(samples[msg_id]) < 2:  # Store 2 samples of each ID
            samples[msg_id].append({
                'data': frame.data,
                'dlc': len(frame.data),
                'raw_hex': frame.data.hex()
            })
    except Empty:
        pass

stop_event.set()
reader.join(timeout=2)

print("\n" + "="*100)
print("CAPTURED SAMPLES")
print("="*100 + "\n")

# Test decode on samples
for msg_id in sorted(samples.keys()):
    print(f"\n{'='*100}")
    print(f"Message ID 0x{msg_id:03X}")
    print(f"{'='*100}")
    
    # Check if in DBC
    try:
        msg_def = db.get_message_by_frame_id(msg_id)
        print(f"✓ Found in DBC: {msg_def.name} (DLC: {msg_def.length} bytes, {len(msg_def.signals)} signals)")
    except:
        print(f"❌ NOT in DBC")
        for i, sample in enumerate(samples[msg_id]):
            print(f"\n  Sample {i+1}: {sample['raw_hex']} (DLC: {sample['dlc']} bytes)")
        continue
    
    # Test decode on each sample
    for i, sample in enumerate(samples[msg_id]):
        print(f"\n  Sample {i+1}: {sample['raw_hex']} (DLC: {sample['dlc']} bytes)")
        
        try:
            decoded = db.decode_message(msg_id, sample['data'])
            if decoded:
                print(f"    ✓ Decoded successfully:")
                for sig_name, value in decoded.items():
                    print(f"      - {sig_name} = {value}")
            else:
                print(f"    ⚠️  Decoded but result is empty dict")
        except Exception as e:
            print(f"    ❌ Decode failed: {e}")
        
        # Also try just getting message definition
        try:
            signals_in_msg = len(msg_def.signals)
            multiplexer = next((s for s in msg_def.signals if s.is_multiplexer), None)
            if multiplexer:
                # For multiplexed messages, show multiplexer value
                try:
                    mux_val_dict = db.decode_message(msg_id, sample['data'], decode_choices=False, allow_truncated=True)
                    if multiplexer.name in mux_val_dict:
                        mux_val = mux_val_dict[multiplexer.name]
                        print(f"    Note: Multiplexer {multiplexer.name} = {mux_val}")
                except:
                    pass
        except:
            pass

print("\n" + "="*100)
print("ANALYSIS COMPLETE")
print("="*100 + "\n")
