from datetime import datetime
from pathlib import Path
import os
import sqlite3
import time

import tkinter as tk
import ttkbootstrap as ttk
from tkinter import filedialog, messagebox
from .can import DRIVERS, CanBusReceiver, Loaded, detect_channels, read_recording, supported_interfaces
from .schema import (
    Schema,
    Signal,
    get_all,
    get_schema,
    load_database,
    new_connection,
    quote_ident,
    set_connection,
)
from .state import (
    Phase,
    State,
    get_last_samples,
    get_latest_state,
    get_latest_times,
    get_newest_time,
    get_oldest_time,
    get_phase,
    get_phase_changes,
    get_samples_between,
)
from .utils import unwrap
from can.typechecking import AutoDetectedConfig
from collections.abc import Callable
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

POLL_MS = 200
STATE_COLOURS = {State.OK: "lightgreen", State.WARNING: "#FFE08A", State.CRITICAL: "#FF8A80"}
NO_DATA_COLOUR = "#E0E0E0"
PHASE_NAMES = {Phase.I: "INIT", Phase.P: "PRE", Phase.T: "TS", Phase.R: "R2D"}
# TSAL light: green when the TSAL says it's safe, red when HVDB sees high voltage
TSAL_GREEN = ("TSALGreen", "TpINTled")
TSAL_RED = ("HVDB", "DpTHRhv")
TSAL_COLOURS = {"green": STATE_COLOURS[State.OK], "red": STATE_COLOURS[State.CRITICAL], "off": "#D0D0D0"}
BAR_FONT = ("TkDefaultFont", 10, "bold")  # TSAL light and phase squares
# Values shown beside the Traffic light grid, as (message, signal)
KEY_VALUES = [
    ("FrontECU_M2", "FpDIGvel"),
    ("FrontECU_M1", "FpDIGRpot"),
    ("FrontECU_M1", "FpDIGLpot"),
    ("FrontECU_M1", "FpANLbrake"),
    ("IMD_Info_Voltage", "imdHVsystvolt"),
    ("IMD_Info_IsolationDetail", "imdRisooriginal"),
    ("InverterTX", "iRPM"),
    ("InverterTX", "iTmot"),
]

ICONS_DIR = Path(__file__).parent / "icons"
SCHEMA_PATH = "EMXCAN.json"

# Time (ms) every page shows. None shows the newest data (CAN); in Datalogger
# mode the timeline sets it.
view_time: int | None = None


def current_time() -> int | None:
    """Time shown by every page, None while there's no data"""
    return view_time if view_time is not None else get_newest_time()


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
        """Colours each signal by its state at the time shown, in that time's phase"""
        phase = get_phase(view_time) or Phase.I
        for message, message_labels in labels.items():
            states = get_latest_state(phase, message, view_time)
            for signal, label in message_labels.items():
                state = states.get(signal)
                label.configure(background=STATE_COLOURS[state[1]] if state else NO_DATA_COLOUR)
        refresh_values()
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

    # Key values beside the grid, at the time shown
    values_frame = ttk.Frame(grid_view, borderwidth=2, relief="ridge", padding=(8, 4))
    values_frame.pack(pady=5, padx=5, anchor="nw", side="left")
    value_labels: dict[tuple[str, str], ttk.Label] = {}
    for message, name in KEY_VALUES:
        ttk.Label(values_frame, text=name, font=("TkDefaultFont", 9), foreground="#707070").pack(anchor="w", pady=(4, 0))
        value_labels[(message, name)] = ttk.Label(values_frame, font=("TkDefaultFont", 12, "bold"), width=11)
        value_labels[(message, name)].pack(anchor="w")

    def refresh_values() -> None:
        for (message, name), label in value_labels.items():
            sample = get_last_samples(message, name, 1, view_time)
            if not sample:
                label["text"] = "—"
                continue
            value = sample[0][1]
            unit = schema.Messages[message].Signals[name].Unit
            label["text"] = f"{value if isinstance(value, int) else f'{value:.1f}'} {unit or ''}".strip()

    refresh()
    return refresh


def clickable(widget: tk.Widget, command: Callable[[], None]) -> None:
    widget.configure(cursor="hand2")
    widget.bind("<Button-1>", lambda _: command())


def format_value(signal: Signal, value: int | float) -> str:
    # Integers in full; floats without the noise of their binary representation
    text = str(value) if isinstance(value, int) else f"{value:.10g}"
    choices = signal.choice_labels()
    if value in choices:
        text += f" ({choices[value]})"
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

    # Messages without signals have nothing to show
    messages = {message: signals_in_message for message, signals_in_message in messages.items() if signals_in_message}
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
            # Typed values aren't bound by the spinbox's range
            limit = min(5000, max(1, int(count.get())))
        except ValueError:
            limit = 200
        samples = get_last_samples(message, signal, limit, view_time)
        line.set_data([t / 1000 for t, _ in samples], [v for _, v in samples])
        unit = schema.Messages[message].Signals[signal].Unit
        axes.set_title(signal)
        axes.set_ylabel(unit)
        # Both axes follow the samples shown
        axes.relim()
        axes.autoscale_view()
        canvas.draw_idle()

    def refresh() -> None:
        phase = get_phase(view_time) or Phase.I
        newest = current_time()
        for message, tree in tables.items():
            signals = schema.Messages[message].Signals
            states = get_latest_state(phase, message, view_time)
            times = get_latest_times(message, view_time)
            for signal in tree.get_children():
                unit = signals[signal].Unit
                if signal in states and newest is not None:
                    value, state = states[signal]
                    tree.item(signal, values=(format_value(signals[signal], value), unit, newest - times[signal]), tags=(state.name,))
                else:
                    tree.item(signal, values=("—", unit, "—"), tags=("none",))
        draw()

    if selected is None and messages:
        first_message = next(iter(messages))
        selected = (first_message, messages[first_message][0])
    if selected is not None:
        message, signal = selected
        tables[message].selection_set(signal)
        tables[message].see(signal)
        graphed[:] = [(message, signal)]
    refresh()
    return {"refresh": refresh, "close": view.destroy}

## Grid position (row, column) of each graph shown, per layout button icon
GRAPH_LAYOUTS = {
    "square.svg": [(0, 0)],
    "rows-2.svg": [(0, 0), (1, 0)],
    "columns-2.svg": [(0, 0), (0, 1)],
    "grid-2x2.svg": [(0, 0), (0, 1), (1, 0), (1, 1)],
}


class Graph:
    """One graph of the Gràfics page, with the signals it shows"""

    def __init__(
        self, parent: tk.Widget, number: int, on_click: Callable[[], None], on_change: Callable[[], None]
    ) -> None:
        self.on_change = on_change  # redraws the values after the signals change
        self.box = ttk.Labelframe(parent, text=f"Gràfic {number}", padding=4)
        self.tags = ttk.Frame(self.box)
        self.tags.pack(fill="x")
        # Small requested size: the graph grows to fill its cell, never past it.
        # No layout engine: it nearly doubles the time of every redraw, so the
        # margins are fixed in pixels instead.
        self.figure = Figure(figsize=(3, 2))
        self.axes = self.figure.add_subplot()
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.box)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.mpl_connect("resize_event", lambda _: self.fit_margins())
        self.signals: list[tuple[str, str]] = []  # (message, signal)
        self.lines: list = []
        self.drawn: tuple[int, int, int] | None = None  # (start, end, newest) last drawn
        for widget in (self.box, self.canvas.get_tk_widget()):
            widget.bind("<Button-1>", lambda _: on_click(), add="+")
        self.rebuild()

    def add(self, message: str, signal: str) -> None:
        if (message, signal) not in self.signals:
            self.signals.append((message, signal))
            self.rebuild()
            self.on_change()

    def remove(self, key: tuple[str, str]) -> None:
        self.signals.remove(key)
        self.rebuild()
        self.on_change()

    def fit_margins(self) -> None:
        # Margins in screen points, so they hold at any display scaling
        width, height = self.figure.get_size_inches() * 72
        if width > 120 and height > 80:
            self.figure.subplots_adjust(left=55 / width, right=1 - 8 / width, top=1 - 8 / height, bottom=38 / height)

    def rebuild(self) -> None:
        """Lines, tags and axes for the current signals; values come in draw()"""
        schema = unwrap(get_schema())
        self.drawn = None
        for tag in self.tags.winfo_children():
            tag.destroy()
        self.axes.clear()
        self.axes.grid(True, alpha=0.3)
        self.axes.set_xlabel("Temps (s)")
        self.lines = []
        if not self.signals:
            self.axes.text(0.5, 0.5, "Tria el gràfic i fes doble clic en un senyal", ha="center",
                           va="center", color="gray", transform=self.axes.transAxes)
            self.canvas.draw_idle()
            return

        units: list[str] = []
        for message, name in self.signals:
            signal = schema.Messages[message].Signals[name]
            label = f"{name} [{signal.Unit}]" if signal.Unit else name
            (line,) = self.axes.plot([], [], linewidth=1, label=label,
                                     drawstyle="steps-post" if signal.discrete else "default")
            self.lines.append(line)
            if signal.Unit and signal.Unit not in units:
                units.append(signal.Unit)
            ttk.Button(self.tags, text=f"{name} ✕", bootstyle="secondary-outline", padding=(4, 0),
                       cursor="hand2", command=lambda key=(message, name): self.remove(key)).pack(side="left", padx=2)
        self.axes.set_ylabel(", ".join(units))
        self.axes.legend(loc="upper left", fontsize="small")
        if len(self.signals) == 1:
            # A single labelled signal shows its labels (e.g. the phase I/P/T/R)
            labels = schema.Messages[self.signals[0][0]].Signals[self.signals[0][1]].choice_labels()
            if labels:
                self.axes.set_yticks(list(labels), list(labels.values()))
        self.canvas.draw_idle()

    def draw(self, start: int, end: int, newest: int) -> None:
        """Values from `start` to `end` (ms); `newest` is the newest frame stored,
        so nothing is redrawn while neither the window nor the data changed"""
        if not self.signals or self.drawn == (start, end, newest):
            return
        self.drawn = (start, end, newest)
        for (message, signal), line in zip(self.signals, self.lines):
            samples = get_samples_between(message, signal, start, end)
            line.set_data([t / 1000 for t, _ in samples], [v for _, v in samples])
        self.axes.set_xlim(start / 1000, end / 1000)
        # The y axis fits the values shown
        self.axes.relim()
        self.axes.autoscale_view(scalex=False)
        # Drawn now rather than when idle, so the caller can time it
        self.canvas.draw()


PLAYBACK_SPEEDS = ("0.5×", "1×", "2×", "5×", "10×")
PHASE_COLOURS = {Phase.I: "#D9D9D9", Phase.P: "#FFE08A", Phase.T: "#FFB38A", Phase.R: "#A8E6A1"}
UNKNOWN_PHASE_COLOUR = "#FFFFFF"
TIMELINE_HEIGHT = 34
TIMELINE_PAD = 8  # px left and right of the box, so the cursor shows at both ends


def parse_time(text: str) -> int | None:
    """ms from "mm:ss.s" or plain seconds, None if it's neither"""
    try:
        minutes, _, seconds = text.strip().rpartition(":")
        ms = round((int(minutes or 0) * 60 + float(seconds)) * 1000)
    except ValueError:
        return None
    return ms if ms >= 0 else None


def build_timeline(parent_frame) -> None:
    """Datalogger timeline: every page shows the moment it's set to. Greyed out
    without a file."""
    bar = ttk.Frame(parent_frame)
    bar.pack(fill="x")
    start_button = ttk.Button(bar, text="⏮", width=3, cursor="hand2", command=lambda: playback.seek(source.start))
    start_button.pack(side="left")
    play_button = ttk.Button(bar, text="▶", width=3, cursor="hand2", command=lambda: playback.play(not playback.playing))
    play_button.pack(side="left", padx=5)
    speed = ttk.Combobox(bar, values=PLAYBACK_SPEEDS, state="readonly", width=5)
    speed.set("1×")
    speed.pack(side="left")
    speed.bind("<<ComboboxSelected>>", lambda _: playback.set_speed(speed.get()))

    # Right: the editable current time and the total
    total = ttk.Label(bar, text="/ --:--.-", width=9)
    total.pack(side="right")
    entry = ttk.Entry(bar, width=8, justify="right")
    entry.pack(side="right", padx=(10, 4))

    box = tk.Canvas(bar, height=TIMELINE_HEIGHT, highlightthickness=0, background="white", cursor="hand2")
    box.pack(side="left", fill="x", expand=True, padx=10)

    def x_of(t: int) -> float:
        width = box.winfo_width() - 2 * TIMELINE_PAD
        return TIMELINE_PAD + (t - source.start) / max(source.end - source.start, 1) * width

    def time_at(x: float) -> int:
        width = max(box.winfo_width() - 2 * TIMELINE_PAD, 1)
        return round(source.start + (x - TIMELINE_PAD) / width * (source.end - source.start))

    def draw(*_: object) -> None:
        """Phases, minute and 10 s lines, restarts and the box; the cursor is
        moved by show()"""
        box.delete("all")
        height = TIMELINE_HEIGHT
        active = source.kind == "Datalogger"
        if active:
            changes = playback.phases
            for i, (t, phase) in enumerate(changes):
                end = changes[i + 1][0] if i + 1 < len(changes) else source.end
                box.create_rectangle(x_of(t), 0, x_of(end), height,
                                     fill=PHASE_COLOURS.get(phase, UNKNOWN_PHASE_COLOUR), width=0)
            # Lines every 10 s from the start of the recording, darker each minute
            for ms in range(0, source.end - source.start + 1, 10_000):
                x = x_of(source.start + ms)
                if ms % 60_000:
                    box.create_line(x, height * 0.55, x, height, fill="#9A9A9A")
                else:
                    box.create_line(x, 0, x, height, fill="#404040")
                    if ms:
                        box.create_text(x + 3, 2, text=f"{ms // 60_000}:00", anchor="nw", font=("TkDefaultFont", 7))
            for restart in source.restarts:
                box.create_line(x_of(restart), 0, x_of(restart), height, fill="red", width=2, dash=(3, 2))
        box.create_rectangle(TIMELINE_PAD, 0, box.winfo_width() - TIMELINE_PAD, height - 1,
                             outline="#808080" if active else "#C8C8C8")
        box.create_line(0, 0, 0, height, fill="#1F3A93", width=3, tags="cursor", state="hidden")
        show()

    def show() -> None:
        """Puts the cursor, the time and the buttons where playback is"""
        active = source.kind == "Datalogger" and view_time is not None
        for widget in (start_button, play_button, entry):
            widget.configure(state="normal" if active else "disabled")
        speed.configure(state="readonly" if active else "disabled")
        play_button.configure(text="⏸" if playback.playing else "▶")
        speed.set(playback.speed_text)
        if not active:
            box.itemconfigure("cursor", state="hidden")
            total["text"] = "/ --:--.-"
            entry.delete(0, "end")
            return
        x = x_of(view_time)
        box.coords("cursor", x, 0, x, TIMELINE_HEIGHT)
        box.itemconfigure("cursor", state="normal")
        total["text"] = f"/ {format_time(source.end - source.start)}"
        # Not while the user is typing a time in it
        if entry.focus_get() is not entry:
            entry.delete(0, "end")
            entry.insert(0, format_time(view_time - source.start))

    def typed(_: tk.Event) -> None:
        ms = parse_time(entry.get())
        if ms is None or source.kind != "Datalogger":
            entry.configure(bootstyle="danger")
            return
        entry.configure(bootstyle="default")
        box.focus_set()  # leaves the entry, so it shows the time set
        playback.seek(source.start + ms)

    def pressed(event: tk.Event) -> None:
        if source.kind == "Datalogger":
            playback.seek(time_at(event.x))

    entry.bind("<Return>", typed)
    entry.bind("<KP_Enter>", typed)
    entry.bind("<Escape>", lambda _: (box.focus_set(), show()))
    box.bind("<ButtonPress-1>", pressed)
    box.bind("<B1-Motion>", pressed)
    box.bind("<Configure>", draw)
    playback.views.append((draw, show))


class Playback:
    """Datalogger playback, shared by every timeline"""

    def __init__(self) -> None:
        self.playing = False
        self.speed_text = "1×"
        self.last_tick = 0.0  # monotonic time of the last step forward
        self.phases: list[tuple[int, Phase | None]] = []  # the recording's phase changes
        self.views: list[tuple[Callable[[], None], Callable[[], None]]] = []  # (redraw all, show time)

    def show(self) -> None:
        for _, show in self.views:
            show()

    def seek(self, ms: int) -> None:
        global view_time
        if source.kind != "Datalogger":
            return
        view_time = min(max(ms, source.start), source.end)
        self.show()

    def play(self, on: bool) -> None:
        if on and view_time is not None and view_time >= source.end:
            self.seek(source.start)  # playing again from the end starts over
        self.playing = on and source.kind == "Datalogger"
        self.last_tick = time.monotonic()
        self.show()

    def set_speed(self, text: str) -> None:
        self.speed_text = text
        self.show()

    def advance(self) -> None:
        """Moves the time on while playing; run by the app's timer"""
        if not self.playing or view_time is None:
            return
        now = time.monotonic()
        step = int((now - self.last_tick) * 1000 * float(self.speed_text.rstrip("×")))
        self.last_tick = now
        self.seek(view_time + step)
        if view_time >= source.end:
            self.play(False)  # stops at the end

    def changed(self) -> None:
        """A new source: stop, and redraw the timelines for it"""
        self.playing = False
        self.phases = get_phase_changes() if source.kind == "Datalogger" else []
        for draw, _ in self.views:
            draw()


def build_grafics(parent_frame, signals: dict[str, dict[str, list[str]]]) -> Callable[[], None]:
    """Fins a 4 gràfics amb els senyals triats a l'arbre de l'esquerra.
    Returns the function that redraws them."""
    schema = unwrap(get_schema())

    top = ttk.Frame(parent_frame)
    top.pack(fill="x", padx=5, pady=5)
    left =ttk.Frame(parent_frame)
    left.pack(side="left", fill="y", padx=5, pady=(0, 5))
    area = ttk.Frame(parent_frame)
    area.pack(side="left", fill="both", expand=True, padx=(0, 5), pady=(0, 5))

    graphs: list[Graph] = []
    active = [0]  # index of the graph signals are added to

    def activate(index: int) -> None:
        active[0] = index
        for i, graph in enumerate(graphs):
            graph.box.configure(bootstyle="primary" if i == index else "default")

    graphs.extend(Graph(area, i + 1, lambda i=i: activate(i), lambda: refresh(now=True)) for i in range(4))

    def set_layout(icon: str) -> None:
        cells = GRAPH_LAYOUTS[icon]
        for graph in graphs:
            graph.box.grid_forget()
        # Graphs left out keep their signals, so going back shows them again
        for graph, (row, column) in zip(graphs, cells):
            graph.box.grid(row=row, column=column, sticky="nsew", padx=3, pady=3)
        for i in range(2):
            area.rowconfigure(i, weight=1 if any(r == i for r, _ in cells) else 0)
            area.columnconfigure(i, weight=1 if any(c == i for _, c in cells) else 0)
        if active[0] >= len(cells):
            activate(0)
        refresh(now=True)

    for icon in GRAPH_LAYOUTS:
        image = load_svg(icon, 24)
        button = ttk.Button(top, image=image, padding=(0, 0), cursor="hand2", command=lambda icon=icon: set_layout(icon))
        button.pack(padx=5, side="left")
        button.image = image  # keep a reference, or Tk drops the image
    ttk.Label(top, text="Finestra:").pack(side="left", padx=(20, 5))
    window = ttk.Spinbox(top, from_=1, to=600, increment=5, width=5, command=lambda: refresh(now=True))
    window.set(10)
    window.pack(side="left")
    window.bind("<Return>", lambda _: refresh(now=True))
    ttk.Label(top, text="s").pack(side="left", padx=5)

    # Signal tree: node -> message -> signal, filtered by the search box
    search = tk.StringVar()
    ttk.Entry(left, textvariable=search).pack(fill="x", pady=(0, 5))
    tree = ttk.Treeview(left, columns=("unit",), selectmode="browse")
    tree.heading("#0", text="Senyal", anchor="w")
    tree.heading("unit", text="Unitat", anchor="w")
    tree.column("#0", width=230)
    tree.column("unit", width=60)
    scroll = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=scroll.set)
    tree.pack(side="left", fill="y")
    scroll.pack(side="left", fill="y")

    def populate(*_: object) -> None:
        tree.delete(*tree.get_children())
        query = search.get().strip().lower()
        for node, messages in signals.items():
            node_id = None
            for message, names in messages.items():
                matching = [n for n in names if query in n.lower() or query in message.lower() or query in node.lower()]
                if not matching:
                    continue
                if node_id is None:
                    node_id = tree.insert("", "end", text=node, open=bool(query))
                message_id = tree.insert(node_id, "end", text=message, open=bool(query))
                for name in matching:
                    tree.insert(message_id, "end", iid=f"{message}.{name}", text=name,
                                values=(schema.Messages[message].Signals[name].Unit,))

    def on_double_click(_: tk.Event) -> None:
        selection = tree.selection()
        if selection and "." in selection[0]:
            message, name = selection[0].split(".", 1)
            graphs[active[0]].add(message, name)

    search.trace_add("write", populate)
    tree.bind("<Double-1>", on_double_click)
    populate()

    paused_until = [0.0]  # monotonic time before which the timer skips redraws

    def refresh(now: bool = False) -> None:
        """Redraws the graphs; `now` for the user's own changes, which the
        timer's pacing doesn't hold back"""
        # Hidden graphs aren't redrawn, which keeps the shared timer light
        if not parent_frame.winfo_ismapped():
            return
        # Redrawing takes ~40 ms a graph, so the timer waits as long as the last
        # redraw took: the window keeps half its time for everything else
        if not now and time.monotonic() < paused_until[0]:
            return
        started = time.monotonic()
        newest = get_newest_time()
        end = view_time if view_time is not None else newest
        if end is None or newest is None:
            return
        try:
            seconds = min(600, max(1, int(window.get())))
        except ValueError:
            seconds = 10
        for graph in graphs:
            if graph.box.winfo_manager():
                graph.draw(end - seconds * 1000, end, newest)
        paused_until[0] = time.monotonic() + (time.monotonic() - started)

    # Showing the tab draws the graphs at once, without waiting for the timer
    parent_frame.bind("<Map>", lambda _: refresh(now=True), add="+")
    set_layout("grid-2x2.svg")
    activate(0)
    return refresh


class Source:
    """The data being shown: a datalogger file, or frames from a CAN adapter.
    Pages read `view_time`; the app's timer runs the tickers."""

    def __init__(self) -> None:
        self.kind: str | None = None  # "Datalogger" or "CAN"
        self.name = ""  # file name, or adapter
        self.start = 0  # Datalogger: first and last frame (ms)
        self.end = 0
        self.restarts: list[int] = []  # Datalogger: where the logger's clock restarted
        self.receiver: CanBusReceiver | None = None  # CAN: while connected
        self.bitrate: int | None = None  # CAN: as configured, None if left empty
        self.listeners: list[Callable[[], None]] = []  # told when the source changes
        self.tickers: list[Callable[[], None]] = []  # run on every tick

    def opened(self, kind: str | None, name: str = "", restarts: list[int] | None = None) -> None:
        global view_time
        self.kind, self.name, self.restarts = kind, name, restarts or []
        self.start, self.end = get_oldest_time() or 0, get_newest_time() or 0
        # A file starts at its beginning; live data always shows the newest
        view_time = self.start if kind == "Datalogger" else None
        for listener in self.listeners:
            listener()

    def label(self) -> str:
        return f"{self.kind}: {self.name}" if self.kind else "Sense dades"


source = Source()
playback = Playback()
source.tickers.append(playback.advance)
source.listeners.append(playback.changed)


def format_time(ms: int) -> str:
    """mm:ss.s"""
    # Rounded to tenths first, so 59.97 s shows as 01:00.0, not 00:60.0
    minutes, tenths = divmod(round(ms / 100), 600)
    return f"{minutes:02d}:{tenths / 10:04.1f}"


def tsal_colour(green: bool, red: bool, flash: bool) -> str:
    """TSAL light colour: red flashes, both alternate; `flash` flips every refresh"""
    if green and red:
        return TSAL_COLOURS["green" if flash else "red"]
    if red:
        return TSAL_COLOURS["red" if flash else "off"]
    return TSAL_COLOURS["green" if green else "off"]


def bus_text(samples: list[tuple[float, int, int]]) -> str:
    """Bus load and frames/s between the oldest and newest (time s, frames, bits)"""
    if source.receiver is None:
        return "CAN desconnectat"
    (t0, frames0, bits0), (t1, frames1, bits1) = samples[0], samples[-1]
    if t1 - t0 < 0.5:
        return "Càrrega: … · … trames/s"
    rate = (frames1 - frames0) / (t1 - t0)
    load = (
        f"Càrrega {100 * (bits1 - bits0) / (t1 - t0) / source.bitrate:.0f} %"
        if source.bitrate
        else "Càrrega: — (indica el bitrate)"
    )
    return f"{load} · {rate:,.0f} trames/s".replace(",", " ")


def build_bottom_bar(parent_frame) -> Callable[[], None]:
    """Bar under every Visualitzar page: the timeline (Datalogger) or the bus
    (CAN) on the left; the TSAL light and the phases on the right"""
    bar = ttk.Frame(parent_frame)
    bar.pack(side="bottom", fill="x", padx=5, pady=(0, 5))

    right = ttk.Frame(bar)
    right.pack(side="right", padx=(10, 0))
    tsal = tk.Label(right, text="TSAL LIGHT", font=BAR_FONT, foreground="black",
                    highlightthickness=1, highlightbackground="#A0A0A0")
    tsal.grid(row=0, column=0, columnspan=len(Phase), sticky="ew", padx=2, pady=(0, 3))
    squares: dict[Phase, tk.Label] = {}
    for column, phase in enumerate(Phase):
        square = tk.Label(right, text=PHASE_NAMES[phase], font=BAR_FONT, width=6, pady=6, borderwidth=1)
        square.grid(row=1, column=column, padx=2)
        squares[phase] = square

    left = ttk.Frame(bar)
    left.pack(side="left", fill="both", expand=True)
    timeline = ttk.Frame(left)
    build_timeline(timeline)
    bus = ttk.Label(left, font=("TkDefaultFont", 12, "bold"), anchor="w")
    samples: list[tuple[float, int, int]] = []  # last second of (time s, frames, bits)
    flash = [False]

    def show_mode() -> None:
        samples.clear()
        if source.kind == "CAN":
            timeline.pack_forget()
            bus.pack(fill="both", expand=True, padx=5)
        else:
            bus.pack_forget()
            timeline.pack(fill="x", expand=True, anchor="s")

    def refresh() -> None:
        now = time.monotonic()
        if source.kind == "CAN":
            r = source.receiver
            if r is not None:
                samples.append((now, r.frames_seen, r.bits_seen))
                while now - samples[0][0] > 1.0:
                    samples.pop(0)
            bus["text"] = bus_text(samples)

        current = get_phase(view_time)
        for phase, square in squares.items():
            on = phase == current
            square.configure(
                background=PHASE_COLOURS[phase] if on else "#F5F5F5",
                foreground="black" if on else "#A0A0A0",
                relief="solid" if on else "ridge",
            )
        green, red = (get_last_samples(*signal, 1, view_time) for signal in (TSAL_GREEN, TSAL_RED))
        # Flipped on every refresh, i.e. every 200 ms of the app's timer (5 Hz)
        flash[0] = not flash[0]
        colour = tsal_colour(bool(green and green[0][1] == 1), bool(red and red[0][1] == 1), flash[0])
        tsal.configure(background=colour)

    source.listeners.append(show_mode)
    show_mode()
    refresh()
    return refresh


def get_frame_count(conn: sqlite3.Connection) -> int:
    schema = unwrap(get_schema())
    return sum(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(m)}").fetchone()[0] for m in schema.Messages)


RECORDING_TYPES = [
    ("Gravacions", "*.cpf *.sqlite *.blf *.asc *.trc *.log"),
    ("Fitxers del datalogger", "*.cpf"),
    ("Bases de dades desades", "*.sqlite"),
    ("Registres CAN", "*.blf *.asc *.trc *.log"),
]


def build_sources(parent_frame):
    """Font de dades: un fitxer del datalogger o un adaptador CAN (UDP, més endavant)"""
    choice = tk.StringVar(value="Datalogger")
    choices = ttk.Frame(parent_frame)
    choices.pack(anchor="nw", padx=20, pady=(20, 0))
    panels: dict[str, ttk.Frame] = {}
    for kind in ("Datalogger", "CAN", "UDP"):
        ttk.Radiobutton(choices, text=kind, value=kind, variable=choice, command=lambda: show_panel(),
                        state="disabled" if kind == "UDP" else "normal").pack(side="left", padx=(0, 20))
        panels[kind] = ttk.Frame(parent_frame, padding=10, borderwidth=2, relief="ridge")

    def show_panel() -> None:
        for panel in panels.values():
            panel.pack_forget()
        panels[choice.get()].pack(pady=10, padx=20, anchor="nw")

    # Datalogger
    datalogger = panels["Datalogger"]
    open_button = ttk.Button(datalogger, text="Obrir fitxer…", cursor="hand2")
    open_button.grid(row=0, column=0, sticky="w")
    file_label = ttk.Label(datalogger, text="Cap fitxer obert")
    file_label.grid(row=0, column=1, sticky="w", padx=10)
    file_status = ttk.Label(datalogger, text="", wraplength=700)
    file_status.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
    file_error = ttk.Label(datalogger, text="", bootstyle="danger", wraplength=700)
    file_error.grid(row=2, column=0, columnspan=2, sticky="w")

    # CAN
    frame = panels["CAN"]
    channels: list[AutoDetectedConfig] = []
    receiver: CanBusReceiver | None = None

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

    ttk.Label(panels["UDP"], text="Encara no disponible").pack(anchor="w")

    def open_file(path: str | None = None) -> None:
        path = path or filedialog.askopenfilename(parent=parent_frame, filetypes=RECORDING_TYPES)
        if not path:
            return
        name = os.path.basename(path)
        if receiver is not None:
            if not messagebox.askyesno(
                "Obrir fitxer",
                "Obrir un fitxer desconnecta l'adaptador CAN, i les dades rebudes no es desen. Vols continuar?",
                parent=parent_frame,
            ):
                return
            disconnect()
        root.configure(cursor="watch")
        root.update_idletasks()
        conn = None
        try:
            if os.path.splitext(path)[1].lower() == ".sqlite":
                conn = load_database(path)
                loaded = Loaded(get_frame_count(conn), 0, [], None)
            else:
                conn = new_connection()
                loaded = read_recording(path, conn)
        except Exception as e:
            if conn is not None:
                conn.close()
            file_error["text"] = f"No s'ha pogut obrir {name}: {e}"
            return
        finally:
            root.configure(cursor="")
        if loaded.frames == 0:
            conn.close()
            file_error["text"] = f"{name} no té cap trama dels missatges coneguts"
            return

        # The data shown until now is only replaced once the file has loaded
        set_connection(conn)
        source.opened("Datalogger", name, loaded.restarts)
        file_label["text"] = path
        file_error["text"] = ""
        notes = [f"{loaded.frames} trames, {format_time(source.end - source.start)}"]
        if loaded.skipped:
            notes.append(f"{loaded.skipped} trames descartades (missatges desconeguts o que no es poden descodificar)")
        if loaded.restarts:
            notes.append(
                f"el rellotge del datalogger s'ha reiniciat {len(loaded.restarts)} cop(s), a "
                + ", ".join(format_time(t - source.start) for t in loaded.restarts)
            )
        if loaded.stopped:
            notes.append(f"el fitxer s'acaba abans d'hora ({loaded.stopped}); es mostra fins aquí")
        file_status["text"] = " · ".join(notes)

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
        source.receiver, source.bitrate = r, int(text) if text else None
        source.opened("CAN", adapter.get())
        file_label["text"] = "Cap fitxer obert"
        file_status["text"] = ""

    def disconnect(message: str = "") -> None:
        nonlocal receiver
        if receiver is None:
            return
        r, receiver = receiver, None
        source.receiver = None
        set_connected(False)
        try:
            r.stop()
        except Exception as e:
            # e.g. the adapter was unplugged; keep what was received
            message = message or str(e)
        try:
            while r.pending:
                r.flush()
        finally:
            status["text"] = f"Desconnectat · {counts(r)}"
            error["text"] = message

    def poll() -> None:
        """Stores what the adapter received; run by the app's timer"""
        if receiver is None:
            return
        try:
            receiver.flush()
        except Exception as e:
            # Stop rather than keep receiving with nothing storing the frames
            disconnect(f"Error: {e}")
            return
        status["text"] = f"Connectat · {counts(receiver)}"
        if receiver.last_error is not None:
            error["text"] = f"Últim error: {receiver.last_error}"
        if not receiver.running:
            disconnect(f"Adaptador perdut: {receiver.bus_error}")

    def on_close() -> None:
        try:
            disconnect()
        finally:
            root.destroy()

    open_button.configure(command=open_file)
    detect_button.configure(command=detect)
    connect_button.configure(command=connect)
    disconnect_button.configure(command=disconnect)
    source.tickers.append(poll)
    root = parent_frame.winfo_toplevel()
    root.protocol("WM_DELETE_WINDOW", on_close)
    # macOS's Quit (Cmd+Q) doesn't go through WM_DELETE_WINDOW
    root.createcommand("::tk::mac::Quit", on_close)
    show_panel()
    detect()
    return open_file


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
        "Configuració": ("Font de dades", "Editar fitxers"),
    }

    primary_notebook = ttk.Notebook(root, padding=0)
    primary_notebook.pack(fill="both", expand=True, padx=10, pady=10)
    # The data being shown, in the corner next to the menus
    source_label = ttk.Label(root, font=("TkDefaultFont", 10, "bold"))
    source_label.place(relx=1.0, x=-20, y=14, anchor="ne")

    # Construcció dinàmica del menú i submenús
    for menu_title, submenus in mainmenu.items():
        primary_frame = ttk.Frame(primary_notebook)
        primary_notebook.add(primary_frame, text=menu_title)
        if menu_title == "Visualitzar":
            # Packed before the tabs, so it stays under every page of the menu
            refresh_bottom_bar = build_bottom_bar(primary_frame)

        secondary_notebook = ttk.Notebook(primary_frame)
        secondary_notebook.pack(fill="both", expand=True, padx=5, pady=5)

        for sub_title in submenus:
            sub_frame = ttk.Frame(secondary_notebook)
            secondary_notebook.add(sub_frame, text=sub_title)

            # Assignem el contingut específic directament en crear la pestanya
            if sub_title == "Traffic light":
                refresh_trafficlight = build_trafficlight(sub_frame, dict_signals)
            if sub_title == "Gràfics":
                refresh_grafics = build_grafics(sub_frame, dict_signals)
            if sub_title == "Font de dades":
                build_sources(sub_frame)
            if sub_title == "Temperatures":
                build_temperatures(sub_frame, dict_signals)

    def refresh_pages() -> None:
        refresh_bottom_bar()
        refresh_trafficlight()
        refresh_grafics()

    def show_source() -> None:
        source_label["text"] = source.label()
        refresh_pages()

    # One timer for the whole app: it stores what the adapter received, moves
    # the timeline on while playing, then every page shows the time reached
    def tick() -> None:
        for ticker in source.tickers:
            try:
                ticker()
            except Exception as e:
                print(f"Error: {e}")
        try:
            refresh_pages()
        except Exception as e:
            print(f"Error: {e}")
        root.after(POLL_MS, tick)

    source.listeners.append(show_source)
    show_source()
    tick()
    return root


if __name__ == "__main__":
    app = create_app()
    app.mainloop()