"""
Skills: rutinas reutilizables que el usuario guarda por nombre.

Ejemplo: "guardar rutina de mañana: abre VSCode, Spotify y Chrome"
         → se guarda en data/skills.json
         "ejecuta rutina de mañana"
         → corre los comandos guardados sin gastar tokens del LLM

Storage: JSON plano para inspección manual fácil.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from backend.config import ajustes

log = logging.getLogger("gem.skills")

_SKILLS_PATH = Path(ajustes.chromadb_path).parent / "skills.json"


class Skills:
    def __init__(self, path: Path | None = None):
        self._path = path or _SKILLS_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict] = self._cargar()

    def _cargar(self) -> dict[str, dict]:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("Skills inválidos: %s", e)
            return {}

    def _persistir(self) -> None:
        try:
            self._path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            log.error("No se pudo guardar skills: %s", e)

    def listar(self) -> list[dict]:
        return [
            {"nombre": k, "descripcion": v.get("descripcion", ""),
             "pasos": len(v.get("comandos", []))}
            for k, v in self._cache.items()
        ]

    def obtener(self, nombre: str) -> dict | None:
        return self._cache.get(_norm(nombre))

    def guardar(self, nombre: str, comandos: list[str], descripcion: str = "") -> None:
        clave = _norm(nombre)
        self._cache[clave] = {
            "descripcion": descripcion or nombre,
            "comandos":    comandos,
            "creado":      datetime.now().isoformat(),
        }
        self._persistir()
        log.info("Skill guardada: %s (%d comandos)", clave, len(comandos))

    def eliminar(self, nombre: str) -> bool:
        clave = _norm(nombre)
        if clave in self._cache:
            del self._cache[clave]
            self._persistir()
            return True
        return False


def _norm(nombre: str) -> str:
    return nombre.strip().lower()
