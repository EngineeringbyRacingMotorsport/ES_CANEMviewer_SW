#!/usr/bin/env python3
"""
Master Diagnostic Guide - Step-by-step investigation of data flow.

This script orchestrates all diagnostics in the correct order.
"""
import subprocess
import sys

def print_header(title):
    """Print a formatted header."""
    print("\n" + "="*100)
    print(f"  {title}")
    print("="*100 + "\n")

def run_diagnostic(script_name, description):
    """Run a diagnostic script and ask user to continue."""
    print_header(description)
    print(f"Running: python {script_name}\n")
    
    try:
        subprocess.run([sys.executable, script_name], cwd=".")
    except Exception as e:
        print(f"Error running {script_name}: {e}")
    
    input("\n⏸️  Press ENTER to continue to next diagnostic...")

def main():
    print_header("CANEM VIEWER - DATA FLOW DIAGNOSTIC")
    print("""
This diagnostic suite will help identify where data is lost in the pipeline:

   PCAN Hardware → Raw Queue → Decoder → Decoded Queue → Model → UI

The tests will run in sequence and help you pinpoint the exact location of the problem.

Make sure:
  ✓ PCAN is connected and powered
  ✓ DBC file is at dbc/EM06CAN.dbc
  ✓ You can press CTRL+C to stop any test
    """)
    
    input("\n▶️  Press ENTER to start diagnostics...")
    
    print_header("DIAGNOSTIC SUITE - ORDER OF EXECUTION")
    print("""
1. check_ui_binding.py      → Verify UI can access model data
2. analyze_pipeline.py      → Test each pipeline stage individually
3. diagnose_bus_traffic.py  → Capture and decode raw CAN traffic
4. trace_data_flow.py       → Monitor complete pipeline with counters
    """)
    
    input("\n▶️  Press ENTER to begin...")
    
    # Test 1: UI Binding
    run_diagnostic(
        "check_ui_binding.py",
        "TEST 1/4: UI DATA BINDING"
    )
    
    # Test 2: Pipeline Analysis
    run_diagnostic(
        "analyze_pipeline.py",
        "TEST 2/4: PIPELINE STAGE ANALYSIS"
    )
    
    # Test 3: Bus Traffic
    run_diagnostic(
        "diagnose_bus_traffic.py",
        "TEST 3/4: RAW BUS TRAFFIC ANALYSIS"
    )
    
    # Test 4: Data Flow Tracing
    run_diagnostic(
        "trace_data_flow.py",
        "TEST 4/4: COMPLETE DATA FLOW TRACE"
    )
    
    print_header("DIAGNOSTIC SUITE COMPLETE")
    print("""
All tests completed. Review the output above to identify where data is lost:

POSSIBLE ISSUES:

❌ If TEST 1 failed:
   → Problem is in UI data access
   → Check: views.py, tabs.py for correct PCB/signal names

❌ If TEST 2 Stage 1-2 failed:
   → PCAN not receiving data
   → Check: PCAN hardware connection, power, DIP switches

❌ If TEST 2 Stage 3-4 failed:
   → Decoder or model not accepting data
   → Check: DBC file, signal names, message IDs

❌ If TEST 3 shows no messages:
   → No traffic on CAN bus
   → Check: Bus voltage, termination resistors, BUSMASTER

❌ If TEST 4 shows data loss between stages:
   → Data is being received but lost in queues
   → Check: Thread synchronization, queue timeouts

NEXT STEPS:
  1. Review the diagnostic output above
  2. Identify which stage is failing
  3. Check the corresponding component
  4. Run individual diagnostic as needed:
     - python check_ui_binding.py
     - python analyze_pipeline.py
     - python diagnose_bus_traffic.py 10  (10 = seconds to capture)
     - python trace_data_flow.py 20      (20 = seconds to trace)
    """)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Diagnostics interrupted by user")
        sys.exit(0)
