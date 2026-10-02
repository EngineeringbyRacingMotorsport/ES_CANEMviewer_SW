import nt
import tkinter as tk
from tkinter import ttk
import pandas as pd
import cantools as ct

root = tk.Tk()
root.title("CANEM Viewer")
root.geometry("800x600")

mainmenu = {"Visualitzar":("Semafor", "Gràfics", "BMS", "SDC", "Dinàmica"), "Configuració":("Connectar", "Editar fitxers")}

mm_nb = ttk.Notebook(root)
mm_nb.pack(fill="both", expand=True, padx=10, pady=10)

for menu, submenus in mainmenu.items():
    menu_frame = ttk.Frame(mm_nb)
    mm_nb.add(menu_frame, text=menu)
    sm_nb = ttk.Notebook(menu_frame)
    sm_nb.pack(fill="both", expand=True, padx=5, pady=5)
    for sub in submenus:
        sm_nb.add(ttk.Frame(sm_nb), text=sub)

root.mainloop()