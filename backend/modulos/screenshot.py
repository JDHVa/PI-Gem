"""
Screenshot bajo demanda.

Permite que GEM "vea" la pantalla del usuario cuando se le pide ayuda
con código, errores, UI, etc. No se ejecuta automáticamente —
solo cuando el usuario lo pide explícitamente o el agente lo solicita.

Usa mss (multi-monitor) si está disponible, sino PIL.ImageGrab (Windows/Mac).
"""

import io
import logging
from backend.modulos.gemini_cliente import analizar_imagen

log = logging.getLogger("gem.screenshot")


def capturar() -> bytes | None:
    """Captura la pantalla principal como JPEG bytes."""
    try:
        import mss
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)
            from PIL import Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return buf.getvalue()
    except ImportError:
        pass
    except Exception as e:
        log.warning("mss falló: %s", e)

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=80)
        return buf.getvalue()
    except Exception as e:
        log.error("No se pudo capturar pantalla: %s", e)
        return None


async def analizar_pantalla(prompt_usuario: str) -> str:
    """Captura la pantalla y la analiza con un prompt del usuario."""
    jpeg = capturar()
    if jpeg is None:
        return "No pude capturar la pantalla. Verifica que tengas mss o Pillow instalados."

    prompt = (
        f"El usuario está viendo esta pantalla. Su pregunta es: {prompt_usuario}\n\n"
        "Responde de forma directa y útil, en español. No describas todo, "
        "céntrate en lo que el usuario está preguntando."
    )
    try:
        return await analizar_imagen(jpeg, prompt, max_tokens=600)
    except Exception as e:
        log.error("Análisis de pantalla falló: %s", e)
        return "Tuve un problema analizando la pantalla."
