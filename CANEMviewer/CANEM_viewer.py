import tkinter as tk
from tkinter import ttk

ventana = tk.Tk()
ventana.title("CANEM VIEWER")
ventana.geometry("1400x800")
ventana.configure(bg="#DDD")

# --- BARRA SUPERIOR (BOTONES) ---
barra = tk.Frame(ventana, bg="#DDD")
barra.grid(row=0, column=0, sticky="ew")

# Lista con los nombres de los botones de la imagen
nombres_botones = ["FUNCIONS", "TEMPERATURES", "SDC", "HV", "LV"]

# Bucle para crear y colocar cada botón
for i, nombre in enumerate(nombres_botones):
    boton = tk.Button(
        barra, 
        text=nombre, 
        font=("Arial", 10, "bold"), 
        relief="flat",   # Sin relieve
        bd=0,            # Sin borde 
        bg="white",      
        padx=10,
        pady=5,
    )
    # padx=5 aquí añade un margen EXTERNO de 5 píxeles entre cada botón
    boton.grid(row=0, column=i, padx=5, pady=5 )
ventana.mainloop()
