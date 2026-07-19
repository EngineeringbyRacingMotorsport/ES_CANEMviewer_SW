#!/usr/bin/env python3
"""
Quick Check - Fast verification of each pipeline stage.
"""
import sys
import time
from queue import Queue, Empty
import threading

def quick_check():
    """Quick verification of data flow."""
    print("\n" + "="*80)
    print("QUICK DATA FLOW CHECK")
    print("="*80 + "\n")
    
    checks_passed = 0
    checks_failed = 0
    
    # Check 1: DBC Loading
    print("✓ Checking DBC file...")
    try:
        import cantools
        db = cantools.database.load_file("dbc/EM06CAN.dbc")
        print(f"  ✓ DBC loaded: {len(db.messages)} messages, {sum(len(m.signals) for m in db.messages)} signals")
        checks_passed += 1
    except Exception as e:
        print(f"  ❌ DBC load failed: {e}")
        checks_failed += 1
    
    # Check 2: PCAN Detection
    print("\n✓ Checking PCAN availability...")
    try:
        from src.can_layer.vector_interface import detect_pcan_available, list_pcan_channels
        if detect_pcan_available():
            channels = list_pcan_channels()
            print(f"  ✓ PCAN available: {channels}")
            checks_passed += 1
        else:
            print(f"  ❌ PCAN not detected")
            checks_failed += 1
    except Exception as e:
        print(f"  ❌ PCAN check failed: {e}")
        checks_failed += 1
    
    # Check 3: Decoder
    print("\n✓ Checking DBCDecoder...")
    try:
        from src.decoder.dbc_decoder import DBCDecoder
        decoder = DBCDecoder("dbc/EM06CAN.dbc")
        if decoder.available:
            print(f"  ✓ Decoder ready")
            checks_passed += 1
        else:
            print(f"  ❌ Decoder not available")
            checks_failed += 1
    except Exception as e:
        print(f"  ❌ Decoder check failed: {e}")
        checks_failed += 1
    
    # Check 4: VehicleModel
    print("\n✓ Checking VehicleModel...")
    try:
        from src.model.vehicle_model import VehicleModel
        model = VehicleModel(dbc_path="dbc/EM06CAN.dbc")
        pcb_count = len(model.vehicle.pcbs)
        print(f"  ✓ Model initialized: {pcb_count} PCBs")
        checks_passed += 1
    except Exception as e:
        print(f"  ❌ Model check failed: {e}")
        checks_failed += 1
    
    # Check 5: PCAN Data Reception (5 seconds)
    print("\n✓ Checking PCAN data reception (5 seconds)...")
    try:
        from src.can_layer.vector_interface import PCANUSBReader, auto_detect_interface
        
        interface_name, config = auto_detect_interface()
        if interface_name == "pcan":
            raw_queue = Queue()
            stop_event = threading.Event()
            
            reader = PCANUSBReader(
                output_queue=raw_queue,
                stop_event=stop_event,
                channel=config.get("channel", "PCAN_USBBUS1"),
                bitrate=config.get("bitrate", 250000),
            )
            
            reader.start()
            frame_count = 0
            start = time.time()
            
            while time.time() - start < 5:
                try:
                    frame = raw_queue.get(timeout=0.1)
                    frame_count += 1
                except Empty:
                    pass
            
            stop_event.set()
            reader.join(timeout=2)
            
            if frame_count > 0:
                print(f"  ✓ Received {frame_count} frames ({frame_count/5:.0f} frames/sec)")
                checks_passed += 1
            else:
                print(f"  ❌ No frames received (check PCAN connection/power)")
                checks_failed += 1
        else:
            print(f"  ⚠️  PCAN not available (got {interface_name})")
    except Exception as e:
        print(f"  ❌ Reception check failed: {e}")
        checks_failed += 1
    
    # Summary
    print("\n" + "="*80)
    print(f"RESULTS: {checks_passed} passed, {checks_failed} failed")
    print("="*80 + "\n")
    
    if checks_failed == 0:
        print("✓ All checks passed! Data flow should work.")
        print("\nTroubleshooting data display issues:")
        print("  1. Run: python app.py --auto-detect --debug")
        print("  2. Check terminal output for [DECODE] messages")
        print("  3. If no [DECODE] output: run python analyze_pipeline.py")
        print("  4. For complete analysis: python run_diagnostics.py")
    else:
        print("❌ Some checks failed. Fix these issues first:")
        print("\nFailing checks:")
        if checks_failed > 0:
            print("  1. Check DBC file at dbc/EM06CAN.dbc")
            print("  2. Check PCAN hardware connection and power")
            print("  3. Check CAN bus traffic with BUSMASTER")
            print("  4. Run: python run_diagnostics.py for detailed analysis")
    
    return checks_failed == 0

if __name__ == "__main__":
    success = quick_check()
    sys.exit(0 if success else 1)
