import tkinter as tk
from tkinter import ttk

ventana = tk.Tk()
ventana.title("CANEM VIEWER")
ventana.geometry("1400x800")
ventana.resizable(False, False)
ventana.configure(bg="#DDD")

# --- ESTIL ---
style = ttk.Style()
style.theme_use("clam")

style.configure("TNotebook", background="#DDD", borderwidth=0)

style.configure(
    "TNotebook.Tab",
    font=("Arial", 11, "bold"),
    background="#CCC",
)

style.map(
    "TNotebook.Tab",
    background=[("selected", "white"), ("!selected", "#CCC")],
    foreground=[("selected", "#0a594d"), ("!selected", "black")],
)

# --- NOTEBOOK ---
notebook = ttk.Notebook(ventana)
notebook.pack(fill="both", expand=True)

# --- PESTAÑAS PRINCIPALES ---
tabs = ["General", "Temperatures", "SDC", "HV", "LV"]

frames = {}

for tab in tabs:
    frame = tk.Frame(notebook, bg="white")
    notebook.add(frame, text=tab)
    frames[tab] = frame

# --- GENERAL FRAME ---
general_frame = frames["General"]

titulos = ["FRONT ECU", "REAR ECU", "HVAB", "HVDB", "TSAL GREEN", "SDC RESET", "BSPD", "BMS", "IMD","INVERTER"]

num_cols = 5

for col in range(num_cols):
    general_frame.columnconfigure(col, weight=1)

general_frame.rowconfigure(0, weight=1)
general_frame.rowconfigure(1, weight=1)

trees = []

for titulo in titulos:
    tree = ttk.Treeview(
        general_frame,
        columns=(titulo,),
        show="headings",
        height=1
    )

    tree.heading(titulo, text=titulo)
    tree.column(titulo, width=100, stretch=True, anchor="center")

    trees.append(tree)

for i, tree in enumerate(trees):
    row = i // num_cols
    col = i % num_cols

    tree.grid(row=row, column=col, pady=10, padx=10, sticky="nsew")


detalle_frame = tk.Frame(general_frame, bg="white")
modo_detalle = False

def mostrar_detalle(titulo):
    global modo_detalle
    modo_detalle = True

    # ocultar grid principal
    for widget in general_frame.winfo_children():
        widget.grid_remove()

    # limpiar contenido anterior
    for widget in detalle_frame.winfo_children():
        widget.destroy()

    # mostrar vista detalle
    detalle_frame.place(relwidth=1, relheight=1)

    label = tk.Label(
        detalle_frame,
        text=titulo,
        font=("Arial", 18, "bold"),
        bg="white"
    )
    label.pack(pady=20)


def volver_general():
    global modo_detalle

    if not modo_detalle:
        return

    modo_detalle = False

    # ocultar detalle
    detalle_frame.place_forget()

    # restaurar grid
    for i, tree in enumerate(trees):
        row = i // num_cols
        col = i % num_cols
        tree.grid(row=row, column=col, pady=10, padx=10, sticky="nsew")


def on_tree_click(event):
    region = event.widget.identify_region(event.x, event.y)

    if region == "heading":
        col_id = event.widget.identify_column(event.x)
        col_index = int(col_id.replace("#", "")) - 1
        titulo = event.widget["columns"][col_index]

        mostrar_detalle(titulo)


def on_tab_change(event):
    selected = notebook.tab(notebook.select(), "text")

    if selected == "General":
        volver_general()


def on_tab_click(event):
    x, y = event.x, event.y
    elem = notebook.identify(x, y)

    if "label" in elem:
        index = notebook.index(f"@{x},{y}")
        tab_text = notebook.tab(index, "text")

        if tab_text == "General":
            volver_general()


for tree in trees:
    tree.bind("<Button-1>", on_tree_click)

notebook.bind("<<NotebookTabChanged>>", on_tab_change)
notebook.bind("<Button-1>", on_tab_click)

ventana.mainloop()