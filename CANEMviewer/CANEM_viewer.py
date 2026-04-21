import tkinter as tk
from tkinter import ttk

ventana = tk.Tk()
ventana.title("CANEM VIEWER")
ventana.geometry("1400x800")
ventana.resizable(False, False)
ventana.configure(bg="#DDD")

# --- ESTIL ---
style = ttk.Style()
style.theme_use("clam")  # Important per poder modificar colors

# Configuració general del Notebook
style.configure("TNotebook", background="#DDD", borderwidth=0)

# Configuració de les pestanyes
style.configure(
    "TNotebook.Tab",
    font=("Arial", 11, "bold"),
    background="#CCC",
)

# Comportament segons estat
style.map(
    "TNotebook.Tab",
    background=[("selected", "white"), ("!selected", "#CCC")],
    foreground=[("selected", "#0a594d"), ("!selected", "black")],
)

# --- NOTEBOOK ---
notebook = ttk.Notebook(ventana)
notebook.pack(fill="both", expand=True)

# --- PESTAÑAS ---
general_frame = tk.Frame(notebook, bg="white")
temperatures_frame = tk.Frame(notebook, bg="white")
sdc_frame = tk.Frame(notebook, bg="white")
hv_frame = tk.Frame(notebook, bg="white")
lv_frame = tk.Frame(notebook, bg="white")

notebook.add(general_frame, text="General")
notebook.add(temperatures_frame, text="Temperatures")
notebook.add(sdc_frame, text="SDC")
notebook.add(hv_frame, text="HV")
notebook.add(lv_frame, text="LV")

# --- TREEVIEWS GENERAL ---
titulos = ["REAR ECU", "HVAB", "HVDB", "TSAL GREEN", "SDC RESET"]

# layout grid centrado
for col in range(6):
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
    tree.column(titulo, width=160, anchor="center")

    trees.append(tree)

# --- POSICIÓN (2 arriba / 3 abajo) ---

# arriba
trees[0].grid(row=0, column=2, pady=40)
trees[1].grid(row=0, column=4, pady=40)

# abajo
trees[2].grid(row=1, column=1, pady=40)
trees[3].grid(row=1, column=3, pady=40)
trees[4].grid(row=1, column=5, pady=40)

ventana.mainloop()