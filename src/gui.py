from datetime import datetime
from pathlib import Path

import tkinter as tk
import ttkbootstrap as ttk
from .can import DRIVERS, CanBusReceiver, detect_channels, supported_interfaces
from .schema import Schema, Signal, get_all, get_schema, new_connection, set_connection
from .state import (
    Phase,
    State,
    get_last_samples,
    get_latest_state,
    get_latest_times,
    get_newest_time,
    get_phase,
)
from .utils import unwrap
from can.typechecking import AutoDetectedConfig
from collections.abc import Callable
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

POLL_MS = 200
STATE_COLOURS = {State.OK: "lightgreen", State.WARNING: "#FFE08A", State.CRITICAL: "#FF8A80"}
NO_DATA_COLOUR = "#E0E0E0"
PHASE_NAMES = {
    Phase.I: "Repòs",
    Phase.P: "Precàrrega",
    Phase.T: "Alta tensió activa",
    Phase.R: "Llest per conduir",
}

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
    schema = unwrap(get_schema())
    # Every signal's state depends on the phase, so it's shown above both views
    phase_label = ttk.Label(parent_frame, font=("TkDefaultFont", 11, "bold"), padding=(5, 2))
    phase_label.pack(side="top", anchor="w")
    grid_view = ttk.Frame(parent_frame)
    grid_view.pack(fill="both", expand=True)
    node_view: dict[str, Callable[[], None]] = {}  # "refresh" / "close" of the open node, if any

    lightframe = ttk.Frame(grid_view, height=700, width=1300, borderwidth=2, relief="ridge")
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
        for widget in (board_frame, board_label):
            clickable(widget, lambda board=board: open_node(board))

        for row, (message, signals_in_message) in enumerate(messages.items()):
            message_frame = ttk.Frame(board_frame, borderwidth=2, relief="ridge")
            message_frame.grid(row=row, column=1, pady=2, padx=2, sticky="ew")

            message_label = ttk.Label(message_frame, text=message, width=message_column_width, anchor="w")
            message_label.grid(row=0, column=0, pady=2, padx=2, sticky="w")
            for widget in (message_frame, message_label):
                clickable(widget, lambda board=board: open_node(board))
            for column, signal in enumerate(signals_in_message, start=1):
                signal_frame = ttk.Frame(message_frame, borderwidth=2, relief=None)
                signal_frame.grid(row=0, column=column, pady=2, padx=2, sticky="w")
                label = ttk.Label(signal_frame, text=signal, padding=(5,0))
                label.pack(pady=0, padx=0, anchor="center")
                labels.setdefault(message, {})[signal] = label
                for widget in (signal_frame, label):
                    clickable(widget, lambda board=board, message=message, signal=signal: open_node(board, (message, signal)))

    def refresh() -> None:
        """Colours each signal by its latest state in the current phase"""
        current = get_phase()
        phase_label["text"] = f"Fase: {current.name} · {PHASE_NAMES[current]}" if current else "Fase: —"
        phase = current or Phase.I
        for message, message_labels in labels.items():
            states = get_latest_state(phase, message)
            for signal, label in message_labels.items():
                state = states.get(signal)
                label.configure(background=STATE_COLOURS[state[1]] if state else NO_DATA_COLOUR)
        if "refresh" in node_view:
            node_view["refresh"]()

    def open_node(node: str, selected: tuple[str, str] | None = None) -> None:
        if "close" in node_view:
            node_view["close"]()
        grid_view.pack_forget()
        node_view.update(build_node_view(parent_frame, schema, node, signals[node], selected))

    def close_node() -> None:
        if "close" in node_view:
            node_view.pop("close")()
            node_view.pop("refresh")
            grid_view.pack(fill="both", expand=True)

    # Clicking the "Traffic light" tab goes back to the grid
    notebook = parent_frame.master

    def on_tab_click(event: tk.Event) -> None:
        try:
            index = notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return  # not on a tab
        if notebook.tabs()[index] == str(parent_frame):
            close_node()

    notebook.bind("<Button-1>", on_tab_click, add="+")

    tsal_status = ttk.Frame(grid_view, height=50, borderwidth=2, relief="ridge")
    tsal_status.pack(pady=5, padx=5, anchor="nw", side="left", expand=True, fill="x")
    ttk.Label(tsal_status, text="TSAL LIGHT", font=("TkDefaultFont", 12, "bold"), background="#FFCCCB", anchor="center", padding=(0,5)).pack(side="top", expand=True, fill="both")

    scs_signals = ttk.Frame(grid_view, height=50, borderwidth=2, relief="ridge")
    scs_signals.pack(pady=5, padx=5, anchor="w", side="bottom", expand=True, fill="x")

    refresh()
    return refresh


def clickable(widget: tk.Widget, command: Callable[[], None]) -> None:
    widget.configure(cursor="hand2")
    widget.bind("<Button-1>", lambda _: command())


def format_value(signal: Signal, value: int | float) -> str:
    text = f"{value:g}"
    if signal.Choices and value == int(value) and int(value) in signal.Choices:
        text += f" ({signal.Choices[int(value)]})"
    return text


def build_node_view(
    parent_frame, schema: Schema, node: str, messages: dict[str, list[str]], selected: tuple[str, str] | None
) -> dict[str, Callable[[], None]]:
    """Taules dels missatges d'un node a l'esquerra i gràfic del senyal triat a la dreta.
    Returns its "refresh" and "close" functions."""
    view = ttk.Frame(parent_frame)
    view.pack(fill="both", expand=True, padx=5, pady=5)
    ttk.Label(view, text=node, font=("TkDefaultFont", 12, "bold")).pack(anchor="w", pady=(0, 5))
    left = ttk.Frame(view)
    left.pack(side="left", fill="y", anchor="n")
    right = ttk.Frame(view)
    right.pack(side="left", fill="both", expand=True, padx=(10, 0))

    tables: dict[str, ttk.Treeview] = {}
    for message, signals_in_message in messages.items():
        box = ttk.Labelframe(left, text=message, padding=4)
        box.pack(fill="x", anchor="n", pady=3)
        tree = ttk.Treeview(box, columns=("value", "unit", "age"), height=len(signals_in_message), selectmode="browse")
        for column, text, width in (("#0", "Senyal", 170), ("value", "Valor", 120), ("unit", "Unitat", 60), ("age", "Fa (ms)", 70)):
            tree.heading(column, text=text, anchor="w")
            tree.column(column, width=width, stretch=False, anchor="w" if column == "#0" else "e")
        tree.tag_configure("none", background=NO_DATA_COLOUR)
        for state, colour in STATE_COLOURS.items():
            tree.tag_configure(state.name, background=colour)
        for signal in signals_in_message:
            tree.insert("", "end", iid=signal, text=signal, values=("—", schema.Messages[message].Signals[signal].Unit, "—"), tags=("none",))
        tree.pack(fill="x")
        tree.bind("<<TreeviewSelect>>", lambda _, message=message: select(message))
        tables[message] = tree

    # Packed before the graph, which then takes the space that's left
    controls = ttk.Frame(right)
    controls.pack(side="bottom", anchor="w", pady=5)
    # Small requested size: the graph grows to fill the window, never past it
    figure = Figure(figsize=(4, 3), layout="constrained")
    axes = figure.add_subplot()
    (line,) = axes.plot([], [], marker=".", markersize=3, linewidth=1)
    axes.set_xlabel("Temps (s)")
    axes.grid(True, alpha=0.3)
    canvas = FigureCanvasTkAgg(figure, master=right)
    canvas.get_tk_widget().pack(fill="both", expand=True)
    ttk.Label(controls, text="Últims").pack(side="left")
    count = ttk.Spinbox(controls, from_=10, to=5000, increment=50, width=6, command=lambda: draw())
    count.set(200)
    count.pack(side="left", padx=5)
    count.bind("<Return>", lambda _: draw())
    ttk.Label(controls, text="valors").pack(side="left")

    graphed: list[tuple[str, str]] = []  # the selected (message, signal)

    def select(message: str) -> None:
        tree = tables[message]
        if not tree.selection():
            return  # cleared because another table was selected
        for other in tables.values():
            if other is not tree:
                other.selection_remove(other.selection())
        graphed[:] = [(message, tree.selection()[0])]
        draw()

    def draw() -> None:
        if not graphed:
            return
        message, signal = graphed[0]
        try:
            limit = max(1, int(count.get()))
        except ValueError:
            limit = 200
        samples = get_last_samples(message, signal, limit)
        line.set_data([t / 1000 for t, _ in samples], [v for _, v in samples])
        unit = schema.Messages[message].Signals[signal].Unit
        axes.set_title(signal)
        axes.set_ylabel(unit)
        # Both axes follow the samples shown
        axes.relim()
        axes.autoscale_view()
        canvas.draw_idle()

    def refresh() -> None:
        phase = get_phase() or Phase.I
        newest = get_newest_time()
        for message, tree in tables.items():
            signals = schema.Messages[message].Signals
            states = get_latest_state(phase, message)
            times = get_latest_times(message)
            for signal in tree.get_children():
                unit = signals[signal].Unit
                if signal in states and newest is not None:
                    value, state = states[signal]
                    tree.item(signal, values=(format_value(signals[signal], value), unit, newest - times[signal]), tags=(state.name,))
                else:
                    tree.item(signal, values=("—", unit, "—"), tags=("none",))
        draw()

    first_message = next(iter(messages))
    message, signal = selected or (first_message, messages[first_message][0])
    tables[message].selection_set(signal)
    tables[message].see(signal)
    graphed[:] = [(message, signal)]
    refresh()
    return {"refresh": refresh, "close": view.destroy}

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
    ttk.Label(bitrate_row, text="buit = la que ja té l'adaptador (PCAN: 500000)").pack(side="left", padx=5)

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
        failure: Exception | None = None
        try:
            channels = detect_channels()
        except Exception as e:
            channels = []
            failure = e
        adapter["values"] = [
            f"{c['interface']} · {c['channel']}" + (f" · {c['serial']}" if "serial" in c else "")
            for c in channels
        ]
        if channels:
            adapter.current(0)
            error["text"] = ""
        else:
            adapter.set("")
            error["text"] = (
                f"No s'han pogut detectar els adaptadors: {failure}"
                if failure is not None
                else f"No s'ha trobat cap adaptador ({', '.join(supported_interfaces())})"
            )

    def connect() -> None:
        nonlocal receiver
        text = bitrate.get().strip()
        if adapter.current() < 0:
            error["text"] = "Tria un adaptador"
            return
        if text and not (text.isdecimal() and int(text) > 0):
            error["text"] = "El bitrate ha de ser un nombre enter positiu, p. ex. 500000"
            return

        config = channels[adapter.current()]
        interface, channel = config["interface"], config["channel"]
        if interface == "pcan" and text:
            # python-can silently opens PCAN at 500000 for any other bitrate
            from can.interfaces.pcan.basic import PCAN_BITRATES

            if int(text) not in PCAN_BITRATES:
                error["text"] = f"PCAN només admet aquests bitrates: {', '.join(map(str, sorted(PCAN_BITRATES)))}"
                return
        # Vector channel numbers repeat on each device, so open it on the detected
        # one; by serial, which stays the same if the adapter is plugged in again
        device = {"serial": config["serial"]} if "serial" in config else {}
        # Empty database: timestamps restart at 0, so old rows would look newer.
        # The previous one is only replaced once the adapter opens.
        _, can, _ = unwrap(get_all())
        conn = new_connection()
        r = CanBusReceiver(can, conn, interface, channel, int(text) if text else None, **device)
        try:
            r.start()
        except Exception as e:
            conn.close()
            hint = f"\nCal: {DRIVERS[interface]}" if interface in DRIVERS else ""
            error["text"] = f"No s'ha pogut obrir {interface} canal {channel}: {e}{hint}"
            return

        set_connection(conn)
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
        r, receiver = receiver, None
        set_connected(False)
        try:
            r.stop()
        except Exception as e:
            # e.g. the adapter was unplugged; keep what was received
            message = message or str(e)
        try:
            while r.pending:
                r.flush()
            on_data()
        finally:
            status["text"] = f"Desconnectat · {counts(r)}"
            error["text"] = message

    def poll() -> None:
        nonlocal job
        job = None
        if receiver is None:
            return
        try:
            receiver.flush()
            on_data()
        except Exception as e:
            # Stop rather than keep receiving with nothing storing the frames
            disconnect(f"Error: {e}")
            return
        status["text"] = f"Connectat · {counts(receiver)}"
        if receiver.last_error is not None:
            error["text"] = f"Últim error: {receiver.last_error}"
        if receiver.running:
            job = frame.after(POLL_MS, poll)
        else:
            disconnect(f"Adaptador perdut: {receiver.bus_error}")

    def on_close() -> None:
        try:
            disconnect()
        finally:
            root.destroy()

    detect_button.configure(command=detect)
    connect_button.configure(command=connect)
    disconnect_button.configure(command=disconnect)
    root = frame.winfo_toplevel()
    root.protocol("WM_DELETE_WINDOW", on_close)
    # macOS's Quit (Cmd+Q) doesn't go through WM_DELETE_WINDOW
    root.createcommand("::tk::mac::Quit", on_close)
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