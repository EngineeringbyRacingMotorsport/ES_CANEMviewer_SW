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

# --- DEFINICIÓ DE PESTANYES ---
tabs = ["General", "Temperatures", "SDC", "HV", "LV"]

frames = {}

for tab in tabs:
    frame = tk.Frame(notebook, bg="white")
    notebook.add(frame, text=tab)
    frames[tab] = frame  # guardem referència per ús posterior

# --- TREEVIEWS GENERAL ---
titulos = ["FRONT ECU", "REAR ECU", "HVAB", "HVDB", "TSAL GREEN", "SDC RESET", "BSPD", "BMS", "IMD","INVERTER"]

general_frame = frames["General"]

# layout grid centrado
num_cols = 5  # 5 a dalt, 5 a baix

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

# --- POSICIONAMENT AUTOMÀTIC ---
for i, tree in enumerate(trees):
    row = i // num_cols
    col = i % num_cols

    tree.grid(row=row, column=col, pady=10, padx=10, sticky="nsew")

ventana.mainloop()