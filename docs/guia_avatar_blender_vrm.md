# Guía: Avatar VRM en Blender → VTube Studio → GEM

GEM usa la API pública de **VTube Studio** para mover un avatar mientras habla. Esta guía cubre el camino completo: crear/conseguir un avatar, exportarlo como VRM, cargarlo en VTube Studio y mapear las expresiones que GEM espera.

## 1. Conseguir el avatar

Tienes tres caminos:

### A. VRoid Studio (lo más rápido, gratis)

1. Descarga **VRoid Studio** desde [vroid.com](https://vroid.com/en/studio).
2. Modela tu personaje con sliders (rostro, pelo, ropa).
3. Exporta como `.vrm` (Archivo → Exportar → VRM).
4. Salta directo al paso **3. Cargar en VTube Studio**.

### B. Blender + add-on VRM (más control)

Si quieres control fino o ya tienes una malla:

1. Instala Blender 4.x.
2. Instala el add-on [**VRM Add-on for Blender**](https://vrm-addon-for-blender.info/).
3. Importa tu modelo `.fbx`/`.obj`.
4. **Rigging:** crea un armature humanoide. Los nombres de huesos deben mapear al estándar VRM (Hips, Spine, Chest, Neck, Head, LeftShoulder, etc.).
5. **Pesos (skinning):** asigna vértices a huesos (Weight Paint).
6. **Blendshapes (shape keys):** crea al menos:
   - `Joy`, `Angry`, `Sorrow`, `Fun`, `Neutral` (las 5 que usa GEM)
   - `A`, `I`, `U`, `E`, `O` (visemas para lipsync; `MouthOpen` también funciona)
   - `Blink_L`, `Blink_R` (parpadeo)
7. En el panel del add-on: **Make Armature → VRM Humanoid**, asigna metadatos.
8. Exporta: `File → Export → VRM`.

### C. Comprar / descargar un VRM hecho

[Booth.pm](https://booth.pm/), [VRoid Hub](https://hub.vroid.com/), itch.io. Asegúrate que la licencia permita uso comercial si lo vas a streamear.

## 2. Verificar el VRM

Antes de importarlo a VTube, abre el `.vrm` en [**VRM Viewer**](https://vrm-viewer.com/) o el viewer de UniVRM. Confirma:

- El modelo está parado, mirando al frente.
- Los huesos están bien orientados (no hay codos torcidos).
- Las blendshapes responden (prueba "Joy", "Angry").

## 3. Cargar en VTube Studio

1. Compra **VTube Studio** en Steam (o usa la versión gratis con marca de agua).
2. Coloca el `.vrm` en `Documents/VTube Studio/Live2DModels/` (sí, también acepta VRM).
   - Si VTube no lo detecta, revisa el log; puede que necesites convertirlo a Live2D primero. Para 3D puro, conviene usar **VSeeFace** en lugar de VTube Studio.
   - **Alternativa fácil**: usa un modelo Live2D de la propia VTube en lugar de VRM. La API es la misma.
3. Carga el modelo desde el menú lateral de VTube.
4. **Habilita la API**: ⚙ Configuración → "API de complementos" → activar. Default port: **8001**.

## 4. Mapear expresiones para GEM

GEM enviará a VTube los siguientes archivos `.exp3.json` por nombre:

| Emoción detectada (visión) | Archivo esperado    |
|----------------------------|---------------------|
| `alegre`                   | `Joy.exp3.json`     |
| `estresado`                | `Angry.exp3.json`   |
| `confundido`               | `Sorrow.exp3.json`  |
| `sorprendido`              | `Fun.exp3.json`     |
| `neutro`                   | `Neutral.exp3.json` |

### Crear las expresiones en VTube

1. En VTube Studio, abre el editor de expresiones (icono 🎭).
2. Crea una nueva, nómbrala exactamente `Joy` (sin extensión).
3. Mueve los sliders de blendshapes al gusto (sonrisa abierta, ojos cerrados, etc.).
4. Guarda. VTube genera `Joy.exp3.json` automáticamente.
5. Repite para `Angry`, `Sorrow`, `Fun`, `Neutral`.

> Si los nombres no coinciden, GEM no podrá activarlas. Puedes cambiar el mapeo en `backend/modulos/vtube.py`, dict `EXPRESIONES`.

## 5. Lipsync

GEM no usa los visemas de VTube; calcula RMS del audio TTS en tiempo real y lo envía como `MouthOpen` y `MouthSmile` vía `InjectParameterDataRequest`. Para que funcione:

- En el modelo, esos parámetros deben llamarse exactamente **`MouthOpen`** y **`MouthSmile`** (default de VTube).
- Si tu modelo los llama distinto, edita `vtube.py` línea ~155 y cambia los `id`.

## 6. Primer arranque

1. Abre VTube Studio con el modelo cargado y la API encendida.
2. Arranca GEM (`python -m backend.main`).
3. La **primera vez** VTube te mostrará un pop-up pidiendo autorizar al plugin **GEM Assistant**. Acéptalo.
4. GEM guarda el token en `data/vtube_token.txt` y no te lo vuelve a pedir.

Si sale algo mal:
- Borra `data/vtube_token.txt` y reinicia.
- Verifica que el puerto en `.env` (`VTUBE_WS_PORT`) coincida con el de VTube.
- Revisa el log del backend; busca líneas con `gem.vtube`.

## 7. Probar manualmente

Con GEM corriendo y VTube conectado, abre Python:

```python
import asyncio
from backend.modulos.vtube import VTubeCliente

async def test():
    v = VTubeCliente()
    await v.conectar()
    for emocion in ["alegre", "estresado", "confundido", "sorprendido", "neutro"]:
        print(emocion)
        await v.set_expresion(emocion)
        await asyncio.sleep(2)
    await v.desconectar()

asyncio.run(test())
```

Si el avatar cambia de cara cada 2 segundos, todo está bien.
