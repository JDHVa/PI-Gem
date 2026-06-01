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
from backend.modulos import git_tools

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


async def editar_archivo(
    ruta: str, buscar: str, reemplazar: str, crear_si_no_existe: bool = False
) -> dict:
    try:
        p = _resolver(ruta)
        if not p.exists():
            if crear_si_no_existe:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(reemplazar, encoding="utf-8")
                return {"exito": True, "resultado": f"Archivo creado: {p}"}
            return {"exito": False, "error": f"No existe: {p}"}
        texto = p.read_text(encoding="utf-8", errors="replace")
        if buscar not in texto:
            similares = [
                l.strip()
                for l in texto.splitlines()
                if any(palabra in l.lower() for palabra in buscar.lower().split()[:3])
            ][:3]
            msg = "Texto buscado no encontrado."
            if similares:
                msg += f" Líneas similares:\n" + "\n".join(
                    f"  · {s[:100]}" for s in similares
                )
            return {"exito": False, "error": msg}
        conteo = texto.count(buscar)
        nuevo = texto.replace(buscar, reemplazar)
        p.write_text(nuevo, encoding="utf-8")
        return {
            "exito": True,
            "resultado": f"Reemplazado en {p} ({conteo} ocurrencia{'s' if conteo > 1 else ''})",
        }
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
    patron: str,
    directorio: str = ".",
    extension: str = "",
    contexto: int = 3,
    max_resultados: int = 30,
) -> dict:
    try:
        p = _resolver(directorio)
        glob_pat = f"**/*{extension}" if extension else "**/*"
        coincidencias = []
        archivos_revisados = 0

        for archivo in p.glob(glob_pat):
            if not archivo.is_file():
                continue
            if archivo.stat().st_size > 500_000:
                continue
            try:
                lineas = archivo.read_text(
                    encoding="utf-8", errors="ignore"
                ).splitlines()
                for i, linea in enumerate(lineas):
                    if patron.lower() in linea.lower():
                        inicio = max(0, i - contexto)
                        fin = min(len(lineas), i + contexto + 1)
                        bloque = []
                        for j in range(inicio, fin):
                            marca = ">>>" if j == i else "   "
                            bloque.append(f"{marca} {j+1:4d} | {lineas[j]}")
                        rel = archivo.relative_to(p)
                        coincidencias.append(f"── {rel}:{i+1} ──\n" + "\n".join(bloque))
                        if len(coincidencias) >= max_resultados:
                            break
            except Exception:
                continue
            archivos_revisados += 1
            if len(coincidencias) >= max_resultados:
                break

        if not coincidencias:
            return {
                "exito": True,
                "resultado": f"Sin resultados para '{patron}' en {archivos_revisados} archivos.",
            }
        return {
            "exito": True,
            "resultado": "\n\n".join(coincidencias),
            "total": len(coincidencias),
            "archivos_revisados": archivos_revisados,
        }
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
async def git_status(directorio: str = ".") -> dict:
    return await git_tools.git_status(str(_resolver(directorio)))


async def git_diff(directorio: str = ".", archivo: str = "") -> dict:
    return await git_tools.git_diff(str(_resolver(directorio)), archivo)


async def git_log(directorio: str = ".", n: int = 10) -> dict:
    return await git_tools.git_log(str(_resolver(directorio)), n)


async def git_add(directorio: str = ".", archivos: str = ".") -> dict:
    return await git_tools.git_add(str(_resolver(directorio)), archivos)


async def git_commit(directorio: str = ".", mensaje: str = "") -> dict:
    if not mensaje:
        return {"exito": False, "error": "Necesito un mensaje de commit."}
    return await git_tools.git_commit(str(_resolver(directorio)), mensaje)


async def git_branch(directorio: str = ".") -> dict:
    return await git_tools.git_branch(str(_resolver(directorio)))


from backend.modulos import workspace_memory


async def proyecto_info(directorio: str = ".") -> dict:
    info = workspace_memory.resumen_proyecto(str(_resolver(directorio)))
    return {
        "exito": True,
        "resultado": info or "No se encontró información del proyecto.",
    }


async def proyecto_memoria_leer(directorio: str = ".") -> dict:
    mem = workspace_memory.leer_memoria(str(_resolver(directorio)))
    if mem is None:
        return {"exito": True, "resultado": "No hay .gem.md en este directorio."}
    return {"exito": True, "resultado": mem}


async def proyecto_memoria_escribir(directorio: str = ".", contenido: str = "") -> dict:
    ok = workspace_memory.escribir_memoria(str(_resolver(directorio)), contenido)
    return {
        "exito": ok,
        "resultado": ".gem.md actualizado." if ok else "Error escribiendo.",
    }


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
    "git_status": git_status,
    "git_diff": git_diff,
    "git_log": git_log,
    "git_add": git_add,
    "git_commit": git_commit,
    "git_branch": git_branch,
    "proyecto_info": proyecto_info,
    "proyecto_memoria_leer": proyecto_memoria_leer,
    "proyecto_memoria_escribir": proyecto_memoria_escribir,
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
            description=(
                "Busca un patrón en archivos de un directorio. "
                "Devuelve las coincidencias con ±3 líneas de contexto. "
                "Ideal para encontrar funciones, variables, imports, bugs."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "patron": types.Schema(type="STRING", description="Texto a buscar"),
                    "directorio": types.Schema(
                        type="STRING", description="Carpeta donde buscar"
                    ),
                    "extension": types.Schema(
                        type="STRING",
                        description="Filtrar por extensión (.py, .js, etc.)",
                    ),
                    "contexto": types.Schema(
                        type="INTEGER",
                        description="Líneas de contexto arriba/abajo (default 3)",
                    ),
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
        types.FunctionDeclaration(
            name="git_status",
            description="Muestra el estado de git (archivos modificados, branch actual).",
            parameters=types.Schema(
                type="OBJECT",
                properties={"directorio": types.Schema(type="STRING")},
            ),
        ),
        types.FunctionDeclaration(
            name="git_diff",
            description="Muestra los cambios no commiteados. Si se da un archivo, muestra solo ese diff.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "directorio": types.Schema(type="STRING"),
                    "archivo": types.Schema(
                        type="STRING", description="Archivo específico (opcional)"
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="git_log",
            description="Muestra el historial de commits recientes.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "directorio": types.Schema(type="STRING"),
                    "n": types.Schema(
                        type="INTEGER", description="Número de commits (default 10)"
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="git_add",
            description="Agrega archivos al staging area de git.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "directorio": types.Schema(type="STRING"),
                    "archivos": types.Schema(
                        type="STRING",
                        description="Archivos a agregar (default '.' = todos)",
                    ),
                },
            ),
        ),
        types.FunctionDeclaration(
            name="git_commit",
            description="Crea un commit con los archivos en staging.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "directorio": types.Schema(type="STRING"),
                    "mensaje": types.Schema(
                        type="STRING", description="Mensaje del commit"
                    ),
                },
                required=["mensaje"],
            ),
        ),
        types.FunctionDeclaration(
            name="git_branch",
            description="Lista las ramas del repositorio.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"directorio": types.Schema(type="STRING")},
            ),
        ),
        types.FunctionDeclaration(
            name="proyecto_info",
            description="Muestra un resumen del proyecto: tecnologías, estructura, .gem.md.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"directorio": types.Schema(type="STRING")},
            ),
        ),
        types.FunctionDeclaration(
            name="proyecto_memoria_leer",
            description="Lee el archivo .gem.md del proyecto (instrucciones persistentes).",
            parameters=types.Schema(
                type="OBJECT",
                properties={"directorio": types.Schema(type="STRING")},
            ),
        ),
        types.FunctionDeclaration(
            name="proyecto_memoria_escribir",
            description=(
                "Escribe o actualiza el .gem.md del proyecto. "
                "Usa esto para guardar instrucciones que deben persistir: "
                "convenciones del proyecto, comandos frecuentes, notas técnicas."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "directorio": types.Schema(type="STRING"),
                    "contenido": types.Schema(
                        type="STRING", description="Contenido markdown del .gem.md"
                    ),
                },
                required=["contenido"],
            ),
        ),
        types.FunctionDeclaration(
            name="editar_archivo",
            description=(
                "Reemplaza texto dentro de un archivo. Si el texto no se encuentra, "
                "muestra líneas similares para ayudar. Puede crear el archivo si no existe."
            ),
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "ruta": types.Schema(type="STRING"),
                    "buscar": types.Schema(
                        type="STRING", description="Texto exacto a encontrar"
                    ),
                    "reemplazar": types.Schema(
                        type="STRING", description="Texto que lo sustituye"
                    ),
                    "crear_si_no_existe": types.Schema(
                        type="BOOLEAN",
                        description="Crear archivo si no existe (default false)",
                    ),
                },
                required=["ruta", "buscar", "reemplazar"],
            ),
        ),
    ]
)
