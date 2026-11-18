# Connectar tab: live CAN connection

## Why
Step 5 (plus the storing half of step 6) towards seeing live CAN data on the
dashboard. After this, frames from a Vector or PCAN adapter are stored in the
database while connected and can be checked on the bench.

## Goals
- Pick a connected adapter, optionally a bitrate, and Connect / Disconnect.
- While connected, store received frames and show frames stored, dropped and
  the last error.
- Show the driver hint when an adapter can't be opened, and notice when it is
  lost (e.g. unplugged).

## Non-goals
- Updating the Traffic light (steps 2 and 4); step 6 then only adds a
  `refresh()` call to the timer.
- Saving the recording to a file (`tools.live --save`).
- Showing the vehicle phase.

## Anti-goals
- Old data showing as the latest after a reconnect: each connection restarts
  timestamps at 0 ms, so Connect starts an empty database.

## Constraints
- The SQLite connection only works on the thread that created it, so frames are
  stored on the Tk thread.
- Without a bitrate the adapter keeps its own, so a Vector channel can be
  shared with CANalyzer.

## Approaches
- **Tk timer calling `receiver.flush()` every 200 ms (picked).** What
  `_Receiver` was designed for; no threads touch the database.
- Storing frames from a background thread: ruled out by the SQLite constraint.
- A blocking polling loop: would freeze the window.

Scope options: A (only Connect/Disconnect) or B (also store frames and show
status). B was picked, since it can be tested on the bench straight away.

## Design
```
Adaptador: [vector · 0          ▾] [⟳]
Bitrate:   [          ]  buit = la que ja té l'adaptador
[Connectar] [Desconnectar]
Estat: Connectat · 1 234 trames desades · 0 descartades
Error: —
```
- Read-only dropdown filled by `detect_channels()`; ⟳ detects again.
- Bitrate: empty means none; anything that isn't a positive whole number is an
  error.
- Connectar: fresh database via `get_all(SCHEMA_PATH)`, start a
  `CanBusReceiver`; on failure show the error and the `DRIVERS` hint.
- Timer: flush, update the status; if the receiver stops, show "Adaptador
  perdut" with its error and go back to disconnected.
- Desconnectar: stop, then flush the rest; the data stays in the database.
- Only the button that applies to the current state is enabled.
- Closing the window stops the receiver first.
- `DRIVERS` moves from `tools/live.py` to `src/can.py`.

## Left to the builder
Widget layout details, wording of messages, the exact timer period.
