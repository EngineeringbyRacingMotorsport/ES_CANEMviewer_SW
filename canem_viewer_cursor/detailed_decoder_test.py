#!/usr/bin/env python3
"""
Detailed Decoder Test - Test decode() on each message ID from bus.
"""
import sys
import time
import threading
import cantools
from queue import Queue, Empty
from src.can_layer.vector_interface import auto_detect_interface, PCANUSBReader
from src.decoder.dbc_decoder import DBCDecoder

print("\n" + "="*100)
print("DETAILED DECODER TEST")
print("="*100 + "\n")

# Load DBC
db = cantools.database.load_file("dbc/EM06CAN.dbc")
decoder = DBCDecoder("dbc/EM06CAN.dbc")

print(f"DBC loaded: {len(db.messages)} messages\n")

# Detect interface
interface_name, config = auto_detect_interface()
print(f"Listening on {interface_name} for 20 seconds...\n")

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

# Track decode results
frames_by_id = {}
decode_results = {}
start = time.time()

while time.time() - start < 20:
    try:
        frame = raw_queue.get(timeout=0.1)
        msg_id = frame.arbitration_id
        
        # Track frame reception
        if msg_id not in frames_by_id:
            frames_by_id[msg_id] = {"count": 0, "samples": []}
        frames_by_id[msg_id]["count"] += 1
        if len(frames_by_id[msg_id]["samples"]) < 1:
            frames_by_id[msg_id]["samples"].append((frame.data, None))
        
        # Test decode
        try:
            decoded = decoder.decode(msg_id, frame.data)
            
            if msg_id not in decode_results:
                decode_results[msg_id] = {"success": 0, "fail": 0, "empty": 0, "error": None}
            
            if decoded:
                decode_results[msg_id]["success"] += 1
                if len(frames_by_id[msg_id]["samples"]) == 1:
                    frames_by_id[msg_id]["samples"][0] = (frame.data, decoded)
            else:
                decode_results[msg_id]["empty"] += 1
        except Exception as e:
            if msg_id not in decode_results:
                decode_results[msg_id] = {"success": 0, "fail": 0, "empty": 0, "error": str(e)}
            decode_results[msg_id]["fail"] += 1
            decode_results[msg_id]["error"] = str(e)
    
    except Empty:
        pass

stop_event.set()
reader.join(timeout=2)

print("\n" + "="*100)
print("DECODE TEST RESULTS")
print("="*100 + "\n")

print(f"{'ID':<8} {'Hex':<8} {'Rcvd':<8} {'Decoded':<10} {'Failed':<8} {'Empty':<8} {'Success %':<12} {'Status':<40}")
print("-" * 100)

for msg_id in sorted(decode_results.keys()):
    results = decode_results[msg_id]
    rcvd = frames_by_id.get(msg_id, {}).get("count", 0)
    total = results["success"] + results["fail"] + results["empty"]
    success_pct = (results["success"] / total * 100) if total > 0 else 0
    
    status = ""
    if results["fail"] > 0:
        status = f"❌ ERROR: {results['error'][:30]}"
    elif results["empty"] > 0:
        status = f"⚠️  Returns empty list"
    elif results["success"] == 0:
        status = "⚠️  No successful decodes"
    else:
        status = "✓ OK"
    
    print(f"{msg_id:<8} 0x{msg_id:03X}    {rcvd:<8} {results['success']:<10} {results['fail']:<8} {results['empty']:<8} {success_pct:>6.1f}%      {status:<40}")

print("\n" + "="*100)
print("SAMPLE DATA & DECODE RESULTS")
print("="*100 + "\n")

for msg_id in sorted(frames_by_id.keys()):
    samples = frames_by_id[msg_id]["samples"]
    if samples and samples[0][1] is not None:
        data, decoded = samples[0]
        print(f"\n0x{msg_id:03X} - Decoded successfully:")
        print(f"  Raw data: {data.hex()}")
        for pcb, sig, val, unit, desc in decoded:
            print(f"  → {pcb}.{sig} = {val} {unit}")
    elif samples:
        data, _ = samples[0]
        print(f"\n0x{msg_id:03X} - ❌ FAILED to decode:")
        print(f"  Raw data: {data.hex()}")
        if msg_id in decode_results and decode_results[msg_id]["error"]:
            print(f"  Error: {decode_results[msg_id]['error']}")

print("\n")
