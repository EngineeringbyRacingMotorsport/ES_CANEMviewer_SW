from __future__ import annotations

import json
import os
from typing import Dict, Any, Optional

from src.model.vehicle_model import VehicleModel


class CarStateManager:
    """Gestiona els estats del cotxe i la configuració de senyals digitals"""
    
    def __init__(self, config_path: str = "config/digital_signals.json"):
        self.config_path = config_path
        self.current_state = "INIT"
        self.config: Dict[str, Any] = {}
        self._load_config()
    
    def _load_config(self) -> None:
        """Carrega la configuració del fitxer JSON"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                print(f"Config file not found: {self.config_path}")
                self.config = {"car_states": {}, "digital_signals": {}}
        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {"car_states": {}, "digital_signals": {}}
    
    def get_current_state(self) -> str:
        """Retorna l'estat actual del cotxe"""
        return self.current_state
    
    def update_state(self, model: VehicleModel) -> None:
        """Actualitza l'estat del cotxe basat en els senyals"""
        trigger_signals = self.config.get("car_states", {})
        
        # Comprovar cada estat possible
        for state_name, state_config in trigger_signals.items():
            triggers = state_config.get("trigger_signals", {})
            
            # Comprovar si tots els senyals de trigger coincideixen
            state_matches = True
            for signal_name, expected_value in triggers.items():
                # Buscar el senyal al model
                signal_found = False
                for pcb in model.vehicle.pcbs.values():
                    if signal_name in pcb.signals:
                        signal = pcb.signals[signal_name]
                        if signal.value != expected_value:
                            state_matches = False
                            signal_found = True
                            break
                        signal_found = True
                        break
                
                if not signal_found or not state_matches:
                    break
            
            if state_matches:
                self.current_state = state_name
                break
    
    def get_signal_config(self, signal_name: str) -> Dict[str, Any]:
        """Retorna la configuració d'un senyal digital"""
        return self.config.get("digital_signals", {}).get(signal_name, {})
    
    def validate_digital_signal(self, signal_name: str, value: float) -> str:
        """Valida un senyal digital segons la configuració i l'estat actual"""
        signal_config = self.get_signal_config(signal_name)
        
        if not signal_config:
            # Si no té configuració, usar lògica simple per defecte
            return "OK" if value == 1 else "ERROR"
        
        logic_type = signal_config.get("logic", "simple_binary")
        
        if logic_type == "simple_binary" or signal_config.get("independent", False):
            # Lògica simple: 0=ERROR, 1=OK
            return "OK" if value == 1 else "ERROR"
        
        elif logic_type == "state_dependent":
            # Lògica dependent de l'estat del cotxe
            current_state = self.current_state
            state_configs = signal_config.get("car_states", {})
            
            # Obtenir configuració per l'estat actual
            state_config = state_configs.get(current_state, {})
            if not state_config:
                # Si no hi ha configuració per aquest estat, usar el default
                default_state = signal_config.get("default_state", "INIT")
                state_config = state_configs.get(default_state, {})
            
            ok_values = state_config.get("ok_values", [1])
            error_values = state_config.get("error_values", [0])
            
            if value in ok_values:
                return "OK"
            elif value in error_values:
                return "ERROR"
            else:
                return "WARNING"  # Valor no esperat
        
        return "OK"  # Default
    
    def get_signal_description(self, signal_name: str) -> str:
        """Retorna la descripció d'un senyal per a l'estat actual"""
        signal_config = self.get_signal_config(signal_name)
        
        if not signal_config:
            return "Senyal digital"
        
        logic_type = signal_config.get("logic", "simple_binary")
        
        if logic_type == "simple_binary" or signal_config.get("independent", False):
            return signal_config.get("description", "Senyal digital independent")
        
        elif logic_type == "state_dependent":
            current_state = self.current_state
            state_configs = signal_config.get("car_states", {})
            
            # Obtenir descripció per l'estat actual
            state_config = state_configs.get(current_state, {})
            if not state_config:
                # Si no hi ha configuració per aquest estat, usar el default
                default_state = signal_config.get("default_state", "INIT")
                state_config = state_configs.get(default_state, {})
            
            return state_config.get("description", f"Senyal digital en estat {current_state}")
        
        return "Senyal digital"
    
    def reload_config(self) -> None:
        """Recarrega la configuració del fitxer JSON"""
        self._load_config()
    
    def get_all_states(self) -> Dict[str, str]:
        """Retorna tots els estats possibles amb les seves descripcions"""
        states = {}
        for state_name, state_config in self.config.get("car_states", {}).items():
            states[state_name] = state_config.get("description", state_name)
        return states


# Global CarStateManager instance
_car_state_manager = CarStateManager()


def get_car_state_manager() -> CarStateManager:
    """Retorna la instància global del CarStateManager"""
    return _car_state_manager


def set_car_state_manager(manager: CarStateManager) -> None:
    """Estableix la instància del CarStateManager"""
    global _car_state_manager
    _car_state_manager = manager
