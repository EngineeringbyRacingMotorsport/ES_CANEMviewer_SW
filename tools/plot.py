"""
Plots the signals of a recorded drive against time.

Run from the project root: python -m tools.plot [json_path] [data_path]

The data file is either a packet file (.cpf, as written by tools.gen_example) or a
database dump (.sqlite, as written by src.main). Select signals in the tree on the
left to plot them; hold Ctrl or Shift to select several.
"""

import os
import sqlite3
import sys
import tkinter as tk
from tkinter import filedialog, messagebox

import ttkbootstrap as ttk
from matplotlib.axes import Axes
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure

from src.can import read_file
from src.schema import TIMESTAMP_COLUMN, Schema, Signal, get_all, quote_ident
from src.utils import read_text_file, unwrap

Series = tuple[list[float], list[float]]


def load_data(json_path: str, data_path: str) -> tuple[Schema, sqlite3.Connection]:
    if os.path.splitext(data_path)[1].lower() == ".sqlite":
        schema = Schema.model_validate_json(read_text_file(json_path))
        # Copied to memory, so the file isn't kept open or modified
        conn = sqlite3.connect(":memory:")
        with open(data_path, "rb") as f:
            conn.deserialize(f.read())
    else:
        schema, _, conn = unwrap(get_all(json_path))
        read_file(data_path)
    return (schema, conn)


def read_series(conn: sqlite3.Connection, message: str, signal: str) -> Series:
    """Timestamps (in seconds) and values of a signal, skipping the frames where a
    multiplexed signal isn't present"""
    rows = conn.execute(
        f"SELECT {quote_ident(TIMESTAMP_COLUMN)}, {quote_ident(signal)} "
        f"FROM {quote_ident(message)} WHERE {quote_ident(signal)} IS NOT NULL "
        f"ORDER BY {quote_ident(TIMESTAMP_COLUMN)}"
    ).fetchall()
    return ([t / 1000 for t, _ in rows], [v for _, v in rows])


def is_discrete(signal: Signal) -> bool:
    """Whether the signal holds states rather than a measurement"""
    return signal.Length == 1 or signal.Multiplexer or bool(signal.Choices)


class PlotApp:
    def __init__(self, root: ttk.Window, json_path: str) -> None:
        self.root = root
        self.json_path = json_path
        self.schema: Schema | None = None
        self.conn: sqlite3.Connection | None = None
        self.counts: dict[str, int] = {}  # rows per message
        self.cache: dict[tuple[str, str], Series] = {}
        # Plotted signals as "message.signal", kept while the filter hides them
        self.plotted: list[str] = []

        root.title("CANEM Plot")
        root.geometry("1400x800")

        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=5, pady=5)

        # Signal browser
        side = ttk.Frame(paned, padding=5)
        paned.add(side, weight=0)

        top = ttk.Frame(side)
        top.pack(fill="x")
        ttk.Button(top, text="Open…", command=self.open_dialog).pack(side="left")
        ttk.Button(
            top, text="Clear", bootstyle="secondary", command=self.clear_selection
        ).pack(side="left", padx=5)
        self.separate = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            top,
            text="Separate plots",
            variable=self.separate,
            bootstyle="round-toggle",
            command=self.redraw,
        ).pack(side="right")

        self.filter = tk.StringVar()
        self.filter.trace_add("write", lambda *_: self.populate())
        entry = ttk.Entry(side, textvariable=self.filter)
        entry.pack(fill="x", pady=5)

        tree_frame = ttk.Frame(side)
        tree_frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            tree_frame, columns=("unit", "samples"), selectmode="extended"
        )
        self.tree.heading("#0", text="Signal", anchor="w")
        self.tree.heading("unit", text="Unit", anchor="w")
        self.tree.heading("samples", text="Samples", anchor="e")
        self.tree.column("#0", width=260)
        self.tree.column("unit", width=60)
        self.tree.column("samples", width=70, anchor="e")
        scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _: self.on_select())

        self.status = ttk.Label(side, text="", bootstyle="secondary")
        self.status.pack(fill="x", pady=(5, 0))

        # Plot area
        plot = ttk.Frame(paned)
        paned.add(plot, weight=1)
        self.figure = Figure(layout="constrained")
        self.canvas = FigureCanvasTkAgg(self.figure, master=plot)
        NavigationToolbar2Tk(self.canvas, plot).update()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        self.redraw()

    def open(self, data_path: str) -> None:
        if self.conn is not None:
            self.conn.close()
        self.schema, self.conn = load_data(self.json_path, data_path)
        self.cache.clear()
        self.plotted.clear()
        self.counts = {
            name: self.conn.execute(f"SELECT COUNT(*) FROM {quote_ident(name)}").fetchone()[0]
            for name in self.schema.Messages
        }
        self.root.title(f"CANEM Plot - {os.path.basename(data_path)}")
        self.status.configure(
            text=f"{sum(self.counts.values())} frames in {sum(1 for c in self.counts.values() if c)} messages"
        )
        self.populate()

    def open_dialog(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.root,
            filetypes=[
                ("Recorded data", "*.cpf *.sqlite"),
                ("Packet files", "*.cpf"),
                ("SQLite databases", "*.sqlite"),
            ],
        )
        if not path:
            return
        try:
            self.open(path)
        except Exception as e:
            messagebox.showerror("Open failed", str(e), parent=self.root)

    ## Fill the tree with the signals matching the filter
    def populate(self) -> None:
        self.tree.delete(*self.tree.get_children())
        if self.schema is None:
            return

        query = self.filter.get().strip().lower()
        for name, message in self.schema.Messages.items():
            message_match = query in name.lower()
            signals = [
                (signal_name, signal)
                for signal_name, signal in message.Signals.items()
                if message_match or query in signal_name.lower()
            ]
            if not signals:
                continue

            count = self.counts.get(name, 0)
            self.tree.insert(
                "", "end", iid=name, text=name, values=("", count), open=bool(query)
            )
            for signal_name, signal in signals:
                iid = f"{name}.{signal_name}"
                self.tree.insert(
                    name, "end", iid=iid, text=signal_name, values=(signal.Unit, "")
                )
                if iid in self.plotted:
                    self.tree.selection_add(iid)

    def on_select(self) -> None:
        # Message rows aren't plotted
        selected = [iid for iid in self.tree.selection() if self.tree.parent(iid)]
        hidden = [iid for iid in self.plotted if not self.tree.exists(iid)]
        kept = [iid for iid in self.plotted if iid in selected or iid in hidden]
        plotted = kept + [iid for iid in selected if iid not in kept]
        if plotted != self.plotted:
            self.plotted = plotted
            self.redraw()

    def clear_selection(self) -> None:
        self.plotted.clear()
        self.tree.selection_remove(*self.tree.selection())
        self.redraw()

    def selected_signals(self) -> list[tuple[str, str, Signal]]:
        if self.schema is None:
            return []
        result: list[tuple[str, str, Signal]] = []
        for iid in self.plotted:
            message, signal_name = iid.split(".", 1)
            signal = self.schema.Messages[message].Signals[signal_name]
            result.append((message, signal_name, signal))
        return result

    def series(self, message: str, signal: str) -> Series:
        key = (message, signal)
        if key not in self.cache:
            self.cache[key] = read_series(unwrap(self.conn), message, signal)
        return self.cache[key]

    def redraw(self) -> None:
        self.figure.clear()
        selected = self.selected_signals()
        if not selected:
            ax = self.figure.add_subplot()
            ax.set_axis_off()
            ax.text(
                0.5,
                0.5,
                "Select signals to plot" if self.schema else "Open a data file",
                ha="center",
                va="center",
                color="gray",
                transform=ax.transAxes,
            )
            self.canvas.draw_idle()
            return

        if self.separate.get():
            axes = self.figure.subplots(len(selected), 1, sharex=True, squeeze=False)
            for ax, (message, name, signal) in zip(axes[:, 0], selected):
                self.plot_signal(ax, message, name, signal)
                ax.set_ylabel(f"{name}\n[{signal.Unit}]" if signal.Unit else name)
                self.label_choices(ax, signal)
            axes[-1, 0].set_xlabel("Time [s]")
        else:
            ax = self.figure.add_subplot()
            for message, name, signal in selected:
                self.plot_signal(ax, message, name, signal)
            units = sorted({signal.Unit for _, _, signal in selected if signal.Unit})
            ax.set_ylabel(", ".join(units))
            ax.set_xlabel("Time [s]")
            ax.legend(loc="upper right", fontsize="small")
            if len(selected) == 1:
                self.label_choices(ax, selected[0][2])

        self.canvas.draw_idle()

    def plot_signal(self, ax: Axes, message: str, name: str, signal: Signal) -> None:
        times, values = self.series(message, name)
        label = f"{name} [{signal.Unit}]" if signal.Unit else name
        if is_discrete(signal):
            ax.step(times, values, where="post", label=label)
        else:
            ax.plot(times, values, linewidth=1, label=label)
        ax.grid(True, alpha=0.3)
        if not times:
            ax.text(
                0.5,
                0.5,
                f"No data for {message}",
                ha="center",
                va="center",
                color="gray",
                transform=ax.transAxes,
            )

    @staticmethod
    def label_choices(ax: Axes, signal: Signal) -> None:
        if not signal.Choices:
            return
        # Physical value of each raw choice, as stored in the database
        ticks = {raw * signal.Factor + signal.Offset: text for raw, text in signal.Choices.items()}
        ax.set_yticks(list(ticks), list(ticks.values()))


def main(json_path: str, data_path: str | None) -> None:
    root = ttk.Window(themename="bootstrap-light")
    app = PlotApp(root, json_path)
    if data_path is not None:
        try:
            app.open(data_path)
        except FileNotFoundError:
            messagebox.showwarning(
                "File not found",
                f"{data_path} doesn't exist. Generate it with 'just gen-example', or "
                "open another file.",
                parent=root,
            )
    root.mainloop()


if __name__ == "__main__":
    main(
        sys.argv[1] if len(sys.argv) > 1 else "EMXCAN.json",
        sys.argv[2] if len(sys.argv) > 2 else "example.cpf",
    )
