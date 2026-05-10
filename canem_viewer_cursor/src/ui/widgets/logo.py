from __future__ import annotations

import tkinter as tk
from PIL import Image, ImageTk
import os


class LogoWidget:
    """Widget per mostrar el logotip de l'equip"""
    
    def __init__(self, parent: tk.Widget, with_text: bool = True, size: tuple[int, int] = (40, 40)):
        """
        Inicialitza el widget del logotip
        
        Args:
            parent: Widget pare
            with_text: Si el logotip ha d'incloure text
            size: Mida del logotip (amplada, alçada)
        """
        self.parent = parent
        self.with_text = with_text
        self.size = size
        self.logo_label = None
        
        # Ruta als logos
        self.logo_with_text_path = "assets/logo_with_text.png"
        self.logo_no_text_path = "assets/logo_no_text.png"
        
        # Crear el widget
        self._create_logo()
    
    def _create_logo(self) -> None:
        """Crea el widget del logotip"""
        try:
            # Determinar quin logo carregar
            logo_path = self.logo_with_text_path if self.with_text else self.logo_no_text_path
            
            if os.path.exists(logo_path):
                # Carregar la imatge
                image = Image.open(logo_path)
                image = image.resize(self.size, Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                
                # Crear el label amb la imatge
                self.logo_label = tk.Label(
                    self.parent,
                    image=photo,
                    bg="#DDD",  # Fons per defecte en Light Mode
                    relief="flat"
                )
                self.logo_label.image = photo  # Mantenir referència
            else:
                # Si no existeix la imatge, crear un placeholder
                self.logo_label = tk.Label(
                    self.parent,
                    text="LOGO",
                    font=("Arial", 10, "bold"),
                    bg="#DDD",
                    fg="#666666",
                    relief="flat",
                    width=5,
                    height=2
                )
        except Exception as e:
            print(f"Error carregant logo: {e}")
            # Crear un label d'error
            self.logo_label = tk.Label(
                self.parent,
                text="ERR",
                font=("Arial", 8),
                bg="#DDD",
                fg="#FF0000",
                relief="flat"
            )
    
    def place(self, **kwargs) -> None:
        """Posiciona el widget"""
        if self.logo_label:
            self.logo_label.place(**kwargs)
    
    def update_background(self, color: str) -> None:
        """Actualitza el color de fons"""
        if self.logo_label:
            self.logo_label.configure(bg=color)
    
    def set_size(self, size: tuple[int, int]) -> None:
        """Estableix una nova mida i recarrega el logo"""
        self.size = size
        self._create_logo()
