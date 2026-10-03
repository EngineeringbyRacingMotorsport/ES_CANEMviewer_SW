from datetime import datetime

import ttkbootstrap as ttk
from .json import parse_schema


def build_trafficlight(parent_frame, signals):
    """Crea els elements visuals del Traffic Light una sola vegada."""
    lightframe = ttk.Frame(parent_frame, height=700, width=1300, borderwidth=2, relief="ridge")
    lightframe.pack(pady=5, padx=5, anchor="nw", side="left", expand=False)

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
            message_frame.grid(row=row, column=1, pady=2, padx=2, sticky="ew")

            ttk.Label(message_frame, text=message, width=message_column_width, anchor="w").grid(
                row=0, column=0, pady=2, padx=2, sticky="w"
            )
            for column, signal in enumerate(signals_in_message, start=1):
                signal_frame = ttk.Frame(message_frame, borderwidth=2, relief=None)
                signal_frame.grid(row=0, column=column, pady=2, padx=2, sticky="w")
                ttk.Label(signal_frame, text=signal, padding=(5,0), background="lightgreen" ).pack(pady=0, padx=0, anchor="center")
            
    tsal_status = ttk.Frame(parent_frame, height=50, borderwidth=2, relief="ridge")
    tsal_status.pack(pady=5, padx=5, anchor="nw", side="left", expand=True, fill="x")
    ttk.Label(tsal_status, text="TSAL LIGHT", font=("TkDefaultFont", 12, "bold"), background="#FFCCCB", anchor="center", padding=(0,5)).pack(side="top", expand=True, fill="both")

    scs_signals = ttk.Frame(parent_frame, height=50, borderwidth=2, relief="ridge")
    scs_signals.pack(pady=5, padx=5, anchor="w", side="bottom", expand=True, fill="x")

    

def build_grafics(parent_frame, signals):
    """Crea els elements visuals del Gràfics una sola vegada."""
    graficsframe = ttk.Frame(parent_frame, padding=10, borderwidth=2, relief="ridge")
    graficsframe.pack(pady=20)

    for signal in signals:
        ttk.Label(graficsframe, text=signal).pack()

def create_app():
    root = ttk.Window(themename="bootstrap-light")
    root.title("CANEM Viewer")
    root.geometry("1860x1045")
    root.resizable(False, False)

    # Carrega de dades
    dict_signals = parse_schema("EMXDATA.json").model_dump()

    # Estructura de navegació
    mainmenu = {
        "Visualitzar": ("Traffic light", "Gràfics", "BMS", "SDC", "Dinàmica"),
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
                build_trafficlight(sub_frame, dict_signals)
            if sub_title == "Gràfics":
                build_grafics(sub_frame, dict_signals)

    return root


if __name__ == "__main__":
    app = create_app()
    app.mainloop()