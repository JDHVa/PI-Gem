"""
Herramientas de Git para el agente GEM.
"""

import asyncio
import os
from pathlib import Path

TIMEOUT = 30


async def _git(args: list[str], cwd: str) -> dict:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=TIMEOUT)
        out = stdout.decode("utf-8", errors="replace").strip()
        err = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 0:
            return {"exito": False, "error": err or f"git exit code {proc.returncode}"}
        return {"exito": True, "resultado": out[:4000] if out else "(sin salida)"}
    except FileNotFoundError:
        return {"exito": False, "error": "Git no está instalado."}
    except asyncio.TimeoutError:
        return {"exito": False, "error": "Git timeout."}
    except Exception as e:
        return {"exito": False, "error": str(e)}


async def git_status(directorio: str) -> dict:
    return await _git(["status", "--short", "--branch"], directorio)


async def git_diff(directorio: str, archivo: str = "") -> dict:
    args = ["diff", "--stat"]
    if archivo:
        args = ["diff", archivo]
    return await _git(args, directorio)


async def git_diff_staged(directorio: str) -> dict:
    return await _git(["diff", "--cached", "--stat"], directorio)


async def git_log(directorio: str, n: int = 10) -> dict:
    return await _git(
        ["log", f"-{n}", "--oneline", "--decorate", "--graph"],
        directorio,
    )


async def git_add(directorio: str, archivos: str = ".") -> dict:
    return await _git(["add", archivos], directorio)


async def git_commit(directorio: str, mensaje: str) -> dict:
    return await _git(["commit", "-m", mensaje], directorio)


async def git_branch(directorio: str) -> dict:
    return await _git(["branch", "-a", "--list"], directorio)


async def git_stash(directorio: str, accion: str = "list") -> dict:
    if accion == "save":
        return await _git(["stash", "push", "-m", "GEM auto-stash"], directorio)
    elif accion == "pop":
        return await _git(["stash", "pop"], directorio)
    return await _git(["stash", "list"], directorio)
