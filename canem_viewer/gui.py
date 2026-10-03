import tkinter as tk
from tkinter import ttk

from .json import parse_schema

def tab_selected(event):
    notebook = event.widget
    page_id = notebook.select()
    page = notebook.nametowidget(page_id)
    title = notebook.tab(page_id, "text")

    print(title)

    if title == "Traffic light":
        for child in page.winfo_children():
            child.destroy()
        build_trafficlight(page)

def build_trafficlight(frame):
    lightframe = ttk.Frame(frame)
    lightframe.pack(pady=20)

    for signal in dict_signals:
        label = ttk.Label(lightframe, text=signal)
        label.pack()

root = tk.Tk()
root.title("CANEM Viewer")
root.geometry("800x600")

mainmenu = {"Visualitzar":("Traffic light", "Gràfics", "BMS", "SDC", "Dinàmica"), "Configuració":("Connectar", "Editar fitxers")}

primarytab = ttk.Notebook(root)
primarytab.pack(fill="both", expand=True, padx=10, pady=10)
tab_widgets = {
    "primary_notebook": primarytab,
    "primary_tabs": {},
    "secondary_notebooks": {},
    "secondary_tabs": {},
}

for menu, submenus in mainmenu.items():
    menu_frame = ttk.Frame(primarytab)
    primarytab.add(menu_frame, text=menu)
    tab_widgets["primary_tabs"][menu] = menu_frame

    subtab = ttk.Notebook(menu_frame)
    subtab.pack(fill="both", expand=True, padx=5, pady=5)
    tab_widgets["secondary_notebooks"][menu] = subtab
    tab_widgets["secondary_tabs"][menu] = {}

    for sub in submenus:
        subtab_frame = ttk.Frame(subtab)
        subtab.add(subtab_frame, text=sub)
        tab_widgets["secondary_tabs"][menu][sub] = subtab_frame

dict_signals = parse_schema("EMXDATA.json").model_dump()

for notebook in tab_widgets["secondary_notebooks"].values():
    notebook.bind("<<NotebookTabChanged>>", tab_selected)

# build_trafficlight(subtab_notebooks["Visualitzar"].winfo_children()[0])  # Build traffic light in the first subtab of "Visualitzar"

root.mainloop()

