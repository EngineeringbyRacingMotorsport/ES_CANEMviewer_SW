# CANEM Viewer - Data Flow Analysis

## Complete Data Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DATA FLOW DIAGRAM                                 │
└─────────────────────────────────────────────────────────────────────────────┘

PCAN Hardware (250kbps)
    ↓ (CAN Messages: ID 0x100, 0x101, 0x102, etc.)
    ├─→ [PCAN Driver] ← Communication via python-can library
    ├─→ [PCANUSBReader Thread] ← Reads from PCAN bus continuously
    ├─→ [raw_queue] ← Queue with max 5000 frames
    │
    ├─→ [DBCDecoder._decode_loop()] ← Thread that decodes each frame
    │   ├─→ Get frame from raw_queue
    │   ├─→ Call cantools.db.decode_message(id, data)
    │   ├─→ Extract signal names, values, units
    │   ├─→ Map message to PCB name (e.g., "FrontECU_M1")
    │   └─→ Put decoded signals into decoded_queue
    │
    ├─→ [decoded_queue] ← Queue with max 5000 items
    │
    └─→ [Pipeline._model_loop()] ← Thread that updates model
        ├─→ Get signal from decoded_queue
        ├─→ Call VehicleModel.update_signal(pcb, signal, value)
        ├─→ Look up signal config from _config_for()
        ├─→ Update SignalState with new value
        ├─→ Call validate_signal() for status check
        └─→ Model now has latest data
            ↓
            └─→ [UI Thread - _ui_tick() every 250ms]
                ├─→ Read from VehicleModel.vehicle.pcbs[]
                ├─→ For each PCB, for each signal
                ├─→ Update GUI labels/values
                └─→ Display on Dashboard
```

## Key Components and Their Responsibilities

### 1. PCAN Hardware Reader (src/can_layer/vector_interface.py)
**Class**: `PCANUSBReader(threading.Thread)`

**Responsibility**: 
- Connect to PCAN-USB device
- Read raw CAN frames in a continuous loop
- Put frames into `raw_queue`

**Potential Issues**:
- ❌ PCAN not connected or powered
- ❌ Wrong channel (should be "PCAN_USBBUS1")
- ❌ Wrong bitrate (should be 250000)
- ❌ Python-can library doesn't have PCAN support
- ❌ PCAN drivers not installed
- ❌ queue.put() fails silently (queue full)

**Verification**: Check `raw_queue.qsize()` - should grow if data is being received

### 2. DBC Decoder (src/decoder/dbc_decoder.py)
**Class**: `DBCDecoder`

**Responsibility**:
- Load EM06CAN.dbc with cantools
- For each frame in raw_queue:
  - `db.get_message_by_frame_id(id)` - get message definition
  - `db.decode_message(id, data)` - decode signal values
  - Extract PCB name from message name
  - Create (pcb_name, signal_name, value, unit, desc) tuples
  - Put into decoded_queue

**Current Code** (src/decoder/dbc_decoder.py):
```python
def decode(self, arbitration_id: int, data: bytes):
    # Returns: (msg_def.name, sig_name, value, unit, desc)
    # msg_def.name = "FrontECU_M1", "FrontECU_M2", etc.
```

**Potential Issues**:
- ❌ DBC file not found or not loading
- ❌ Message ID in frame not in DBC
- ❌ Data format/DLC mismatch
- ❌ Signal byte order issues
- ❌ Decode exceptions caught silently and return []
- ❌ decoded_queue.put_nowait() fails (queue full)

**Verification**: Check if decoded_queue has items, if decoder returns non-empty list

### 3. Pipeline Decode Loop (src/services/pipeline.py)
**Method**: `TelemetryPipeline._decode_loop()`

**Responsibility**:
- Continuously get frames from raw_queue (timeout 0.05s)
- Call decoder.decode() for each frame
- Put results into decoded_queue
- Skip frames that decode to []

**Current Code**:
```python
def _decode_loop(self) -> None:
    while not self.stop_event.is_set():
        try:
            item = self.raw_queue.get(timeout=0.05)
        except Empty:
            continue
        
        frame = item
        decoded = self.decoder.decode(frame.arbitration_id, frame.data)
        # Put each signal into decoded_queue
```

**Potential Issues**:
- ❌ Timeout too short (0.05s) causes messages to be skipped
- ❌ decoded = [] means no signals extracted
- ❌ Exception in decode() silently passes
- ❌ decoded_queue full causes put_nowait() to fail

### 4. Model Update Loop (src/services/pipeline.py)
**Method**: `TelemetryPipeline._model_loop()`

**Responsibility**:
- Continuously get signals from decoded_queue
- Update VehicleModel with signal values
- Validate signal status (OK/WARNING/ERROR/TIMEOUT)
- Recompute global state

**Current Code**:
```python
def _model_loop(self) -> None:
    while not self.stop_event.is_set():
        item = self.decoded_queue.get(timeout=0.05)
        pcb_name, sig_name, value, ... = item
        
        cfg = self._config_for(pcb_name, sig_name)
        sig = self.model.update_signal(pcb_name, sig_name, value, ...)
        sig.status = validate_signal(sig, now=ts)
        self.model.recompute_global_state()
```

**Potential Issues**:
- ❌ PCB name not matching what UI expects (FrontECU_M1 vs FrontECU)
- ❌ Signal name not matching what UI expects
- ❌ Signal configuration (_config_for) returns wrong min/max
- ❌ validate_signal() marks signal as ERROR/TIMEOUT
- ❌ Exception caught silently

### 5. Vehicle Model (src/model/vehicle_model.py)
**Class**: `VehicleModel`

**Responsibility**:
- Maintain vehicle state with hierarchy: Vehicle → PCBs → Signals
- Accept updates from pipeline via `update_signal()`
- Store signal value, status, timestamp, history
- Recompute global status

**Structure**:
```
VehicleModel.vehicle
  ├─ pcbs["FrontECU_M1"]
  │   ├─ signals["FpDIGRpot"]
  │   │   ├─ value: 45.5
  │   │   ├─ status: "OK" | "WARNING" | "ERROR" | "TIMEOUT"
  │   │   ├─ unit: "%"
  │   │   ├─ description: "..."
  │   └─ status: "OK" (aggregate)
  │
  ├─ pcbs["FrontECU_M2"]
  │   └─ ...
  │
  └─ vehicle_status: "OK" (aggregate)
```

**Potential Issues**:
- ❌ PCB created but signals not in initialized structure
- ❌ Signal name doesn't match initialization from DBC
- ❌ Status marked as TIMEOUT due to timeout config
- ❌ Lock contention (threading issue)

### 6. UI Thread (src/ui/main_window.py)
**Method**: `MainWindow._ui_tick()` (called every 250ms)

**Responsibility**:
- Read from VehicleModel.vehicle.pcbs[]
- For each PCB and signal
- Update GUI widgets with values and status colors

**Current Code** (conceptual):
```python
def _ui_tick(self):
    for pcb_name, pcb in self.model.vehicle.pcbs.items():
        for signal_name, signal in pcb.signals.items():
            # Update GUI: label.text = f"{signal.value} {signal.unit}"
            # Update color based on signal.status
```

**Potential Issues**:
- ❌ UI looking for PCB name that doesn't exist
- ❌ Signal value is None (not updated)
- ❌ Status is TIMEOUT (display shows gray)
- ❌ UI crash due to missing PCB/signal

## Data Loss Points - Where to Check

### Point 1️⃣: PCAN Hardware → raw_queue
**Question**: Is PCAN reading any frames?

**Check**:
```bash
python analyze_pipeline.py  # Test 1
```

**Expected**: 100+ frames in 5 seconds (for 250kbps bus with traffic)

**If No Data**:
- Check PCAN is powered and connected
- Check DIP switches on PCAN device
- Check CAN bus has traffic (verify with BUSMASTER)
- Check bitrate is 250000 (not 500000 or other)
- Run `python diagnose_pcan.py` to test PCAN connectivity

### Point 2️⃣: raw_queue → Decoder → decoded_queue
**Question**: Does decoder successfully decode frames?

**Check**:
```bash
python analyze_pipeline.py  # Test 2
```

**Expected**: All frames should decode (no ❌ marks)

**If Decoder Fails**:
- Check DBC file loads correctly: `python check_ui_binding.py`
- Verify message IDs in DBC match CAN frames
- Check data format (DLC, byte order)
- Verify signal definitions in DBC

**Code Check**:
```python
# In src/decoder/dbc_decoder.py
decoded = self.decoder.decode(frame.arbitration_id, frame.data)
# If this returns [], frame wasn't decoded
```

### Point 3️⃣: decoded_queue → VehicleModel.update_signal()
**Question**: Does model accept decoded signals?

**Check**:
```bash
python analyze_pipeline.py  # Test 3
```

**Expected**: All signals should update (0 errors)

**If Model Update Fails**:
- Check PCB names are correct
- Check signal names in DBC match what UI expects
- Check _config_for() returns valid config
- Check model doesn't have threading issues

**Code Check**:
```python
# In src/services/pipeline.py _model_loop()
pcb_name, sig_name, value, ... = decoded_item
model.update_signal(pcb_name=pcb_name, signal_name=sig_name, value=value)
```

### Point 4️⃣: VehicleModel → UI Display
**Question**: Does UI properly read from model?

**Check**:
```bash
python check_ui_binding.py
```

**Expected**: Model should have valid data, UI should be able to access it

**If UI Not Updating**:
- Check PCB names in UI match model structure
- Check signal lookup is correct
- Check _ui_tick() is being called
- Check signal.value is not None

**Code Check**:
```python
# In src/ui/views.py or tabs.py
pcb = self.model.vehicle.pcbs.get("FrontECU_M1")
if pcb:
    sig = pcb.signals.get("FpDIGRpot")
    if sig and sig.value is not None:
        label.text = f"{sig.value:.1f} {sig.unit}"
```

## Quick Diagnosis Checklist

```
[ ] PCAN connected and powered
[ ] DBC file exists at dbc/EM06CAN.dbc
[ ] BUSMASTER shows CAN traffic
[ ] python analyze_pipeline.py - Test 1 shows ✓ frames received
[ ] python analyze_pipeline.py - Test 2 shows ✓ frames decoded
[ ] python analyze_pipeline.py - Test 3 shows ✓ signals updated
[ ] python check_ui_binding.py shows model has data
[ ] python app.py --debug shows "[DECODE]" output
[ ] Dashboard displays values (not all TIMEOUT)
```

## Running Full Diagnostic

```bash
python run_diagnostics.py
```

This will run all tests in sequence and help identify exactly where data is lost.

## Debug Output

Enable debug mode in the application:

```bash
python app.py --auto-detect --debug
```

This will print to terminal:
```
[DECODE] 0x100: FpDIGRpot=45.50, FpDIGLpot=50.20, ... (msg #1)
[DECODE] 0x101: FpSHU=1234.00, ... (msg #101)
...
```

If you see no output, data is not being decoded.

## Common Issues and Solutions

| Symptom | Possible Cause | Solution |
|---------|---|---|
| Dashboard all TIMEOUT | No data from PCAN | Check PCAN connection, run diagnose_pcan.py |
| Only HVDB shows values | Decoder returns wrong PCB names | Check message sender field in DBC |
| Some signals missing | Signal names don't match | Verify signal names in DBC vs UI |
| Data stops after 10s | Thread crashed silently | Check app.py for exceptions |
| High CPU usage | Infinite loop or bad lock | Check pipeline threads |
