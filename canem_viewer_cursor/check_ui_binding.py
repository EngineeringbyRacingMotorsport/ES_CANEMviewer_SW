#!/usr/bin/env python3
"""
UI Data Flow Analysis - Check if UI properly reads from VehicleModel.
"""
import sys
import time
from src.model.vehicle_model import VehicleModel

def check_ui_data_binding():
    """Check if UI can access data from VehicleModel."""
    print("\n" + "="*100)
    print("UI DATA BINDING ANALYSIS")
    print("="*100)
    
    print("\nStep 1: Loading DBC and VehicleModel...")
    model = VehicleModel(dbc_path="dbc/EM06CAN.dbc")
    print(f"✓ Model initialized with {len(model.vehicle.pcbs)} PCBs")
    
    print("\nStep 2: Simulating signal updates (like from pipeline)...")
    
    # Simulate signal updates from different PCBs
    test_signals = [
        ("FrontECU_M1", "FpDIGRpot", 45.5),
        ("FrontECU_M2", "FpSHU", 1234.0),
        ("RearECU_M1", "RpSHU", 2000.0),
        ("RearECU_M2", "IpV", 350.0),
        ("RearECU_M3", "IpT_Mot", 65.0),
        ("Inverter", "iVout", 400.0),
        ("HVDB", "BpSHU", 3000.0),
        ("HVAB", "ApSHU", 1500.0),
        ("TSAL", "TpDIGspre", 1.0),
        ("SDCReset", "SpSHU", 2500.0),
    ]
    
    print(f"\nUpdating {len(test_signals)} signals:")
    for pcb_name, sig_name, value in test_signals:
        try:
            sig = model.update_signal(pcb_name, sig_name, value)
            print(f"  ✓ {pcb_name:15s}.{sig_name:15s} = {value:8.1f}")
        except Exception as e:
            print(f"  ❌ {pcb_name:15s}.{sig_name:15s}: {e}")
    
    print("\nStep 3: Verifying data in model...")
    
    # Check what's actually in the model
    print(f"\nModel state after updates:")
    print(f"{'PCB Name':<15} {'Status':<12} {'Signals':<10} {'Active':<10}")
    print("-" * 47)
    
    for pcb_name, pcb in model.vehicle.pcbs.items():
        active_signals = sum(1 for s in pcb.signals.values() if s.status != "TIMEOUT")
        total_signals = len(pcb.signals)
        status = pcb.status
        print(f"{pcb_name:<15} {status:<12} {total_signals:<10} {active_signals:<10}")
    
    print("\nStep 4: Checking UI access patterns...")
    
    # Check if UI can access signals the way it should
    print(f"\nTesting UI read access patterns:")
    
    access_patterns = [
        ("Direct access", lambda: model.vehicle.pcbs["FrontECU_M1"].signals.get("FpDIGRpot")),
        ("Get PCB first", lambda: model.vehicle.pcbs.get("FrontECU_M1", {}).signals.get("FpDIGRpot") if "FrontECU_M1" in model.vehicle.pcbs else None),
        ("List all signals", lambda: [(p, s.name, s.value) for p in model.vehicle.pcbs for s in model.vehicle.pcbs[p].signals.values() if s.status != "TIMEOUT"][:5]),
    ]
    
    for pattern_name, access_fn in access_patterns:
        try:
            result = access_fn()
            print(f"  ✓ {pattern_name}: Works - {result}")
        except Exception as e:
            print(f"  ❌ {pattern_name}: {e}")
    
    print("\nStep 5: Simulating UI refresh (like _ui_tick)...")
    
    # Simulate what the UI does every 250ms
    print(f"\nSimulating UI refresh cycle:")
    
    updated_count = 0
    for pcb_name, pcb in model.vehicle.pcbs.items():
        for sig in pcb.signals.values():
            if sig.status == "OK" or sig.value is not None:
                updated_count += 1
    
    print(f"  {updated_count} signals ready to display")
    
    # Show sample of what UI would display
    print(f"\nSample UI display (first 10 active signals):")
    displayed = 0
    for pcb_name, pcb in model.vehicle.pcbs.items():
        for sig_name, sig in pcb.signals.items():
            if sig.value is not None and displayed < 10:
                print(f"  [{sig.status:7s}] {pcb_name:15s}.{sig_name:15s} = {sig.value:8.2f} {sig.unit}")
                displayed += 1
    
    print("\n" + "="*100)
    print("UI DATA BINDING ANALYSIS COMPLETE")
    print("="*100 + "\n")


def check_specific_pcb_lookup():
    """Check if specific PCB lookup works (for new message names)."""
    print("\n" + "="*100)
    print("PCB LOOKUP VERIFICATION (Important for FrontECU_M1, RearECU_M2, etc.)")
    print("="*100)
    
    model = VehicleModel(dbc_path="dbc/EM06CAN.dbc")
    
    print("\nPCBs in model:")
    for pcb_name in sorted(model.vehicle.pcbs.keys()):
        signals = model.vehicle.pcbs[pcb_name].signals
        print(f"  {pcb_name:<20} ({len(signals)} signals)")
    
    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    check_specific_pcb_lookup()
    check_ui_data_binding()
