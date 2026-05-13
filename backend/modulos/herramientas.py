"""
Herramientas del agente GEM.

Cambios vs versión anterior:
  · `eliminar` requiere confirmación EXTERNA real, no puede ser auto-confirmada por el LLM.
  · Workdir parametrizable para tests.
  · Cap de salida en bash más estricto (4000 chars).
"""

import asyncio
import os
import shutil
from pathlib import Path
from typing import Callable, Awaitable
from google.genai import types

WORKDIR = Path.home() / "GEM_workspace"
WORKDIR.mkdir(exist_ok=True)

# Callback opcional para que el orquestador confirme operaciones destructivas
# Signatura: async fn(accion: str, args: dict) -> bool
_confirm_callback: Callable[[str, dict], Awaitable[bool]] | None = None


def set_confirmacion_callback(
    cb: Callable[[str, dict], Awaitable[bool]] | None,
) -> None:
    """Registra la función que pide confirmación al usuario antes de operaciones destructivas."""
    global _confirm_callback
    _confirm_callback = cb


async def _confirmar(accion: str, args: dict) -> bool:
    """Devuelve True si está autorizada (o si no hay callback registrado: bloquea)."""
    if _confirm_callback is None:
        return False
    try:
        return await _confirm_callback(accion, args)
    except Exception:
        return False


async def bash(comando: str, workdir: str | None = None) -> dict:
    cwd = Path(workdir) if workdir else WORKDIR
    try:
        if os.name == "nt":
            proc = await asyncio.create_subprocess_exec(
                "powershell",
                "-NonInteractive",
                "-NoProfile",
                "-Command",
                comando,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
        else:
            proc = await asyncio.create_subprocess_shell(
                comando,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(cwd),
            )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        except asyncio.TimeoutError:
            proc.kill()
            return {"exito": False, "error": "Timeout de 120s. Proceso cancelado."}

        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        ok = proc.returncode == 0

        return {
            "exito": ok,
            "resultado": out[:4000] if out else "(sin salida)",
            "error": err[:1000] if err and not ok else None,
            "codigo": proc.returncode,
        }
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def leer_archivo(ruta: str) -> dict:
    try:
        p = _resolver(ruta)
        if not p.exists():
            return {"exito": False, "error": f"No existe: {p}"}
        if p.stat().st_size > 500_000:
            return {"exito": False, "error": "Archivo muy grande (>500 KB)."}
        return {
            "exito": True,
            "resultado": p.read_text(encoding="utf-8", errors="replace"),
        }
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def escribir_archivo(ruta: str, contenido: str) -> dict:
    try:
        p = _resolver(ruta)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contenido, encoding="utf-8")
        return {"exito": True, "resultado": f"Escrito: {p} ({len(contenido)} chars)"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def editar_archivo(ruta: str, buscar: str, reemplazar: str) -> dict:
    try:
        p = _resolver(ruta)
        if not p.exists():
            return {"exito": False, "error": f"No existe: {p}"}
        texto = p.read_text(encoding="utf-8", errors="replace")
        if buscar not in texto:
            return {"exito": False, "error": "Texto buscado no encontrado."}
        nuevo = texto.replace(buscar, reemplazar, 1)
        p.write_text(nuevo, encoding="utf-8")
        return {"exito": True, "resultado": f"Reemplazado en {p}"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def listar_directorio(ruta: str = ".") -> dict:
    try:
        p = _resolver(ruta)
        if not p.exists():
            return {"exito": False, "error": f"No existe: {p}"}
        items = []
        for item in sorted(p.iterdir()):
            tipo = "📁" if item.is_dir() else "📄"
            size = f" ({item.stat().st_size:,} B)" if item.is_file() else ""
            items.append(f"{tipo} {item.name}{size}")
        return {
            "exito": True,
            "resultado": "\n".join(items) or "(vacío)",
            "ruta": str(p),
        }
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def crear_directorio(ruta: str) -> dict:
    try:
        p = _resolver(ruta)
        p.mkdir(parents=True, exist_ok=True)
        return {"exito": True, "resultado": f"Creado: {p}"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def buscar_en_archivos(
    patron: str, directorio: str = ".", extension: str = ""
) -> dict:
    try:
        p = _resolver(directorio)
        glob = f"**/*{extension}" if extension else "**/*"
        coincidencias = []
        for archivo in p.glob(glob):
            if not archivo.is_file():
                continue
            try:
                texto = archivo.read_text(encoding="utf-8", errors="ignore")
                lineas = [
                    f"{archivo.relative_to(p)}:{i+1}: {l.strip()}"
                    for i, l in enumerate(texto.splitlines())
                    if patron.lower() in l.lower()
                ]
                coincidencias.extend(lineas[:5])
            except Exception:
                continue
            if len(coincidencias) > 50:
                break
        if not coincidencias:
            return {"exito": True, "resultado": "Sin resultados."}
        return {"exito": True, "resultado": "\n".join(coincidencias[:50])}
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def mover_archivo(origen: str, destino: str) -> dict:
    try:
        src = _resolver(origen)
        dst = _resolver(destino)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return {"exito": True, "resultado": f"Movido: {src} → {dst}"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def eliminar(ruta: str) -> dict:
    """Requiere confirmación REAL del usuario vía callback."""
    autorizado = await _confirmar("eliminar", {"ruta": ruta})
    if not autorizado:
        return {"exito": False, "error": "Usuario no autorizó la eliminación."}
    try:
        p = _resolver(ruta)
        if not p.exists():
            return {"exito": False, "error": f"No existe: {p}"}
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return {"exito": True, "resultado": f"Eliminado: {p}"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def abrir_app(nombre: str) -> dict:
    """
    Abre una app instalada en Windows.
    Prueba en orden:
      1. UWP apps (Spotify Store, Calculator, etc.)
      2. Start Menu shortcuts (.lnk)
      3. Comando directo (apps en PATH como code, chrome, notepad)
    """
    if os.name != "nt":
        proc = await asyncio.create_subprocess_shell(
            f'xdg-open "{nombre}" 2>/dev/null || open -a "{nombre}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return {
            "exito": proc.returncode == 0,
            "resultado": f"Abriendo {nombre}" if proc.returncode == 0 else None,
            "error": None if proc.returncode == 0 else f"No se encontró '{nombre}'",
        }

    script = f"""
$nombre = "{nombre}"
$matches = @()

# 1) UWP apps
try {{
    $uwp = Get-StartApps | Where-Object {{ $_.Name -like "*$nombre*" }} | Select-Object -First 1
    if ($uwp) {{
        Start-Process "shell:AppsFolder\\$($uwp.AppID)"
        Write-Output "OK_UWP: $($uwp.Name)"
        exit 0
    }}
}} catch {{}}

# 2) Start Menu shortcuts (.lnk)
$startPaths = @(
    "$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs",
    "$env:ProgramData\\Microsoft\\Windows\\Start Menu\\Programs"
)
foreach ($p in $startPaths) {{
    if (Test-Path $p) {{
        $lnk = Get-ChildItem -Path $p -Recurse -Filter "*.lnk" -ErrorAction SilentlyContinue |
               Where-Object {{ $_.BaseName -like "*$nombre*" }} | Select-Object -First 1
        if ($lnk) {{
            Start-Process $lnk.FullName
            Write-Output "OK_LNK: $($lnk.BaseName)"
            exit 0
        }}
    }}
}}

# 3) Comando directo
try {{
    Start-Process $nombre -ErrorAction Stop
    Write-Output "OK_CMD: $nombre"
    exit 0
}} catch {{}}

Write-Output "NO_ENCONTRADO"
exit 1
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "powershell",
            "-NonInteractive",
            "-NoProfile",
            "-Command",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
        out = stdout.decode("utf-8", errors="replace").strip()

        if proc.returncode == 0 and out.startswith("OK_"):
            metodo, nombre_real = out.split(":", 1)
            return {
                "exito": True,
                "resultado": f"Abriendo '{nombre_real.strip()}' ({metodo})",
            }
        return {"exito": False, "error": f"No encontré ninguna app llamada '{nombre}'."}
    except asyncio.TimeoutError:
        return {"exito": False, "error": "Timeout buscando la app."}
    except Exception as e:
        return {"exito": False, "error": str(e)}


# ── Helper ─────────────────────────────────────────────────────────────


def _resolver(ruta: str) -> Path:
    p = Path(ruta)
    return p if p.is_absolute() else WORKDIR / p


# ── Mapa nombre → función ──────────────────────────────────────────────

MAPA: dict[str, callable] = {
    "bash": bash,
    "abrir_app": abrir_app,
    "leer_archivo": leer_archivo,
    "escribir_archivo": escribir_archivo,
    "editar_archivo": editar_archivo,
    "listar_directorio": listar_directorio,
    "crear_directorio": crear_directorio,
    "buscar_en_archivos": buscar_en_archivos,
    "mover_archivo": mover_archivo,
    "eliminar": eliminar,
}


async def ejecutar(nombre: str, args: dict) -> dict:
    fn = MAPA.get(nombre)
    if not fn:
        return {"exito": False, "error": f"Herramienta desconocida: {nombre}"}
    try:
        return await fn(**args)
    except TypeError as e:
        return {"exito": False, "error": f"Args inválidos para {nombre}: {e}"}
    except Exception as e:
        return {"exito": False, "error": str(e)}


# ── Declaraciones para function calling ────────────────────────────────

DECLARACIONES = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="bash",
            description=(
                "Ejecuta un comando en la terminal del usuario. "
                "PowerShell en Windows, bash en Unix."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "comando": types.Schema(type="STRING"),
                    "workdir": types.Schema(type="STRING"),
                },
                required=["comando"],
            ),
        ),
        types.FunctionDeclaration(
            name="abrir_app",
            description=(
                "Abre una aplicación instalada en la computadora del usuario. "
                "Usa esto cuando el usuario pida 'abre X', 'abre Spotify', 'abre Chrome', etc. "
                "Funciona con apps UWP (Spotify, Calculator), shortcuts del Start Menu, "
                "y comandos en PATH (code, chrome, notepad). "
                "Prefiere esta herramienta sobre 'bash' para abrir aplicaciones."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "nombre": types.Schema(
                        type="STRING",
                        description="Nombre de la app (ej: 'Spotify', 'Chrome', 'Code', 'Notepad')",
                    ),
                },
                required=["nombre"],
            ),
        ),
        types.FunctionDeclaration(
            name="leer_archivo",
            description="Lee el contenido de un archivo de texto.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"ruta": types.Schema(type="STRING")},
                required=["ruta"],
            ),
        ),
        types.FunctionDeclaration(
            name="escribir_archivo",
            description="Crea o sobreescribe un archivo.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "ruta": types.Schema(type="STRING"),
                    "contenido": types.Schema(type="STRING"),
                },
                required=["ruta", "contenido"],
            ),
        ),
        types.FunctionDeclaration(
            name="editar_archivo",
            description="Reemplaza una cadena dentro de un archivo existente.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "ruta": types.Schema(type="STRING"),
                    "buscar": types.Schema(type="STRING"),
                    "reemplazar": types.Schema(type="STRING"),
                },
                required=["ruta", "buscar", "reemplazar"],
            ),
        ),
        types.FunctionDeclaration(
            name="listar_directorio",
            description="Lista archivos y carpetas.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"ruta": types.Schema(type="STRING")},
            ),
        ),
        types.FunctionDeclaration(
            name="crear_directorio",
            description="Crea una carpeta.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"ruta": types.Schema(type="STRING")},
                required=["ruta"],
            ),
        ),
        types.FunctionDeclaration(
            name="buscar_en_archivos",
            description="Busca un patrón en archivos de un directorio.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "patron": types.Schema(type="STRING"),
                    "directorio": types.Schema(type="STRING"),
                    "extension": types.Schema(type="STRING"),
                },
                required=["patron"],
            ),
        ),
        types.FunctionDeclaration(
            name="mover_archivo",
            description="Mueve o renombra archivo o carpeta.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "origen": types.Schema(type="STRING"),
                    "destino": types.Schema(type="STRING"),
                },
                required=["origen", "destino"],
            ),
        ),
        types.FunctionDeclaration(
            name="eliminar",
            description="Elimina archivo o carpeta. Requiere confirmación del usuario.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"ruta": types.Schema(type="STRING")},
                required=["ruta"],
            ),
        ),
    ]
)
