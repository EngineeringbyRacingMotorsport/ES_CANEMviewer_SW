#!/usr/bin/env python3
"""
Multiplex Analysis - Understand multiplexed messages in DBC.
"""
import cantools

print("\n" + "="*100)
print("MULTIPLEX MESSAGE ANALYSIS")
print("="*100 + "\n")

db = cantools.database.load_file("dbc/EM06CAN.dbc")

for msg in db.messages:
    has_multiplex = any(sig.is_multiplexer or sig.multiplexer_ids for sig in msg.signals)
    
    if has_multiplex:
        print(f"\n📦 Message 0x{msg.frame_id:03X} - {msg.name}")
        print(f"   DLC: {msg.length} bytes")
        print(f"   Multiplexed: YES")
        
        # Find multiplexer
        multiplexer = next((s for s in msg.signals if s.is_multiplexer), None)
        if multiplexer:
            print(f"   Multiplexer signal: {multiplexer.name}")
        
        # Group signals by multiplexer value
        mux_groups = {}
        for sig in msg.signals:
            if sig.is_multiplexer:
                print(f"   └─ [MULTIPLEXER] {sig.name}")
            elif sig.multiplexer_ids:
                for mux_id in sig.multiplexer_ids:
                    if mux_id not in mux_groups:
                        mux_groups[mux_id] = []
                    mux_groups[mux_id].append(sig.name)
            else:
                print(f"   └─ [ALWAYS] {sig.name} (not multiplexed)")
        
        for mux_val in sorted(mux_groups.keys()):
            sigs = mux_groups[mux_val]
            print(f"   └─ When {multiplexer.name if multiplexer else '?'}={mux_val}:")
            for sig in sigs:
                print(f"      • {sig}")

print("\n" + "="*100)
print("⚠️  SUMMARY:")
print("="*100)
print("""
Multiplexed messages only decode if the multiplexer value matches the data.

For example, InverterTX (0x103) has:
  - RegID (multiplexer) = 0x00-0xFF
  - When RegID=143: decode iWarn
  - When RegID=138: decode iVout
  - etc.

If the bus is sending different RegID values, you might only see some of them.

SOLUTION: The decoder should handle ALL multiplexer values, not just some.
""")
print()
