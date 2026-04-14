import tkinter as tk
from tkinter import ttk
import random

# ============================
# CONFIGURACIÓN Y VARIABLES GLOBALES
# ============================
# Diccionario para guardar referencias a las pestañas abiertas y no perderlas.
pestanas_abiertas = {}

# Definición de colores hexadecimales para mantener consistencia en toda la app.
COLOR_VERDE, COLOR_AMARILLO, COLOR_ROJO = "#71FF71", "#FCEB66", "#FF7C7C"
COLOR_SOMBRA_ALERTA = "#FFDADA"  # Color de fondo suave para zonas fuera de límite en la gráfica.

# --- LÍMITES DE SENSORES (Lógica del negocio) ---
# Aquí definimos el rango aceptable para cada señal.
# Formato: "nombre_señal": (mínimo_aceptable, máximo_aceptable)
limites_senales = {
    # 1. Temperaturas y señales analógicas: 
    # Si el valor toca o supera estos límites, la función marcará ROJO.
    "temp accu": (20, 60), "temp radiadors": (20, 85), "temp inverter": (20, 80), 
    "temp inverter 2": (20, 80), "refri accu": (15, 55),
    "hv accu": (350, 580), "hv inverter": (350, 580), 
    "current sensor": (-20, 200), 
    "IMD": (100, 5000), 
    "acc1": (5, 100), "acc2": (5, 100), "fre????": (0, 100), "bms": (10, 100),
    "brake bspd": (5, 60), "BRAKE": (5, 60),
    "vcc p1": (4.8, 5.2), "vcc p2": (4.8, 5.2), 
    "gnd p1": (-0.2, 0.2), "gnd p2": (-0.2, 0.2),
    "brake bspd vcc": (11.5, 14.5), "brake bspd gnd": (-0.2, 0.2),
    "current sensor vcc": (11.5, 14.5), "current sensor gnd": (-0.2, 0.2),
    "pre board": (11.5, 14.5),

    # 2. Señales Booleanas (ON/OFF):
    # Usamos (0.5, 1.5). 
    # - Si llega un 0: 0 < 0.5 -> Fuera de rango (ROJO/MALO).
    # - Si llega un 1: 1 está entre 0.5 y 1.5 -> Dentro de rango (VERDE/OK).
    "enable": (0.5, 1.5), "sdc ok": (0.5, 1.5), "sdc": (0.5, 1.5),
    "sdc bots": (0.5, 1.5), "sdc ok state": (0.5, 1.5),
    "estat air pos": (0.5, 1.5), "estat air neg": (0.5, 1.5),
    "implau": (0.5, 1.5), "green tsal indicator": (0.5, 1.5),

    # 3. Señales de Error (Lógica inversa):
    # Usamos (-0.1, 0.5).
    # - Si llega un 0 (No hay error): 0 está entre -0.1 y 0.5 -> VERDE.
    # - Si llega un 1 (Hay error): 1 > 0.5 -> Fuera de rango (ROJO).
    "error bms": (-0.1, 0.5), "error imd": (-0.1, 0.5),
    "imd error indicator": (-0.1, 0.5), "bms error indicator": (-0.1, 0.5),
    "red tsal indicator": (-0.1, 0.5) 
}

# Diccionario para pintar la unidad al lado del valor (V, ºC, A, etc.)
unidades = {
    "temp accu": "ºC", "temp radiadors": "ºC", "temp inverter": "ºC", "temp inverter 2": "ºC", "refri accu": "ºC",
    "hv accu": "V", "hv inverter": "V", "sdc": "V", "sdc bots": "V", "pre board": "V",
    "estat air pos": "St", "estat air neg": "St", "estat rele prechar": "St",
    "intencional air pos": "St", "intencional air neg": "St", "intencional pre": "St",
    "vcc p1": "V", "vcc p2": "V", "gnd p1": "V", "gnd p2": "V",
    "brake bspd gnd": "V", "brake bspd vcc": "V", "current sensor gnd": "V", "current sensor vcc": "V",
    "green tsal indicator": "St", "red tsal indicator": "St", "imd error indicator": "St", "bms error indicator": "St",
    "current sensor": "A", "IMD": "kΩ", "brake bspd": "bar", "BRAKE": "bar",
    "acc1": "%", "acc2": "%", "fre????": "%", "bms": "%", "DATALOGGER": "pts",
    "error bms": "err", "error imd": "err", "sdc ok state": "st", "sdc ok": "st",
    "sdc reset button": "st", "latch descarrega": "st", "enable": "st", 
    "implau": "st", "reset": "st", "butt ts": "st", "butt r2d": "st", "buzzer": "st"
}

# Textos de ayuda que aparecen abajo a la derecha al seleccionar una señal.
explicaciones = {s: f"Descripción técnica de {s}. Monitorización en tiempo real." for s in unidades}

# Agrupaciones para la barra superior (botones de categorías).
categorias = {
    "TEMPERATURES": ["temp accu", "temp radiadors", "temp inverter", "temp inverter 2", "refri accu"],
    "SDC": ["sdc", "sdc bots", "sdc ok state", "sdc ok", "sdc reset button", "latch descarrega"],
    "HV": ["hv accu", "hv inverter", "current sensor", "IMD"],
    "LV": ["vcc p1", "vcc p2", "gnd p1", "gnd p2", "enable"],
    "CANDA": ["DATALOGGER", "butt ts", "butt r2d", "buzzer"]
}

# Agrupaciones para los módulos del panel principal (las cajas grises).
modulos_senales = {
    "R2D":["estat air pos","sdc","butt ts","butt r2d","buzzer","enable","BRAKE"],
    "APPS":["fre????","acc1","acc2","sdc","gnd p1","gnd p2","vcc p1","vcc p2","implau","enable","reset"],
    "DATALOGGER":["DATALOGGER"], "BOTS":["sdc bots"], "BMS":["bms"], "ACCU ECU":["refri accu","temp accu"],
    "TSAL GREEN":["estat air pos","estat air neg","hv accu","green tsal indicator"],
    "IMD":["IMD"], "SDC RESET":["error bms","error imd","sdc ok state","sdc reset button"],
    "TSAL GREEN HV":["hv accu"], "PRE BOARD":["pre board"],
    "BSPD":["brake bspd","current sensor","sdc ok"],
    "TSAL RED":["hv inverter","red tsal indicator"], "CIRC DES":["latch descarrega"], "CONT INVERT":["acc1","sdc","enable"],
    "TEMP REFRI REAR":["temp radiadors"], "TEMP INV":["temp inverter", "temp inverter 2"], "CONT BR LIGHT":["BRAKE"]
}

# --- GENERADOR DE DATOS SIMULADOS ---
# Esta función sustituye la lectura real del CAN BUS.
# Genera una lista de 30 valores para dibujar la gráfica histórica.
def obtener_datos(nombre):
    # Usamos random.seed(nombre) para que la gráfica no baile locamente cada vez que refrescamos,
    # sino que parezca una señal continua asociada a ese nombre.
    random.seed(nombre) 
    
    # Dependiendo del nombre, generamos valores en rangos lógicos (simulando realidad)
    if "hv" in nombre: 
        vals = [random.randint(350, 580) for _ in range(30)]
    elif "temp" in nombre or "refri" in nombre: 
        vals = [random.randint(20, 60) for _ in range(30)] # Simula temps normales y altas
    elif "IMD" in nombre:
        vals = [random.randint(90, 5000) for _ in range(30)]
    elif "vcc" in nombre and ("p1" in nombre or "p2" in nombre): 
        vals = [random.uniform(4.8, 5.2) for _ in range(30)]
    elif "vcc" in nombre or "pre board" in nombre: 
        vals = [random.uniform(11.0, 14.5) for _ in range(30)]
    elif "gnd" in nombre:
        vals = [random.uniform(-0.2, 0.2) for _ in range(30)]
    elif "error" in nombre or "red tsal" in nombre:
        # Probabilidad baja de error (0 o 1)
        vals = [1 if random.random() > 0.9 else 0 for _ in range(30)]
    elif "enable" in nombre or "sdc" in nombre or "ok" in nombre or "estat" in nombre:
        vals = [0 if random.random() > 0.9 else 1 for _ in range(30)]
    else: 
        vals = [random.randint(5, 95) for _ in range(30)]
    
    random.seed() # Liberamos la semilla para que otros randoms sean aleatorios de verdad
    return vals

# ==========================================
#  LÓGICA DE COLORES (EL CEREBRO DEL SISTEMA)
# ==========================================
def obtener_estado(nombre_senal, valor):
    # Si la señal no tiene límites definidos, asumimos que siempre está bien.
    if nombre_senal not in limites_senales:
        return "VERDE"
    
    lim_min, lim_max = limites_senales[nombre_senal]
    
    # IMPORTANTE: Redondear a 2 decimales antes de comparar.
    # Esto evita el caso de que veas "60.00" en pantalla pero sea 60.000001 internamente
    # y te de error sin motivo aparente.
    val_visual = round(valor, 2)
    
    # 1. ESTADO ROJO (CRÍTICO)
    # Usamos <= y >=. Si el límite es 60 y el valor es 60, ES ROJO.
    if val_visual <= lim_min or val_visual >= lim_max:
        return "ROJO"
    
    # 2. ESTADO AMARILLO (PRECAUCIÓN)
    # Calculamos si el valor está "cerca" de los límites (zona de advertencia).
    rango = lim_max - lim_min
    if rango > 1.5: # Solo aplicamos amarillo si el rango es lo suficientemente amplio
        margen = rango * 0.1  # Definimos un margen del 10%
        # Si el valor está en ese 10% cerca del borde inferior o superior...
        if val_visual < (lim_min + margen) or val_visual > (lim_max - margen):
            return "AMARILLO"
    
    # 3. ESTADO VERDE (OK)
    return "VERDE"

# -------------------------
# FUNCIÓN DE DIBUJADO (CANVAS)
# -------------------------
def dibujar_grafica(canvas, valores, nombre_senal):
    # Limpiamos el lienzo antes de dibujar de nuevo
    canvas.update_idletasks()
    canvas.delete("all")
    
    # Definición de márgenes (Izquierda, Derecha, Arriba, Abajo)
    m_l, m_r, m_t, m_b = 85, 60, 50, 60
    w, h = canvas.winfo_width(), canvas.winfo_height()
    
    # Si la ventana es muy pequeña, no dibujamos para evitar errores
    if w <= (m_l + m_r) or h <= (m_t + m_b): return

    # Cálculos de máximos y mínimos para escalar la gráfica
    val_max_data = max(valores) if valores else 1
    val_min_data = min(valores) if valores else 0
    
    # Determinamos los límites visuales del Eje Y
    if nombre_senal in limites_senales:
        lim_min, lim_max = limites_senales[nombre_senal]
    else:
        lim_min, lim_max = val_min_data, val_max_data
    
    # Ajustamos el Eje Y para que se vean siempre los datos y los límites rojos
    y_max_eje = max(val_max_data, lim_max)
    y_min_eje = min(val_min_data, lim_min)
    
    # Añadimos un poco de aire (padding) arriba y abajo
    rango_visual = y_max_eje - y_min_eje
    if rango_visual == 0: rango_visual = 1
    y_max_eje += rango_visual * 0.1
    y_min_eje -= rango_visual * 0.1

    # Variables auxiliares para convertir valor numérico -> coordenada píxel Y
    altura_util = h - m_b - m_t
    y_base = h - m_b

    def obtener_y(val):
        # Regla de tres: convierte el valor en una posición en la pantalla
        pct = (val - y_min_eje) / (y_max_eje - y_min_eje)
        return y_base - (pct * altura_util)

    # Convertimos la lista de valores en coordenadas (x, y)
    num_puntos = len(valores)
    puntos = []
    for i, v in enumerate(valores):
        x = m_l + i * (w - m_l - m_r) / (num_puntos - 1)
        y = obtener_y(v)
        puntos.append((x, y))

    # Dibujamos el área azul rellena bajo la curva
    if len(puntos) > 1:
        area_coords = [(m_l, y_base)] + puntos + [(puntos[-1][0], y_base), (m_l, y_base)]
        canvas.create_polygon(area_coords, fill="#E1EFFF", outline="") 

    # Dibujamos las "zonas de peligro" (fondos rojos suaves arriba y abajo de los límites)
    y_lim_max = obtener_y(lim_max)
    y_lim_min = obtener_y(lim_min)
    canvas.create_rectangle(m_l, m_t, w - m_r, y_lim_max, fill=COLOR_SOMBRA_ALERTA, outline="")
    canvas.create_rectangle(m_l, y_lim_min, w - m_r, y_base, fill=COLOR_SOMBRA_ALERTA, outline="")

    # Dibujamos la línea azul de los datos
    if len(puntos) > 1:
        canvas.create_line(puntos, fill="#0055FF", width=2)

    # Dibujamos las líneas rojas discontinuas de los límites
    for val_lim in [lim_min, lim_max]:
        y_pos_lim = obtener_y(val_lim)
        # Solo dibujamos si cae dentro del área visible
        if m_t - 10 <= y_pos_lim <= y_base + 10:
            canvas.create_line(m_l, y_pos_lim, w - m_r, y_pos_lim, fill="red", width=1, dash=(4, 2))
            lbl = f"{val_lim:.1f}" if abs(val_lim) < 10 else f"{int(val_lim)}"
            canvas.create_text(m_l - 15, y_pos_lim, text=lbl, fill="red", font=("Arial", 7, "bold"), anchor="e")

    # Dibujamos ejes X e Y
    canvas.create_line(m_l, y_base, w-m_r, y_base, width=2, arrow=tk.LAST) 
    canvas.create_line(m_l, m_t, m_l, y_base, width=2, arrow=tk.FIRST)    
    unidad = unidades.get(nombre_senal, "")
    canvas.create_text(m_l - 80, m_t - 25, text=f"VALOR ({unidad})", font=("Arial", 10, "bold"), anchor="nw")
    canvas.create_text(w - 20, y_base + 35, text="TIEMPO (s)", font=("Arial", 10, "bold"), anchor="e")

    # Dibujamos las etiquetas numéricas del Eje Y
    for i in range(6):
        val = y_min_eje + (y_max_eje - y_min_eje) * (i / 5)
        y_pos = obtener_y(val)
        txt = f"{int(val)}" if abs(val) >= 10 else f"{val:.1f}"
        canvas.create_text(m_l - 10, y_pos, text=txt, font=("Arial", 8), anchor="e")

    # Dibujamos las etiquetas de tiempo en el Eje X (0s, -3s, -6s...)
    for i in range(0, num_puntos, 5): 
        x_pos = m_l + i * (w - m_l - m_r) / (num_puntos - 1)
        segundos_pasados = (num_puntos - 1 - i) * 3
        txt_tiempo = "0s" if segundos_pasados == 0 else f"-{segundos_pasados}s"
        canvas.create_text(x_pos, y_base + 15, text=txt_tiempo, font=("Arial", 8))

# ============================
# GESTIÓN DE PESTAÑAS (DETALLE DE SENSORES)
# ============================
def abrir_vista(titulo, lista_senales, senal_especifica=None):
    # Ocultamos el panel principal y mostramos el de pestañas
    principal_frame.grid_remove()
    notebook_frame.grid()
    
    # Si la pestaña ya existe, solo la enfocamos
    if titulo in pestanas_abiertas:
        frame_actual = pestanas_abiertas[titulo]
        notebook.select(frame_actual)
    else:
        # Si no existe, creamos una nueva pestaña en el Notebook
        frame_actual = ttk.Frame(notebook)
        notebook.add(frame_actual, text=f"{titulo}   ❌") # La X es decorativa, el cierre es con evento click
        notebook.select(frame_actual)
        pestanas_abiertas[titulo] = frame_actual
        
        # Estructura interna de la pestaña
        cuerpo = tk.Frame(frame_actual, bg="#DDD")
        cuerpo.pack(fill="both", expand=True)
        
        # Izquierda: Lista de sensores (Treeview)
        l_f = tk.Frame(cuerpo, width=320, bg="#DDD")
        l_f.pack(side="left", fill="y", padx=10, pady=10)
        tree = ttk.Treeview(l_f, columns=("v",), show="tree", selectmode="none")
        tree.pack(fill="both", expand=True)
        tree.column("v", anchor="e", width=100)
        
        # Configuramos los colores de las filas del Treeview
        tree.tag_configure("VERDE", background=COLOR_VERDE)
        tree.tag_configure("AMARILLO", background=COLOR_AMARILLO)
        tree.tag_configure("ROJO", background=COLOR_ROJO)
        tree.tag_configure("SEL", foreground="blue", font=("Arial", 10, "bold")) # Estilo para la fila seleccionada
        
        # Rellenamos la lista con los sensores recibidos
        for s in lista_senales:
            v_actual = obtener_datos(s)[-1]
            est_color = obtener_estado(s, v_actual)
            # Traducimos el estado al color visual
            col = "VERDE" if est_color == "VERDE" else ("AMARILLO" if est_color == "AMARILLO" else "ROJO")
            tree.insert("", "end", iid=s, text=s, values=(f"{v_actual:.2f} {unidades.get(s,'')}",), tags=(col,))
        
        # Derecha: Gráfica (Canvas) y Panel de Info
        r_f = tk.Frame(cuerpo, bg="white")
        r_f.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        
        canvas = tk.Canvas(r_f, bg="white", height=400, highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=10, pady=10)
        
        f_info = tk.Frame(r_f, bg="#EEEEEE", bd=1, relief="solid")
        f_info.pack(fill="x", padx=20, pady=10)
        l_exp = tk.Label(f_info, text="Seleccione señal...", font=("Arial", 10), bg="#EEEEEE", anchor="w")
        l_exp.pack(fill="x", padx=10, pady=10)
        
        # Función interna para refrescar gráfica al hacer click en la lista
        def func_actualizar(id_s):
            if not id_s: return
            # Quitamos el estilo 'SEL' de todos y se lo ponemos al nuevo
            for i in tree.get_children():
                t = list(tree.item(i, 'tags'))
                if "SEL" in t: t.remove("SEL"); tree.item(i, tags=t)
            t = list(tree.item(id_s, 'tags')); t.append("SEL"); tree.item(id_s, tags=t)
            
            # Dibujamos gráfica y actualizamos texto descripción
            dibujar_grafica(canvas, obtener_datos(id_s), id_s)
            l_exp.config(text=explicaciones.get(id_s, f"Monitorización de {id_s}."))
            
        tree.bind("<Button-1>", lambda e: func_actualizar(tree.identify_row(e.y)))
        frame_actual.act_func = func_actualizar # Guardamos referencia para usarla desde fuera si hace falta
        
    # Si al abrir se pidió una señal concreta (click en error), la seleccionamos automáticamente
    if senal_especifica: frame_actual.act_func(senal_especifica)

# ============================
# INICIO DE LA APLICACIÓN (MAIN)
# ============================
ventana = tk.Tk()
ventana.title("CANEM VIEWER - TELEMETRY SYSTEM")
ventana.geometry("1400x800")
ventana.configure(bg="#DDD")

# Estilo visual moderno para Tkinter
style = ttk.Style(ventana)
style.theme_use("clam")

# --- BARRA SUPERIOR (BOTONES) ---
barra = tk.Frame(ventana, bg="#DDD")
barra.grid(row=0, column=0, sticky="ew")

# Botón "FUNCIONS" para volver al panel principal
tk.Button(barra, text="FUNCIONS", font=("Arial", 9, "bold"), bg="white", relief="flat", 
          command=lambda: (notebook_frame.grid_remove(), principal_frame.grid())).pack(side="left", padx=5, pady=5)

# Generamos los botones de categorías (TEMPERATURES, SDC, HV...) dinámicamente
for cat, sens in categorias.items():
    est_cat = "VERDE"
    # Comprobamos el estado de TODOS los sensores de esa categoría
    for s in sens:
        val = obtener_datos(s)[-1]
        color_senal = obtener_estado(s, val)
        if color_senal == "ROJO": 
            est_cat = "ROJO"
            break # Si uno falla, la categoría entera se marca roja
        elif color_senal == "AMARILLO" and est_cat != "ROJO": 
            est_cat = "AMARILLO"
    
    color_boton = COLOR_ROJO if est_cat == "ROJO" else (COLOR_AMARILLO if est_cat == "AMARILLO" else COLOR_VERDE)
    tk.Button(barra, text=cat, bg=color_boton, relief="flat", font=("Arial", 9, "bold"),
              command=lambda c=cat, s=sens: abrir_vista(c, s)).pack(side="left", padx=2, pady=5)

# --- PANEL PRINCIPAL (LA VISTA DE CAJAS) ---
principal_frame = tk.Frame(ventana, bg="#DDD")
principal_frame.grid(row=1, column=0, sticky="nsew")
ventana.grid_rowconfigure(1, weight=1)
ventana.grid_columnconfigure(0, weight=1)
# Configuramos 5 columnas iguales
for i in range(5): principal_frame.columnconfigure(i, weight=1, uniform="col")

# --- CONTENEDOR DE PESTAÑAS (INICIALMENTE OCULTO) ---
notebook_frame = tk.Frame(ventana)
notebook_frame.grid(row=1, column=0, sticky="nsew")
notebook_frame.grid_remove()
notebook = ttk.Notebook(notebook_frame)
notebook.pack(fill="both", expand=True)

# Función para cerrar pestañas al hacer click
def cerrar_tab(event):
    try:
        # Detectamos en qué pestaña se hizo click
        idx = notebook.index(f"@{event.x},{event.y}")
        txt = notebook.tab(idx, "text").split("   ")[0]
        pestanas_abiertas.pop(txt, None) # La borramos de la memoria
        notebook.forget(idx)             # La quitamos de la vista
        # Si no quedan pestañas, volvemos al menú principal
        if not notebook.tabs(): (notebook_frame.grid_remove(), principal_frame.grid())
    except: pass
notebook.bind("<Button-1>", cerrar_tab)

# --- MAPEO DEL PANEL PRINCIPAL (COLUMNAS Y CAJAS) ---
# Estructura: (Índice Columna, Título Columna, [Lista de Cajas/Módulos])
mapping = [(0,"FRONT ECU",["R2D","APPS","DATALOGGER","BOTS"]),
           (1,"ACCU 1",["BMS","ACCU ECU", "TSAL GREEN"]),
           (2,"ACCU 2",["IMD","SDC RESET", "TSAL GREEN HV","PRE BOARD"]),
           (3,"HV BOX",["BSPD","TSAL RED","CIRC DES"]),
           (4,"REAR BOX",["CONT INVERT","TEMP REFRI REAR","TEMP INV","CONT BR LIGHT"])]

# Bucle maestro que dibuja todas las columnas y cajas del panel principal
for col_idx, tit, funcs in mapping:
    # Frame para la columna
    f = tk.Frame(principal_frame, bg="#DDD")
    f.grid(row=0, column=col_idx, sticky="nsew", padx=2)
    tk.Label(f, text=tit, font=("Arial", 11, "bold"), bg="#DDD").pack(pady=10)
    
    # Iteramos por cada módulo (Caja gris)
    for fn in funcs:
        s_m = modulos_senales.get(fn, [])
        est, errs = "VERDE", []
        
        # Verificamos estado de todos los sensores dentro de este módulo
        for s in s_m:
            val = obtener_datos(s)[-1]
            color_senal = obtener_estado(s, val)
            if color_senal == "ROJO": 
                est = "ROJO"
                # Guardamos el error para mostrarlo en la lista pequeña debajo del botón
                errs.append((s, val, unidades.get(s,"")))
            elif color_senal == "AMARILLO" and est != "ROJO": 
                est = "AMARILLO"
        
        # Dibujamos el contenedor y el botón del módulo
        cont = tk.Frame(f, bg="#BBB", bd=1); cont.pack(fill="x", padx=10, pady=5)
        btn_c = COLOR_ROJO if est=="ROJO" else (COLOR_AMARILLO if est=="AMARILLO" else COLOR_VERDE)
        tk.Button(cont, text=fn, bg=btn_c, relief="flat", font=("Arial", 9, "bold"), command=lambda n=fn: abrir_vista(n, modulos_senales[n])).pack(fill="x")
        
        # SI EL MÓDULO ESTÁ EN ROJO: Mostramos la lista de errores debajo del botón
        if est == "ROJO":
            t = ttk.Treeview(cont, columns=("v",), show="tree", height=len(errs), selectmode="none")
            t.pack(fill="x"); t.column("#0", width=120); t.column("v", width=60, anchor="e")
            # Insertamos los errores detectados
            for en, ev, eu in errs: t.insert("", "end", iid=en, text=en, values=(f"{ev:.2f} {eu}",), tags=("R",))
            t.tag_configure("R", background=COLOR_ROJO)
            # Al hacer click en un error, abre directamente la vista de detalle de esa señal
            t.bind("<Button-1>", lambda e, tr=t, m=fn: abrir_vista(m, modulos_senales[m], senal_especifica=tr.identify_row(e.y)) if tr.identify_row(e.y) else abrir_vista(m, modulos_senales[m]))

# Bucle principal de eventos (mantiene la ventana abierta)
ventana.mainloop()