from datetime import datetime
from pathlib import Path

import tkinter as tk
import ttkbootstrap as ttk
from .can import DRIVERS, CanBusReceiver, detect_channels, supported_interfaces
from .schema import Schema, get_all, get_schema
from .state import Phase, State, get_latest_state, get_phase
from .utils import unwrap
from can.typechecking import AutoDetectedConfig
from collections.abc import Callable

POLL_MS = 200
STATE_COLOURS = {State.OK: "lightgreen", State.WARNING: "#FFE08A", State.CRITICAL: "#FF8A80"}
NO_DATA_COLOUR = "#E0E0E0"

ICONS_DIR = Path(__file__).parent / "icons"
SCHEMA_PATH = "EMXCAN.json"


def signals_by_board(schema: Schema) -> dict[str, dict[str, list[str]]]:
    """Signal names grouped by sending board, then by message"""
    boards: dict[str, dict[str, list[str]]] = {}
    for name, message in schema.Messages.items():
        board = message.Senders[0] if message.Senders else "Other"
        boards.setdefault(board, {})[name] = list(message.Signals)
    return boards


def load_svg(name: str, width: int) -> tk.PhotoImage:
    """Tk 8.7+ renders SVGs itself; older versions need the tksvg package."""
    path = str(ICONS_DIR / name)
    if tk.TkVersion >= 8.7:
        return tk.PhotoImage(file=path, format=f"svg -scaletowidth {width}")
    import tksvg

    return tksvg.SvgImage(file=path, scaletowidth=width)

def build_trafficlight(parent_frame, signals):
    """Crea els elements visuals del Traffic Light una sola vegada."""
    lightframe = ttk.Frame(parent_frame, height=700, width=1300, borderwidth=2, relief="ridge")
    lightframe.pack(pady=5, padx=5, anchor="nw", side="left", expand=False)

    labels: dict[str, dict[str, ttk.Label]] = {}  # message -> signal -> label
    board_column_width = max((len(str(board)) for board in signals), default=8) + 1
    message_column_width = max((len(str(message)) for messages in signals.values() for message in messages), default=1) + 1

    for board, messages in signals.items():
        board_frame = ttk.Frame(lightframe, borderwidth=2, relief="ridge")
        board_frame.pack(pady=2, padx=2, anchor="w", fill="x")
        board_frame.columnconfigure(1, weight=1)

        board_label = ttk.Label(board_frame, text=board, width=board_column_width, font=("TkDefaultFont", 10, "bold"), anchor="nw",)
        board_label.grid(row=0, column=0, rowspan=max(len(messages), 1), pady=2, padx=2, sticky="nw",)

        for row, (message, signals_in_message) in enumerate(messages.items()):
            message_frame = ttk.Frame(board_frame, borderwidth=2, relief="ridge")
            message_frame.grid(row=row, column=1, pady=1, padx=2, sticky="ew")

            ttk.Label(message_frame, text=message, width=message_column_width, anchor="w").grid(
                row=0, column=0, pady=2, padx=2, sticky="w"
            )
            for column, signal in enumerate(signals_in_message, start=1):
                signal_frame = ttk.Frame(message_frame, borderwidth=0, relief=None)
                signal_frame.grid(row=0, column=column, pady=0, padx=2, sticky="w")
                # Two lines (name, value) in a smaller font, so every board fits the window;
                # a negative width is a minimum, so values changing don't shift the row much
                label = ttk.Label(signal_frame, padding=(5,0), justify="center", anchor="center", width=-6, font=("TkDefaultFont", 9))
                label.pack(pady=0, padx=0, anchor="center")
                labels.setdefault(message, {})[signal] = label

    def refresh() -> None:
        """Latest value of each signal, coloured by its state in the current phase"""
        schema = unwrap(get_schema())
        phase = get_phase() or Phase.I
        for message, message_labels in labels.items():
            states = get_latest_state(phase, message)
            for signal, label in message_labels.items():
                if signal in states:
                    value, state = states[signal]
                    unit = schema.Messages[message].Signals[signal].Unit
                    label.configure(text=f"{signal}\n{round(value, 2)} {unit}".rstrip(), background=STATE_COLOURS[state])
                else:
                    label.configure(text=f"{signal}\n—", background=NO_DATA_COLOUR)

    tsal_status = ttk.Frame(parent_frame, height=50, borderwidth=2, relief="ridge")
    tsal_status.pack(pady=5, padx=5, anchor="nw", side="left", expand=True, fill="x")
    ttk.Label(tsal_status, text="TSAL LIGHT", font=("TkDefaultFont", 12, "bold"), background="#FFCCCB", anchor="center", padding=(0,5)).pack(side="top", expand=True, fill="both")

    scs_signals = ttk.Frame(parent_frame, height=50, borderwidth=2, relief="ridge")
    scs_signals.pack(pady=5, padx=5, anchor="w", side="bottom", expand=True, fill="x")

    refresh()
    return refresh

def build_grafics(parent_frame, signals):
    
    config_frame = ttk.Frame(parent_frame, height=700, width=1300, borderwidth=2, relief="ridge")
    config_frame.pack(pady=5, padx=5, anchor="nw", side="left", expand=False)

    square = load_svg("square.svg", 24)
    rows_2 = load_svg("rows-2.svg", 24)
    columns_2 = load_svg("columns-2.svg", 24)
    icon_2x2 = load_svg("grid-2x2.svg", 24)

    # pack() returns None, so keep the button to hold a reference to its image
    square_button = ttk.Button(config_frame, image=square, padding=(0,0), cursor="hand2")
    square_button.pack(padx=5, pady=5, side="left")
    square_button.image = square

    rows_2_button = ttk.Button(config_frame, image=rows_2, padding=(0,0), cursor="hand2")
    rows_2_button.pack(padx=5, pady=5, side="left")
    rows_2_button.image = rows_2

    columns_2_button = ttk.Button(config_frame, image=columns_2, padding=(0,0), cursor="hand2")
    columns_2_button.pack(padx=5, pady=5, side="left")
    columns_2_button.image = columns_2

    icon_2x2_button = ttk.Button(config_frame, image=icon_2x2, padding=(0,0), cursor="hand2")
    icon_2x2_button.pack(padx=5, pady=5, side="left")
    icon_2x2_button.image = icon_2x2
def build_connect(parent_frame, on_data: Callable[[], None]):
    """Connexió en directe a un adaptador CAN; les trames es desen a la base de dades
    i on_data() actualitza el que es mostra."""
    frame = ttk.Frame(parent_frame, padding=10, borderwidth=2, relief="ridge")
    frame.pack(pady=20, padx=20, anchor="nw")

    channels: list[AutoDetectedConfig] = []
    receiver: CanBusReceiver | None = None
    job: str | None = None  # pending poll() timer

    ttk.Label(frame, text="Adaptador:").grid(row=0, column=0, sticky="w", pady=4)
    adapter = ttk.Combobox(frame, state="readonly", width=30)
    adapter.grid(row=0, column=1, sticky="w", pady=4)
    detect_button = ttk.Button(frame, text="⟳ Detectar", cursor="hand2")
    detect_button.grid(row=0, column=2, sticky="w", padx=5)

    ttk.Label(frame, text="Bitrate:").grid(row=1, column=0, sticky="w", pady=4)
    bitrate_row = ttk.Frame(frame)
    bitrate_row.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
    bitrate = ttk.Entry(bitrate_row, width=12)
    bitrate.pack(side="left")
    ttk.Label(bitrate_row, text="buit = la que ja té l'adaptador").pack(side="left", padx=5)

    buttons = ttk.Frame(frame)
    buttons.grid(row=2, column=0, columnspan=3, sticky="w", pady=8)
    connect_button = ttk.Button(buttons, text="Connectar", cursor="hand2")
    connect_button.pack(side="left")
    disconnect_button = ttk.Button(buttons, text="Desconnectar", cursor="hand2", state="disabled")
    disconnect_button.pack(side="left", padx=5)

    status = ttk.Label(frame, text="Desconnectat")
    status.grid(row=3, column=0, columnspan=3, sticky="w")
    error = ttk.Label(frame, text="", bootstyle="danger", wraplength=600)
    error.grid(row=4, column=0, columnspan=3, sticky="w")

    def counts(r: CanBusReceiver) -> str:
        return f"{r.received} trames desades · {r.dropped} descartades"

    def set_connected(connected: bool) -> None:
        idle = "disabled" if connected else "normal"
        adapter.configure(state="disabled" if connected else "readonly")
        for widget in (bitrate, detect_button, connect_button):
            widget.configure(state=idle)
        disconnect_button.configure(state="normal" if connected else "disabled")

    def detect() -> None:
        nonlocal channels
        try:
            channels = detect_channels()
        except Exception as e:
            channels = []
            error["text"] = f"No s'han pogut detectar els adaptadors: {e}"
        adapter["values"] = [f"{c['interface']} · {c['channel']}" for c in channels]
        if channels:
            adapter.current(0)
            error["text"] = ""
        else:
            adapter.set("")
            error["text"] = error["text"] or f"No s'ha trobat cap adaptador ({', '.join(supported_interfaces())})"

    def connect() -> None:
        nonlocal receiver
        text = bitrate.get().strip()
        if adapter.current() < 0:
            error["text"] = "Tria un adaptador"
            return
        if text and not (text.isdigit() and int(text) > 0):
            error["text"] = "El bitrate ha de ser un nombre enter positiu, p. ex. 500000"
            return

        config = channels[adapter.current()]
        interface, channel = config["interface"], config["channel"]
        # Empty database: timestamps restart at 0, so old rows would look newer
        _, can, conn = unwrap(get_all(SCHEMA_PATH))
        r = CanBusReceiver(can, conn, interface, channel, int(text) if text else None)
        try:
            r.start()
        except Exception as e:
            hint = f"\nCal: {DRIVERS[interface]}" if interface in DRIVERS else ""
            error["text"] = f"No s'ha pogut obrir {interface} canal {channel}: {e}{hint}"
            return

        receiver = r
        error["text"] = ""
        set_connected(True)
        poll()

    def disconnect(message: str = "") -> None:
        nonlocal receiver, job
        if job is not None:
            frame.after_cancel(job)
            job = None
        if receiver is None:
            return
        try:
            receiver.stop()
        except Exception as e:
            # e.g. the adapter was unplugged; keep what was received
            message = message or str(e)
        receiver.flush()
        on_data()
        status["text"] = f"Desconnectat · {counts(receiver)}"
        error["text"] = message
        receiver = None
        set_connected(False)

    def poll() -> None:
        nonlocal job
        job = None
        if receiver is None:
            return
        receiver.flush()
        on_data()
        status["text"] = f"Connectat · {counts(receiver)}"
        if receiver.last_error is not None:
            error["text"] = f"Últim error: {receiver.last_error}"
        if receiver.running:
            job = frame.after(POLL_MS, poll)
        else:
            disconnect(f"Adaptador perdut: {receiver.last_error}")

    def on_close() -> None:
        disconnect()
        root.destroy()

    detect_button.configure(command=detect)
    connect_button.configure(command=connect)
    disconnect_button.configure(command=disconnect)
    root = frame.winfo_toplevel()
    root.protocol("WM_DELETE_WINDOW", on_close)
    detect()

def build_temperatures(parent_frame, signals):
    """Crea els elements visuals del Temperatures una sola vegada."""
    tempframe = ttk.Frame(parent_frame, padding=10, borderwidth=2, relief="ridge")
    tempframe.pack(pady=20)

    for signal in signals:
        ttk.Label(tempframe, text=signal).pack()

def create_app():
    root = ttk.Window(themename="bootstrap-light")
    root.title("CANEM Viewer")
    root.geometry("1860x1045")
    root.resizable(False, False)

    ttk.Style().configure("TButton", focusthickness=0)

    # Carrega de dades
    dict_signals = signals_by_board(unwrap(get_schema(SCHEMA_PATH)))

    # Estructura de navegació
    mainmenu = {
        "Visualitzar": ("Traffic light", "Gràfics", "BMS", "SDC", "Dinàmica","Temperatures"),
        "Configuració": ("Connectar", "Editar fitxers"),
    }

    primary_notebook = ttk.Notebook(root, padding=0)
    primary_notebook.pack(fill="both", expand=True, padx=10, pady=10)

    # Construcció dinàmica del menú i submenús
    for menu_title, submenus in mainmenu.items():
        primary_frame = ttk.Frame(primary_notebook)
        primary_notebook.add(primary_frame, text=menu_title)

        secondary_notebook = ttk.Notebook(primary_frame)
        secondary_notebook.pack(fill="both", expand=True, padx=5, pady=5)

        for sub_title in submenus:
            sub_frame = ttk.Frame(secondary_notebook)
            secondary_notebook.add(sub_frame, text=sub_title)

            # Assignem el contingut específic directament en crear la pestanya
            if sub_title == "Traffic light":
                refresh_trafficlight = build_trafficlight(sub_frame, dict_signals)
            if sub_title == "Gràfics":
                build_grafics(sub_frame, dict_signals)
            if sub_title == "Connectar":
                # "Visualitzar" is built first, so the Traffic light already exists
                build_connect(sub_frame, refresh_trafficlight)
            if sub_title == "Temperatures":
                build_temperatures(sub_frame, dict_signals)
    return root


if __name__ == "__main__":
    app = create_app()
    app.mainloop()