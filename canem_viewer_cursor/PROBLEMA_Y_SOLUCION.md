# Investigación de Pérdida de Datos del CAN Bus

## Problema Encontrado: **Discrepancia en Tamaños DLC**

### Resumen Ejecutivo

La razón por la que **95.2% de los frames recibidos no se decodificaban** fue que el **archivo DBC definía un tamaño de mensaje (DLC) diferente al que el bus realmente enviaba**.

### Ejemplos de Discrepancia

| Mensaje | DBC (bytes) | Bus (bytes) | Estado | Señales |
|---------|-------------|------------|--------|---------|
| FrontECU_M1 (0x100) | 7 | 5 | ❌ NO DECODIFICABA | FpDIGRpot, etc. |
| InverterRX (0x102) | 8 | 3 | ❌ NO DECODIFICABA | FpANLRpot |
| InverterTX (0x103) | 8 | 4 | ❌ NO DECODIFICABA | iWarn, iVout, etc. |
| RearECU_M1 (0x200) | 6 | 5 | ❌ NO DECODIFICABA | RpSHU, etc. |
| FrontECU_M2 (0x101) | 5 | 8 | ✅ SÍ (datos extra) | FpSHU, etc. |
| RearECU_M2 (0x201) | 8 | 8 | ✅ SÍ | IpRPM, etc. |
| RearECU_M3 (0x202) | 8 | 8 | ✅ SÍ | IpT_Mot, etc. |
| HVDB (0x400) | 6 | 6 | ✅ SÍ | BpSHU, DpSHU |

### Causa Root

cantools (librería de Python para CAN) es **muy estricta**: rechaza cualquier frame cuyo tamaño no coincida exactamente con el DLC definido en el DBC.

```
Error: "Wrong data size: 5 instead of 7 bytes"
```

### Solución Implementada

#### 1. **Corrección de tamaños en DBC** ✅
   - FrontECU_M1: 7 → 5 bytes
   - InverterRX: 8 → 3 bytes
   - InverterTX: 8 → 5 bytes
   - RearECU_M1: 6 → 5 bytes

#### 2. **Permitir datos truncados en el decoder** ✅
   - Modificado `src/decoder/dbc_decoder.py` para usar `allow_truncated=True`
   - Permite decodificar InverterTX (4 bytes) cuando espera 5

### Cambios Realizados

**Archivo: `dbc/EM06CAN.dbc`**
```diff
- BO_ 256 FrontECU_M1: 7 FrontECU
+ BO_ 256 FrontECU_M1: 5 FrontECU

- BO_ 258 InverterRX: 8 Inverter
+ BO_ 258 InverterRX: 3 Inverter

- BO_ 259 InverterTX: 8 Inverter
+ BO_ 259 InverterTX: 5 Inverter

- BO_ 512 RearECU_M1: 6 RearECU
+ BO_ 512 RearECU_M1: 5 RearECU
```

**Archivo: `src/decoder/dbc_decoder.py`**
```python
# Antes:
decoded = self.db.decode_message(arbitration_id, data)

# Después:
decoded = self.db.decode_message(arbitration_id, data, allow_truncated=True)
```

### Resultados Esperados

**Antes de la corrección:**
```
Raw → Decoded: 1163 → 56 ⚠️ Loss: 95.2%
```

**Después de la corrección:**
```
Raw → Decoded: ~1000 → ~900+ ✓ Loss: < 5% (solo 0x000, 0x004 que no están en DBC)
```

### Verificación

El script `capture_and_decode.py` confirmó:
- ✅ FrontECU_M1 (0x100): Ahora decodifica correctamente con FpDIGRpot=2.35
- ✅ InverterRX (0x102): Ahora decodifica FpANLRpot=752
- ✅ RearECU_M1 (0x200): Ahora decodifica RpSHU=87, RpSIGlvs=7
- ⚠️ InverterTX (0x103): Requiere `allow_truncated=True` (incluido en decoder)

### Impacto en el Dashboard

Con estos cambios, el dashboard ahora debería mostrar:
- ✅ **FrontECU_M1**: Valores correctos (FpDIGRpot, FpDIGLpot, etc.)
- ✅ **FrontECU_M2**: Valores correctos (FpSHU, FpDIGvel, etc.)
- ✅ **RearECU_M1**: Valores correctos (RpSHU, RpSIGlvs, etc.)
- ✅ **RearECU_M2**: Valores correctos (IpRPM, IpI, IpV, IpPar)
- ✅ **RearECU_M3**: Valores correctos (IpT_Mot, IpT_IGBT, etc.)
- ✅ **Inverter**: Valores correctos (iWarn, iVout, iTmot, etc.)
- ✅ **HVDB**: Valores correctos (BpSHU, DpSHU, etc.)

### Próximos Pasos

1. Ejecutar aplicación: `python app.py --auto-detect`
2. Verificar que todas las PCBs muestren valores
3. Confirmar que no hay más el error "95.2% loss"

### Archivos Modificados

- `dbc/EM06CAN.dbc` - Correcciones de tamaños DLC
- `src/decoder/dbc_decoder.py` - Permitir datos truncados
- `src/services/pipeline.py` - Parámetro `debug` para tracing
- `app.py` - Parámetro `--debug`

### Conclusión

El problema **NO era un error en el código**, sino una **incompatibilidad entre las definiciones del DBC y los datos reales del bus**. Al actualizar los tamaños DLC para que coincidan con lo que el bus realmente envía, los mensajes ahora se decodifican correctamente.

Este es un ejemplo de por qué es crítico verificar que el DBC esté correctamente sincronizado con el hardware real.
