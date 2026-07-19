#!/usr/bin/env python3
"""
Diagnostic tool to capture and analyze raw CAN bus traffic and DBC decoding.
Useful for debugging why signals aren't appearing in the UI.
"""
import sys
import time
import cantools
from src.can_layer.vector_interface import (
    detect_vector_available,
    detect_pcan_available,
    auto_detect_interface,
    VectorCANReader,
    PCANUSBReader,
)
from src.decoder.dbc_decoder import DBCDecoder

def capture_raw_traffic(interface_name: str, config: dict, duration: int = 10):
    """Capture raw CAN messages and decode them with DBC."""
    print(f"\n{'='*80}")
    print(f"Capturing CAN traffic for {duration} seconds using {interface_name}")
    print(f"Configuration: {config}")
    print(f"{'='*80}\n")
    
    if interface_name == "vector":
        reader = VectorCANReader(
            channel=config.get("channel", 0),
            bitrate=config.get("bitrate", 250000),
            app_name=config.get("app_name", "CANalyzer"),
        )
    elif interface_name == "pcan":
        reader = PCANUSBReader(
            channel=config.get("channel", "PCAN_USBBUS1"),
            bitrate=config.get("bitrate", 250000),
        )
    else:
        print("ERROR: Unknown interface")
        return
    
    # Load DBC
    try:
        decoder = DBCDecoder("dbc/EM06CAN.dbc")
        if not decoder.available:
            print("ERROR: DBC decoder not available")
            return
        db = decoder.db
    except Exception as e:
        print(f"ERROR loading DBC: {e}")
        return
    
    reader.start()
    start_time = time.time()
    messages_by_id = {}
    messages_by_name = {}
    
    try:
        while time.time() - start_time < duration:
            msg = reader.queue.get(timeout=0.5)
            if msg is None:
                continue
            
            arbitration_id = msg.arbitration_id
            data = msg.data
            
            # Track by ID
            if arbitration_id not in messages_by_id:
                messages_by_id[arbitration_id] = {"count": 0, "msg_name": "?", "sender": "?"}
            messages_by_id[arbitration_id]["count"] += 1
            
            # Try to decode
            try:
                msg_def = db.get_message_by_frame_id(arbitration_id)
                msg_name = msg_def.name
                sender = msg_def.senders[0] if msg_def.senders else "?"
                decoded = db.decode_message(arbitration_id, data)
                
                messages_by_id[arbitration_id]["msg_name"] = msg_name
                messages_by_id[arbitration_id]["sender"] = sender
                
                if msg_name not in messages_by_name:
                    messages_by_name[msg_name] = {"count": 0, "sample": decoded, "sender": sender}
                messages_by_name[msg_name]["count"] += 1
                
                # Print sample
                print(f"[ID: 0x{arbitration_id:03X}] {msg_name:20s} (Sender: {sender:12s}) → {decoded}")
            except Exception as e:
                print(f"[ID: 0x{arbitration_id:03X}] Cannot decode: {e}")
    
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        reader.stop()
        reader.join(timeout=2)
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY - Messages Captured:")
    print(f"{'='*80}")
    print(f"{'ID':<8} {'Message Name':<20} {'Sender':<15} {'Count':<8}")
    print("-" * 51)
    for arb_id in sorted(messages_by_id.keys()):
        info = messages_by_id[arb_id]
        print(f"0x{arb_id:03X}   {info['msg_name']:<20} {info['sender']:<15} {info['count']:<8}")
    
    print(f"\n{'='*80}")
    print("UNIQUE MESSAGES by Name:")
    print(f"{'='*80}")
    print(f"{'Message Name':<20} {'Sender':<15} {'Count':<8}")
    print("-" * 43)
    for msg_name in sorted(messages_by_name.keys()):
        info = messages_by_name[msg_name]
        print(f"{msg_name:<20} {info['sender']:<15} {info['count']:<8}")
    
    print(f"\n{'='*80}")
    print("EXPECTED Messages from DBC:")
    print(f"{'='*80}")
    print(f"{'ID':<8} {'Message Name':<20} {'Sender':<15} {'Signals':<30}")
    print("-" * 73)
    for msg in db.messages:
        sender = msg.senders[0] if msg.senders else "?"
        sig_names = ", ".join([s.name for s in msg.signals[:3]])
        if len(msg.signals) > 3:
            sig_names += f", ... (+{len(msg.signals)-3})"
        print(f"0x{msg.frame_id:03X}   {msg.name:<20} {sender:<15} {sig_names:<30}")
    
    return messages_by_name

if __name__ == "__main__":
    print("\n🔍 CAN Bus Traffic Diagnostic Tool")
    print("=" * 80)
    
    # Auto-detect or use specified interface
    if len(sys.argv) > 1 and sys.argv[1] == "--interface":
        interface_name = sys.argv[2] if len(sys.argv) > 2 else "vector"
        config = {}
        if interface_name == "pcan" and len(sys.argv) > 3:
            config["channel"] = sys.argv[3]
    else:
        # Auto-detect
        print("\n🔎 Auto-detecting CAN interface...")
        interface_name, config = auto_detect_interface()
        print(f"   ✓ Using {interface_name}")
    
    duration = int(sys.argv[-1]) if sys.argv[-1].isdigit() else 10
    capture_raw_traffic(interface_name, config, duration=duration)
