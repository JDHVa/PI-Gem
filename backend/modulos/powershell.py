import asyncio
import subprocess
import logging
from backend.config import ajustes
from backend.modulos.gemini_cliente import (
    analizar_riesgo_comando,
    generar_correccion_comando,
)

log = logging.getLogger("gem.powershell")


async def clasificar_riesgo(comando: str) -> str:
    return await analizar_riesgo_comando(comando)


def _ejecutar_sync(comando: str) -> tuple[str, str, int]:
    resultado = subprocess.run(
        [
            "powershell",
            "-NonInteractive",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            comando,
        ],
        capture_output=True,
        text=True,
        timeout=ajustes.ps_timeout_s,
        encoding="utf-8",
        errors="replace",
    )
    return resultado.stdout.strip(), resultado.stderr.strip(), resultado.returncode


async def ejecutar(comando: str) -> dict:
    loop = asyncio.get_event_loop()
    try:
        stdout, stderr, codigo = await loop.run_in_executor(
            None, _ejecutar_sync, comando
        )
        log.info("PS exec | code=%s | cmd=%s", codigo, comando[:80])
        return {
            "stdout": stdout,
            "stderr": stderr,
            "codigo": codigo,
            "exito": codigo == 0,
            "comando": comando,
        }
    except subprocess.TimeoutExpired:
        return {
            "exito": False,
            "stderr": f"Timeout: comando tardó más de {ajustes.ps_timeout_s}s",
            "stdout": "",
            "codigo": -1,
            "comando": comando,
        }
    except FileNotFoundError:
        return {
            "exito": False,
            "stderr": "PowerShell no encontrado en el sistema (¿Windows?)",
            "stdout": "",
            "codigo": -1,
            "comando": comando,
        }
    except Exception as e:
        return {
            "exito": False,
            "stderr": str(e),
            "stdout": "",
            "codigo": -1,
            "comando": comando,
        }


async def auto_healing(comando_original: str, error: str) -> dict:
    comando_actual = comando_original
    for intento in range(1, ajustes.ps_max_retries + 1):
        log.info("Auto-healing intento %d", intento)
        comando_fix = await generar_correccion_comando(comando_actual, error)
        if not comando_fix or comando_fix == comando_actual:
            break
        resultado = await ejecutar(comando_fix)
        if resultado["exito"]:
            return {**resultado, "intentos": intento, "comando_final": comando_fix}
        error = resultado["stderr"]
        comando_actual = comando_fix

    return {
        "exito": False,
        "stderr": f"Falló después de {ajustes.ps_max_retries} intentos. Último error: {error}",
        "stdout": "",
        "codigo": -1,
        "intentos": ajustes.ps_max_retries,
        "comando": comando_actual,
    }


async def ejecutar_con_healing(comando: str) -> dict:
    resultado = await ejecutar(comando)
    if not resultado["exito"]:
        return await auto_healing(comando, resultado["stderr"])
    return {**resultado, "intentos": 1, "comando_final": comando}
