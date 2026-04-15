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

# --- NOTEBOOK (PESTANYES) ---
notebook = ttk.Notebook(ventana)
notebook.pack(fill="both", expand=True)

# Llista de pestanyes
llista_finestres = ["General", "Temperatures", "SDC", "HV", "LV"]

# Crear pestanyes
for nombre in llista_finestres:
    frame = tk.Frame(notebook, bg="white")
    notebook.add(frame, text=nombre)

ventana.mainloop()