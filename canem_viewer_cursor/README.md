# CANEM Viewer Skeleton (Formula Student EV)

Esquelet executable de monitoratge CAN amb:

- Tkinter amb `frame` dinàmic i `footer` persistent.
- Model de dades centralitzat (`VehicleModel`).
- Pipeline de telemetria amb `threads + queue`.
- Validació de senyals (`rang`, `timeout`, `frozen`).
- Històric 60s per senyal amb `deque`.
- Persistència no bloquejant (`JSON` / `Pickle`).
- Modes:
  - `mock` (sense hardware)
  - `vector` (VN1610 via `python-can` + DBC via `cantools`)

## Execució

### 1) Mock mode (recomanat per provar la UI)

```bash
python app.py --mode mock
```

### 2) Vector mode (hardware real)

```bash
python app.py --mode vector --dbc dbc/formula_student.dbc --channel 0 --bitrate 500000 --app-name CANalyzer
```

## Dependències

```bash
pip install python-can cantools
```

> Nota: en `mock mode` no calen necessàriament aquestes dependències si no s'entra en mode vector.
