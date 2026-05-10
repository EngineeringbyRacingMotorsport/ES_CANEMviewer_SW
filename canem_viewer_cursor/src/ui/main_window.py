from __future__ import annotations

import time
import tkinter as tk
from tkinter import ttk

from src.model.vehicle_model import VehicleModel
from src.services.pipeline import TelemetryPipeline
from src.ui.tabs import ConfigurationTab, GeneralTab, SDCTab, SensorTab, TemperatureTab
from src.ui.widgets.footer_bar import FooterBar
from src.ui.widgets.logo import LogoWidget


class MainWindow(tk.Tk):
    def __init__(self, model: VehicleModel, pipeline: TelemetryPipeline) -> None:
        super().__init__()
        self.model = model
        self.pipeline = pipeline
        
        self.title("CANEM Viewer - EUSS Motorsport")
        self.geometry("1400x800")
        self.minsize(1400, 800)
        self.maxsize(1400, 800)
        self.resizable(False, False)
        self.configure(bg="#DDD")

        self.setup_styles()

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        self.dynamic_frame = tk.Frame(self, bg="#DDD")
        self.dynamic_frame.grid(row=0, column=0, sticky="nsew")
        self.footer = FooterBar(self, model=self.model)
        self.footer.grid(row=1, column=0, sticky="ew")
        
        # Afegir logos
        self._setup_logos()
        
        self.notebook = ttk.Notebook(self.dynamic_frame)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(8, 8))

        self.tab_general = GeneralTab(self.notebook, model=self.model)
        self.tab_temps = TemperatureTab(self.notebook)
        self.tab_sdc = SDCTab(self.notebook, model=self.model)
        self.tab_sensor = SensorTab(self.notebook, model=self.model)
        self.tab_config = ConfigurationTab(self.notebook)
        self._dark_mode_enabled = False
        self._demo_enabled = True

        self.notebook.add(self.tab_general, text="General")
        self.notebook.add(self.tab_sensor, text="Sensòrica")
        self.notebook.add(self.tab_temps, text="Temperatures")
        self.notebook.add(self.tab_sdc, text="SDC")
        self.notebook.add(self.tab_config, text="Configuració")

        # Aplicar mode inicial (light mode per defecte)
        self._set_dark_mode(False)

        # Configurar icona de la finestra al final (després de tota la UI)
        self._set_window_icon()

        self.ui_refresh_ms = 250
        self.after(self.ui_refresh_ms, self._ui_tick)

    def _setup_logos(self) -> None:
        """Configura els logos a diferents ubicacions"""
        # Només logo per la barra de tasques de Windows (sense text)
        self.taskbar_logo = LogoWidget(self, with_text=False, size=(16, 16))
        self._update_taskbar_icon()
    
    def _set_window_icon(self) -> None:
        """Configura la icona de la finestra per reemplaçar el logo de Python"""
        try:
            import os
            import sys
            
            print("=== ANÀLISI PROFUNDA: PYTHON VS EXE ===")
            
            # Analitzar com s'està executant l'aplicació
            print(f"1. Executable: {sys.executable}")
            print(f"2. Arguments: {sys.argv}")
            print(f"3. És script Python?: {'.py' in sys.executable}")
            print(f"4. És executable?: {'.exe' in sys.executable}")
            
            # Primer provar carregar el logo original per la finestra
            ico_path = "assets/logo_no_text.ico"
            if os.path.exists(ico_path):
                print(f"5. Fitxer ICO trobat: {os.path.getsize(ico_path)} bytes")
                
                try:
                    from PIL import Image, ImageTk
                    print("6. Carregant logo per finestra...")
                    img = Image.open(ico_path)
                    print(f"   Info: {img.format}, {img.mode}, {img.size}")
                    
                    # Convertir a 32x32 si cal
                    if img.size != (32, 32):
                        print(f"   Convertint de {img.size} a 32x32...")
                        img = img.resize((32, 32), Image.Resampling.LANCZOS)
                    
                    # Carregar com a icona de la finestra
                    photo = ImageTk.PhotoImage(img)
                    self.iconphoto(False, photo)
                    self.window_icon = photo
                    
                    print("SUCCESS: Logo carregat a la finestra!")
                    
                    # Analitzar problema de la barra de tasques
                    self._analyze_taskbar_issue(ico_path)
                    
                    return
                    
                except Exception as e:
                    print(f"ERROR carregant logo: {e}")
            
            # Si falla el logo, usar icona verda amb "E"
            print("7. Usant icona verda de l'equip amb 'E'...")
            
            green_icon = tk.PhotoImage(width=32, height=32)
            
            # Fons verd del color de l'equip
            for x in range(32):
                for y in range(32):
                    green_icon.put("#22C55E", (x, y))
            
            # Afegir "E" blanca al centre
            for y in range(8, 24):
                green_icon.put("#FFFFFF", (6, y))
                green_icon.put("#FFFFFF", (26, y))
            for x in range(6, 27):
                green_icon.put("#FFFFFF", (x, 8))
                green_icon.put("#FFFFFF", (x, 16))
                green_icon.put("#FFFFFF", (x, 24))
            
            self.iconphoto(False, green_icon)
            self.window_icon = green_icon
            
            print("SUCCESS: Icona verda carregada a la finestra!")
            
        except Exception as e:
            print(f"ERROR general: {e}")
            import traceback
            traceback.print_exc()
    
    def _analyze_taskbar_issue(self, ico_path: str) -> None:
        """Analitza el problema específic de la barra de tasques"""
        try:
            print("8. ANALITZANT PROBLEMA DE BARRA DE TASQUES...")
            
            import sys
            import os
            
            # Comprovar si estem executant amb Python directe
            if '.py' in sys.executable or 'python' in sys.executable.lower():
                print("   ⚠️  PROBLEMA IDENTIFICAT: Estàs executant amb Python!")
                print("   📋 EXPLICACIÓ:")
                print("      - Quan executes 'python app.py', Windows mostra l'icona de python.exe")
                print("      - La icona de la finestra (iconphoto) només afecta la finestra")
                print("      - La barra de tasques mostra l'icona de l'executable (python.exe)")
                print("      - Per canviar la icona de la barra de tasques, necessites:")
                print("        a) Canviar la icona de python.exe (no recomanat)")
                print("        b) Crear un .exe específic per la teva aplicació")
                print("        c) Utilitzar eines com PyInstaller, cx_Freeze, etc.")
                
                # Provar mètodes addicionals
                self._try_alternative_taskbar_methods(ico_path)
                
            else:
                print("   ✅ Estàs executant un .exe - hauria de funcionar")
                self._set_taskbar_icon(ico_path)
            
        except Exception as e:
            print(f"ERROR analitzant problema: {e}")
    
    def _try_alternative_taskbar_methods(self, ico_path: str) -> None:
        """Prova mètodes alternatius per la barra de tasques quan s'executa amb Python"""
        try:
            print("9. PROVANT METODES ALTERNATIUS PER PYTHON...")
            
            # Mètode 1: Intentar canviar la icona del procés
            try:
                import ctypes
                from ctypes import wintypes
                
                kernel32 = ctypes.windll.kernel32
                user32 = ctypes.windll.user32
                
                # Obtenir el handle del procés actual
                hProcess = kernel32.GetCurrentProcess()
                print(f"   Handle del procés: {hProcess}")
                
                # Carregar icona
                hIcon = user32.LoadImageW(None, ico_path, 1, 32, 32, 0x00000010)
                if hIcon:
                    print(f"   Icona carregada: {hIcon}")
                    # Aquest mètode probablement no funcionarà per Python
                    print("   ⚠️  Aquest mètode probablement no funcionarà amb Python")
                else:
                    print("   ERROR: No s'ha pogut carregar la icona")
                    
            except Exception as e:
                print(f"   ERROR mètode 1: {e}")
            
            # Mètode 2: Crear un fitxer .exe temporal
            try:
                print("10. SUGGERIMENT: Crear un .exe per a l'aplicació")
                print("    Opcions:")
                print("    - PyInstaller: pip install pyinstaller")
                print("    - pyinstaller --onefile --icon=assets/logo_no_text.ico app.py")
                print("    - cx_Freeze: pip install cx_Freeze")
                print("    - Auto-py-to-exe: pip install auto-py-to-exe")
                
            except Exception as e:
                print(f"ERROR suggeriment: {e}")
            
            # Mostrar diagnòstic complet
            self._show_diagnosis_complete()
                
        except Exception as e:
            print(f"ERROR mètodes alternatius: {e}")
    
    def _set_taskbar_icon(self, ico_path: str) -> None:
        """Intenta configurar la icona de la barra de tasques de Windows amb mètodes agressius"""
        try:
            print("11. Intentant configurar icona de barra de tasques (metodes agressius)...")
            
            # Mètode 1: iconbitmap (mètode Tkinter)
            try:
                self.iconbitmap(ico_path)
                print("   SUCCESS: iconbitmap aplicat")
            except Exception as e:
                print(f"   ERROR iconbitmap: {e}")
            
            # Mètode 2: ctypes amb múltiples crides
            try:
                import ctypes
                from ctypes import wintypes
                
                # Carregar user32.dll i shell32.dll
                user32 = ctypes.windll.user32
                shell32 = ctypes.windll.shell32
                
                # Obtenir el handle de la finestra
                hwnd = self.winfo_id()
                print(f"   HWND: {hwnd}")
                
                # Carregar l'icona des del fitxer
                hicon = user32.LoadImageW(
                    None,
                    ico_path,
                    1,  # IMAGE_ICON
                    32, 32,  # ample i alçada
                    0x00000010  # LR_LOADFROMFILE
                )
                
                if hicon:
                    print(f"   HICON carregat: {hicon}")
                    
                    # Establir icona petita (afecta barra de tasques)
                    result1 = user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # WM_SETICON, ICON_SMALL
                    print(f"   SendMessageW (ICON_SMALL): {result1}")
                    
                    # Establir icona gran
                    result2 = user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # WM_SETICON, ICON_BIG
                    print(f"   SendMessageW (ICON_BIG): {result2}")
                    
                    # Forçar actualització de la finestra
                    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002)  # SWP_NOMOVE | SWP_NOSIZE
                    
                    # Notificar al sistema de canvi d'icona
                    user32.PostMessageW(hwnd, 0x0111, 0, 0)  # WM_COMMAND
                    
                    print("   SUCCESS: Icona configurada amb ctypes (multiples metodes)")
                    
                    # Programar actualització addicional
                    self.after(500, lambda: self._force_icon_update(hwnd, hicon))
                    self.after(2000, lambda: self._force_icon_update(hwnd, hicon))
                    
                else:
                    print("   ERROR: No s'ha pogut carregar HICON")
                    
            except Exception as e:
                print(f"   ERROR ctypes: {e}")
            
            # Mètode 3: Forçar actualització de UI
            try:
                self.update()
                self.update_idletasks()
                self.after(100, self.update)
                self.after(1000, self.update)
                print("   SUCCESS: Actualització forçada")
            except Exception as e:
                print(f"   ERROR actualització: {e}")
            
        except Exception as e:
            print(f"ERROR configurant icona de barra de tasques: {e}")
            import traceback
            traceback.print_exc()
    
    def _force_icon_update(self, hwnd: int, hicon: int) -> None:
        """Força actualització de la icona després d'un retard"""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            
            # Tornar a establir l'icona
            user32.SendMessageW(hwnd, 0x0080, 0, hicon)  # ICON_SMALL
            user32.SendMessageW(hwnd, 0x0080, 1, hicon)  # ICON_BIG
            
            # Forçar redibuix de la finestra
            user32.InvalidateRect(hwnd, None, True)
            user32.UpdateWindow(hwnd)
            
            print(f"   Icona actualitzada (delayed): hwnd={hwnd}")
            
        except Exception as e:
            print(f"   ERROR actualització retardada: {e}")
    
    def _show_diagnosis_complete(self) -> None:
        """Mostra el diagnòstic complet del problema"""
        try:
            print("\n" + "="*60)
            print("DIAGNOSTIC COMPLET DEL PROBLEMA D'ICONA")
            print("="*60)
            print("PROBLEMA IDENTIFICAT:")
            print("1. Estàs executant: python.exe (Windows Apps)")
            print("2. Windows mostra l'icona de l'executable a la barra de tasques")
            print("3. La icona de la finestra (iconphoto) només afecta la finestra")
            print("4. La barra de tasques mostra l'icona de python.exe")
            print("")
            print("SOLUCIONS:")
            print("1. Crear un executable (.exe) de l'aplicació:")
            print("   pip install pyinstaller")
            print("   pyinstaller --onefile --icon=assets/logo_no_text.ico app.py")
            print("")
            print("2. Utilitzar altres eines:")
            print("   - cx_Freeze")
            print("   - Auto-py-to-exe")
            print("   - py2exe")
            print("")
            print("3. Canviar la icona de python.exe (NO RECOMANAT)")
            print("")
            print("RESULTAT ACTUAL:")
            print("✅ Icona de finestra: Logo de l'equip visible")
            print("❌ Icona de barra de tasques: Logo de Python visible")
            print("")
            print("PER FER-HO FUNCIONAR COMPLETAMENT:")
            print("Cal crear un .exe específic per la teva aplicació")
            print("="*60)
            
        except Exception as e:
            print(f"ERROR mostrant diagnòstic: {e}")
    
    def _test_different_icons(self) -> None:
        """Prova diferents icones per trobar una que funcioni"""
        try:
            # Provar icona simple vermella
            print("Provant icona vermella...")
            red_icon = tk.PhotoImage(width=32, height=32)
            for x in range(32):
                for y in range(32):
                    red_icon.put("#FF0000", (x, y))
            self.iconphoto(False, red_icon)
            self.window_icon = red_icon
            print("Icona vermella creada")
            
            # Esperar una mica i canviar a icona blava
            self.after(1000, lambda: self._change_to_blue_icon())
            
        except Exception as e:
            print(f"Error provant icones: {e}")
            self._create_simple_icon()
    
    def _change_to_blue_icon(self) -> None:
        """Canvia a icona blava per prova"""
        try:
            print("Provant icona blava...")
            blue_icon = tk.PhotoImage(width=32, height=32)
            for x in range(32):
                for y in range(32):
                    blue_icon.put("#0000FF", (x, y))
            self.iconphoto(False, blue_icon)
            self.window_icon = blue_icon
            print("Icona blava creada")
            
            # Esperar i canviar a icona verda
            self.after(1000, self._create_simple_icon)
            
        except Exception as e:
            print(f"Error canviant a blava: {e}")
            self._create_simple_icon()
    
    def _create_simple_icon(self) -> None:
        """Crea una icona simple programàtica que funcioni"""
        try:
            # Provar l'aproximació més simple possible
            print("Intentant icona més simple possible")
            
            # Crear una icona 16x16 (mida estàndard per a la barra de tasques)
            icon = tk.PhotoImage(width=16, height=16)
            
            # Fons verd sòlid
            for x in range(16):
                for y in range(16):
                    icon.put("#22C55E", (x, y))
            
            # Establir com a icona de la finestra
            self.iconphoto(False, icon)
            self.window_icon = icon
            print("Icona 16x16 verd sòlida creada")
            
            # Provar també una icona 32x32
            icon32 = tk.PhotoImage(width=32, height=32)
            for x in range(32):
                for y in range(32):
                    icon32.put("#22C55E", (x, y))
            
            # Canviar a la icona de 32x32
            self.iconphoto(False, icon32)
            self.window_icon = icon32
            print("Icona 32x32 verd sòlida creada")
            
        except Exception as e:
            print(f"Error creant icona simple: {e}")
            # Últim recurs: icona buida
            try:
                empty_icon = tk.PhotoImage(width=1, height=1)
                self.iconphoto(False, empty_icon)
                self.window_icon = empty_icon
                print("Icona buida creada com a últim recurs")
            except Exception as e2:
                print(f"Error creant icona buida: {e2}")
    
    def _create_custom_icon(self) -> None:
        """Crea una icona personalitzada com a fallback"""
        try:
            # Crear una icona simple amb un rectangle de color
            icon = tk.PhotoImage(width=32, height=32)
            
            # Pintar un rectangle verd (color de l'equip)
            for x in range(4, 28):
                for y in range(4, 28):
                    icon.put("#22C55E", (x, y))
            
            # Afegir una "E" blanca al centre
            # E vertical
            for y in range(8, 24):
                icon.put("#FFFFFF", (8, y))
                icon.put("#FFFFFF", (24, y))
            # E horitzontal superior
            for x in range(8, 25):
                icon.put("#FFFFFF", (x, 8))
            # E horitzontal mitjana
            for x in range(8, 25):
                icon.put("#FFFFFF", (x, 16))
            # E horitzontal inferior
            for x in range(8, 25):
                icon.put("#FFFFFF", (x, 24))
            
            self.iconphoto(False, icon)
            self.window_icon = icon
            print("Icona personalitzada creada correctament")
            
        except Exception as e:
            print(f"Error creant icona personalitzada: {e}")
            # Últim recurs: icona buida
            empty_icon = tk.PhotoImage(width=1, height=1)
            self.iconphoto(False, empty_icon)
            self.window_icon = empty_icon
    
    def _update_taskbar_icon(self) -> None:
        """Actualitza la icona de la barra de tasques de Windows"""
        try:
            # Intentar carregar la icona per la barra de tasques
            if hasattr(self, 'taskbar_logo') and self.taskbar_logo.logo_label:
                # En Windows, Tkinter no suporta directament la icona de la barra de tasques
                # Però podem mostrar un petit logo a la cantonada superior esquerra
                pass  # Placeholder per futura implementació
        except Exception as e:
            print(f"Error actualitzant icona de barra de tasques: {e}")

    @staticmethod
    def setup_styles() -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#DDD", borderwidth=0)
        style.configure("TNotebook.Tab", font=("Montserrat", 11, "bold"), background="#CCC")
        style.map(
            "TNotebook.Tab",
            background=[("selected", "white"), ("!selected", "#CCC")],
            foreground=[("selected", "#0a594d"), ("!selected", "black")],
        )

    def _ui_tick(self) -> None:
        self._apply_config_runtime()
        self.tab_general.update_ui()
        self.tab_sensor.update_ui()
        self.tab_temps.update_ui()
        self.tab_sdc.update_ui()
        self.tab_config.update_ui()
        self.footer.refresh(now=time.monotonic())
        self.after(self.ui_refresh_ms, self._ui_tick)

    def _apply_config_runtime(self) -> None:
        new_refresh = int(self.tab_config.refresh_var.get())
        if new_refresh != self.ui_refresh_ms:
            self.ui_refresh_ms = new_refresh

        new_demo = bool(self.tab_config.demo_var.get())
        if new_demo != self._demo_enabled:
            self._demo_enabled = new_demo
            self.tab_sensor.set_demo_enabled(new_demo)
            self.tab_sdc.set_demo_enabled(new_demo)

        new_dark = bool(self.tab_config.dark_mode_var.get())
        if new_dark != self._dark_mode_enabled:
            self._dark_mode_enabled = new_dark
            self._set_dark_mode(new_dark)

    def _set_dark_mode(self, enabled: bool) -> None:
        if enabled:
            self.configure(bg="#1e1e1e")
            self.dynamic_frame.configure(bg="#1e1e1e")
            style = ttk.Style()
            style.configure("TNotebook", background="#1e1e1e")
            style.configure("TNotebook.Tab", background="#2f2f2f")
            style.map(
                "TNotebook.Tab",
                background=[("selected", "#1f1f1f"), ("!selected", "#2f2f2f")],
                foreground=[("selected", "#67d7c5"), ("!selected", "#d7d7d7")],
            )
        else:
            self.configure(bg="#DDD")
            self.dynamic_frame.configure(bg="#DDD")
            style = ttk.Style()
            style.configure("TNotebook", background="#DDD")
            style.configure("TNotebook.Tab", background="#CCC")
            style.map(
                "TNotebook.Tab",
                background=[("selected", "white"), ("!selected", "#CCC")],
                foreground=[("selected", "#0a594d"), ("!selected", "black")],
            )
        
        # Actualitzar colors dels logos
        bg_color = "#1e1e1e" if enabled else "#DDD"
        if hasattr(self, 'taskbar_logo'):
            self.taskbar_logo.update_background(bg_color)
        
        self.tab_general.set_dark_mode(enabled)
        self.tab_sensor.set_dark_mode(enabled)
        self.tab_temps.set_dark_mode(enabled)
        self.tab_sdc.set_dark_mode(enabled)
        self.tab_config.set_dark_mode(enabled)
        self.footer.set_dark_mode(enabled)
