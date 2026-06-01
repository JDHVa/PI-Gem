"""
Memoria por proyecto (.gem.md).

Cuando GEM entra a un directorio, busca .gem.md y lo inyecta al contexto.
El usuario o GEM pueden escribir ahí instrucciones persistentes del proyecto.
"""

import logging
from pathlib import Path

log = logging.getLogger("gem.workspace")

NOMBRE_ARCHIVO = ".gem.md"


def leer_memoria(directorio: str) -> str | None:
    p = Path(directorio) / NOMBRE_ARCHIVO
    if not p.exists():
        return None
    try:
        contenido = p.read_text(encoding="utf-8", errors="replace").strip()
        if contenido:
            log.info("Memoria de proyecto cargada: %s (%d chars)", p, len(contenido))
        return contenido or None
    except Exception as e:
        log.warning("No se pudo leer %s: %s", p, e)
        return None


def escribir_memoria(directorio: str, contenido: str) -> bool:
    try:
        p = Path(directorio) / NOMBRE_ARCHIVO
        p.write_text(contenido, encoding="utf-8")
        log.info("Memoria guardada: %s", p)
        return True
    except Exception as e:
        log.error("No se pudo escribir %s: %s", p, e)
        return False


def resumen_proyecto(directorio: str) -> str:
    """Genera un resumen rápido de la estructura del proyecto sin LLM."""
    p = Path(directorio)
    if not p.exists():
        return ""

    info = []

    memoria = leer_memoria(directorio)
    if memoria:
        info.append(f"━━ .gem.md ━━\n{memoria[:500]}")

    archivos_clave = {
        "package.json": "Node.js",
        "Cargo.toml": "Rust",
        "requirements.txt": "Python",
        "go.mod": "Go",
        "pom.xml": "Java (Maven)",
        "build.gradle": "Java (Gradle)",
        "Gemfile": "Ruby",
        "composer.json": "PHP",
        "Makefile": "Make",
        "Dockerfile": "Docker",
        ".gitignore": "Git",
        "README.md": "Documentado",
        "tsconfig.json": "TypeScript",
    }

    techs = []
    for archivo, tech in archivos_clave.items():
        if (p / archivo).exists():
            techs.append(tech)
    if techs:
        info.append(f"Tecnologías: {', '.join(techs)}")

    try:
        items = sorted(p.iterdir())
        dirs = [i.name for i in items if i.is_dir() and not i.name.startswith(".")][:15]
        files = [i.name for i in items if i.is_file()][:15]
        info.append(f"Carpetas: {', '.join(dirs) if dirs else '(vacío)'}")
        info.append(f"Archivos raíz: {', '.join(files) if files else '(vacío)'}")
    except Exception:
        pass

    return "\n".join(info) if info else ""
