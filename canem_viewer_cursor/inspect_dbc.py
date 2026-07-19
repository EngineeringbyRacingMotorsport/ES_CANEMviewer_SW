#!/usr/bin/env python3
"""
Quick DBC Inspector - See what message IDs are in the DBC file.
"""
import cantools

print("\n" + "="*100)
print("DBC MESSAGE INVENTORY")
print("="*100 + "\n")

try:
    db = cantools.database.load_file("dbc/EM06CAN.dbc")
    print(f"DBC loaded: {len(db.messages)} messages\n")
    
    print(f"{'ID':<8} {'Hex ID':<10} {'Message Name':<25} {'Signals':<10} {'Sender':<15}")
    print("-" * 68)
    
    for msg in sorted(db.messages, key=lambda m: m.frame_id):
        sender = msg.senders[0] if msg.senders else "?"
        print(f"{msg.frame_id:<8} 0x{msg.frame_id:03X}    {msg.name:<25} {len(msg.signals):<10} {sender:<15}")
    
    print("\n" + "="*100)
    print("RECEIVED FROM BUS (from trace_data_flow.py output):")
    print("="*100 + "\n")
    
    bus_ids = [0x000, 0x004, 0x100, 0x101, 0x102, 0x103, 0x200, 0x201, 0x202, 0x400]
    dbc_ids = {msg.frame_id for msg in db.messages}
    
    print(f"{'ID':<8} {'Hex ID':<10} {'In DBC?':<15} {'Status':<40}")
    print("-" * 68)
    
    missing = []
    for bus_id in bus_ids:
        in_dbc = bus_id in dbc_ids
        if in_dbc:
            msg = db.get_message_by_frame_id(bus_id)
            status = f"✓ Found: {msg.name}"
        else:
            status = "❌ NOT IN DBC"
            missing.append(bus_id)
        
        print(f"{bus_id:<8} 0x{bus_id:03X}    {str(in_dbc):<15} {status:<40}")
    
    if missing:
        print(f"\n⚠️  MISSING {len(missing)} MESSAGE IDs IN DBC:")
        for msg_id in missing:
            print(f"   - 0x{msg_id:03X} ({msg_id})")
        
        print(f"\nThese {len(missing)} message IDs are on the CAN bus but NOT defined in DBC.")
        print(f"That's why decoder skips them: {(len(missing)/len(bus_ids))*100:.1f}% of received frames are ignored!")
    
except Exception as e:
    print(f"Error: {e}")

print("\n")
