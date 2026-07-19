#!/usr/bin/env python3
"""
Detailed pipeline analysis - identifies exactly where data is lost.
"""
import sys
import time
import threading
import cantools
from queue import Queue, Empty

def analyze_pcan_reader():
    """Test 1: PCAN Reader - Does it receive frames?"""
    print("\n" + "="*100)
    print("TEST 1️⃣  PCAN READER - Hardware reception")
    print("="*100)
    
    from src.can_layer.vector_interface import auto_detect_interface, PCANUSBReader
    
    interface_name, config = auto_detect_interface()
    print(f"Detected: {interface_name}")
    
    if interface_name != "pcan":
        print(f"❌ Not PCAN! Got {interface_name} instead")
        return None
    
    print(f"Config: {config}")
    print(f"\nListening for 5 seconds...\n")
    
    raw_queue = Queue()
    stop_event = threading.Event()
    
    reader = PCANUSBReader(
        output_queue=raw_queue,
        stop_event=stop_event,
        channel=config.get("channel", "PCAN_USBBUS1"),
        bitrate=config.get("bitrate", 250000),
    )
    
    reader.start()
    frames = []
    start = time.time()
    
    while time.time() - start < 5:
        try:
            frame = raw_queue.get(timeout=0.1)
            frames.append(frame)
            if len(frames) <= 3 or len(frames) % 100 == 0:
                print(f"  Frame #{len(frames)}: ID=0x{frame.arbitration_id:03X}, DLC={len(frame.data)}, Data={frame.data.hex()}")
        except Empty:
            pass
    
    stop_event.set()
    reader.join(timeout=2)
    
    print(f"\n✓ Result: {len(frames)} frames received")
    if len(frames) == 0:
        print("❌ PROBLEM: No frames received from PCAN!")
        return None
    
    return frames


def analyze_dbc_decoder(frames):
    """Test 2: DBC Decoder - Can it decode the frames?"""
    print("\n" + "="*100)
    print("TEST 2️⃣  DBC DECODER - Message decoding")
    print("="*100)
    
    from src.decoder.dbc_decoder import DBCDecoder
    
    try:
        decoder = DBCDecoder("dbc/EM06CAN.dbc")
        if not decoder.available:
            print("❌ Decoder not available")
            return None
    except Exception as e:
        print(f"❌ Failed to load decoder: {e}")
        return None
    
    print(f"DBC loaded: {len(decoder.db.messages)} messages")
    print(f"\nTesting decode on first 10 frames:\n")
    
    decoded_count = 0
    failed_count = 0
    decoded_frames = []
    
    for i, frame in enumerate(frames[:10]):
        try:
            decoded = decoder.decode(frame.arbitration_id, frame.data)
            if decoded:
                print(f"  Frame 0x{frame.arbitration_id:03X}: ✓ Decoded {len(decoded)} signals")
                decoded_count += 1
                decoded_frames.append((frame, decoded))
                # Show first 2 signals
                for j, (pcb, sig, val, unit, desc) in enumerate(decoded[:2]):
                    print(f"    → {pcb}.{sig} = {val} {unit}")
            else:
                print(f"  Frame 0x{frame.arbitration_id:03X}: ⚠️  No signals decoded")
                failed_count += 1
        except Exception as e:
            print(f"  Frame 0x{frame.arbitration_id:03X}: ❌ Error: {e}")
            failed_count += 1
    
    print(f"\n✓ Result: {decoded_count}/{len(frames[:10])} frames decoded successfully")
    if decoded_count == 0:
        print("❌ PROBLEM: Decoder cannot decode any frames!")
        return None
    
    return decoded_frames


def analyze_vehicle_model(decoded_frames):
    """Test 3: Vehicle Model - Does it accept the decoded data?"""
    print("\n" + "="*100)
    print("TEST 3️⃣  VEHICLE MODEL - Signal updates")
    print("="*100)
    
    from src.model.vehicle_model import VehicleModel
    
    try:
        model = VehicleModel(dbc_path="dbc/EM06CAN.dbc")
    except Exception as e:
        print(f"❌ Failed to create model: {e}")
        return None
    
    print(f"Model initialized: {len(model.vehicle.pcbs)} PCBs")
    for pcb_name, pcb in list(model.vehicle.pcbs.items())[:5]:
        print(f"  - {pcb_name}: {len(pcb.signals)} signals")
    
    print(f"\nUpdating model with {len(decoded_frames)} decoded frames:\n")
    
    update_count = 0
    pcbs_updated = set()
    
    for frame, decoded in decoded_frames:
        for pcb_name, sig_name, value, unit, desc in decoded:
            try:
                model.update_signal(
                    pcb_name=pcb_name,
                    signal_name=sig_name,
                    value=value,
                    unit=unit,
                    description=desc,
                )
                update_count += 1
                pcbs_updated.add(pcb_name)
                print(f"  ✓ Updated {pcb_name}.{sig_name} = {value}")
            except Exception as e:
                print(f"  ❌ Failed to update {pcb_name}.{sig_name}: {e}")
    
    print(f"\n✓ Result: {update_count} signals updated in {len(pcbs_updated)} PCBs")
    
    # Check if updates are actually in the model
    print(f"\nVerifying model state:")
    for pcb_name in list(pcbs_updated):
        pcb = model.vehicle.pcbs.get(pcb_name)
        if pcb:
            updated_signals = [s for s in pcb.signals.values() if s.status != "TIMEOUT"]
            print(f"  {pcb_name}: {len(updated_signals)}/{len(pcb.signals)} signals have values")
    
    if update_count == 0:
        print("❌ PROBLEM: No signals updated in model!")
        return None
    
    return model


def analyze_pipeline_queues():
    """Test 4: Pipeline Queues - Is data flowing through queues?"""
    print("\n" + "="*100)
    print("TEST 4️⃣  PIPELINE QUEUES - Data flow through queues")
    print("="*100)
    
    from src.model.vehicle_model import VehicleModel
    from src.services.pipeline import TelemetryPipeline
    from src.can_layer.vector_interface import auto_detect_interface
    
    interface_name, config = auto_detect_interface()
    
    model = VehicleModel(dbc_path="dbc/EM06CAN.dbc")
    pipeline = TelemetryPipeline(
        model=model,
        dbc_path="dbc/EM06CAN.dbc",
        pcan_channel=config.get("channel", "PCAN_USBBUS1"),
        pcan_bitrate=config.get("bitrate", 250000),
        interface="pcan",
        no_vector=False,
    )
    
    # Tracking
    raw_in = 0
    raw_out = 0
    decoded_in = 0
    decoded_out = 0
    
    def count_queues():
        nonlocal raw_in, raw_out, decoded_in, decoded_out
        while not pipeline.stop_event.is_set():
            try:
                # Check raw queue
                pipeline.raw_queue.get_nowait()
                raw_out += 1
            except:
                pass
            
            try:
                # Check decoded queue
                pipeline.decoded_queue.get_nowait()
                decoded_out += 1
            except:
                pass
            
            time.sleep(0.1)
    
    print("Running pipeline for 10 seconds with queue monitoring...\n")
    
    # Start monitoring thread
    monitor = threading.Thread(target=count_queues, daemon=True)
    
    pipeline.start()
    monitor.start()
    
    time.sleep(10)
    pipeline.stop()
    
    # Get queue sizes before stopping
    raw_size = pipeline.raw_queue.qsize()
    decoded_size = pipeline.decoded_queue.qsize()
    
    print(f"Raw queue final size: {raw_size}")
    print(f"Decoded queue final size: {decoded_size}")
    print(f"\n✓ Pipeline ran for 10 seconds")


def full_integration_test():
    """Complete integration test with detailed analysis."""
    print("\n" + "="*100)
    print("COMPLETE DATA FLOW ANALYSIS")
    print("="*100)
    
    # Test 1: PCAN reader
    print("\n[STAGE 1] Testing PCAN hardware reception...")
    frames = analyze_pcan_reader()
    if not frames:
        print("\n⛔ Cannot proceed - PCAN reader not working")
        return
    
    # Test 2: DBC decoder
    print("\n[STAGE 2] Testing DBC decoder...")
    decoded_frames = analyze_dbc_decoder(frames)
    if not decoded_frames:
        print("\n⛔ Cannot proceed - DBC decoder not working")
        return
    
    # Test 3: Vehicle model
    print("\n[STAGE 3] Testing vehicle model...")
    model = analyze_vehicle_model(decoded_frames)
    if not model:
        print("\n⛔ Cannot proceed - Vehicle model not accepting data")
        return
    
    # Test 4: Full pipeline
    print("\n[STAGE 4] Testing full pipeline...")
    analyze_pipeline_queues()
    
    print("\n" + "="*100)
    print("ANALYSIS COMPLETE")
    print("="*100 + "\n")


if __name__ == "__main__":
    full_integration_test()
