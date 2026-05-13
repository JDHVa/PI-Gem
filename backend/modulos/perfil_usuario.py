"""
Perfil visual del usuario — aprende y recuerda todo con el tiempo.

Almacena observaciones en ChromaDB (colección: perfil_visual).
Construye un modelo de "lo normal" del usuario para detectar desviaciones.

Registro inicial:
  perfil.registrar_inicial(descripcion_texto, frame_bgr)
    → Guarda la línea base de apariencia, cuarto y estado habitual

Observaciones continuas:
  perfil.guardar_observacion(obs_dict)
    → Cada análisis de Gemini Vision se almacena

Detección de cambios:
  perfil.detectar_cambios(obs_actual) → list[str]
    → Compara lo actual contra la línea base aprendida
"""

import json
import logging
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

import chromadb
import numpy as np

from backend.config import ajustes

log = logging.getLogger("gem.perfil")


class PerfilUsuario:
    def __init__(self):
        cliente = chromadb.PersistentClient(path=ajustes.chromadb_path)
        self._col = cliente.get_or_create_collection("perfil_visual")
        self._baseline: dict | None = None
        self._cargar_baseline()

    # ── Registro inicial ───────────────────────────────────────────────

    async def registrar_inicial(self, descripcion: str, observacion: dict) -> None:
        """
        Guarda la línea base del usuario.
        Se llama al hacer clic en "Registrar mi perfil".
        """
        baseline = {
            "tipo":        "baseline",
            "timestamp":   datetime.now().isoformat(),
            "descripcion": descripcion,
            **observacion,
        }
        self._col.upsert(
            ids=["baseline"],
            documents=[json.dumps(baseline, ensure_ascii=False)],
            metadatas=[{"tipo": "baseline", "timestamp": baseline["timestamp"]}],
        )
        self._baseline = baseline
        log.info("Perfil baseline registrado")

    def tiene_baseline(self) -> bool:
        return self._baseline is not None

    def get_baseline(self) -> dict | None:
        return self._baseline

    def _cargar_baseline(self) -> None:
        try:
            r = self._col.get(ids=["baseline"])
            if r["documents"]:
                self._baseline = json.loads(r["documents"][0])
        except Exception:
            self._baseline = None

    # ── Observaciones continuas ────────────────────────────────────────

    async def guardar_observacion(self, obs: dict) -> None:
        ahora     = datetime.now()
        obs_id    = f"obs_{ahora.strftime('%Y%m%d_%H%M%S')}"
        obs_full  = {
            "timestamp":   ahora.isoformat(),
            "hora_dia":    _hora_del_dia(ahora.hour),
            "dia_semana":  ahora.strftime("%A"),
            **obs,
        }
        self._col.add(
            ids=[obs_id],
            documents=[json.dumps(obs_full, ensure_ascii=False)],
            metadatas={"tipo": "observacion", "timestamp": obs_full["timestamp"]},
        )

    async def observaciones_recientes(self, horas: int = 24) -> list[dict]:
        """Devuelve observaciones de las últimas N horas."""
        try:
            resultado = self._col.get(where={"tipo": "observacion"})
            limite    = datetime.now() - timedelta(hours=horas)
            obs = []
            for doc in (resultado["documents"] or []):
                try:
                    d = json.loads(doc)
                    if datetime.fromisoformat(d["timestamp"]) >= limite:
                        obs.append(d)
                except Exception:
                    continue
            return sorted(obs, key=lambda x: x["timestamp"])
        except Exception:
            return []

    # ── Detección de cambios vs baseline ──────────────────────────────

    async def detectar_cambios(self, obs_actual: dict) -> list[str]:
        """
        Compara observación actual contra la línea base.
        Devuelve lista de cambios notables en lenguaje natural.
        """
        if not self._baseline:
            return []

        cambios: list[str] = []
        b = self._baseline

        # Ubicación / cuarto
        ub_base  = b.get("ubicacion", "")
        ub_actual = obs_actual.get("ubicacion", "")
        if ub_base and ub_actual and not _similares(ub_base, ub_actual):
            cambios.append(f"cambio de ubicación: normalmente estás en '{ub_base}', ahora en '{ub_actual}'")

        # Apariencia (cabello, ropa, accesorios)
        ap_base   = b.get("apariencia", {})
        ap_actual = obs_actual.get("apariencia", {})
        for campo, etiqueta in [("cabello", "cabello"), ("accesorios", "accesorios"), ("ropa", "ropa")]:
            v_base   = ap_base.get(campo, "")
            v_actual = ap_actual.get(campo, "")
            if v_base and v_actual and not _similares(v_base, v_actual):
                cambios.append(f"{etiqueta} diferente: antes '{v_base}', ahora '{v_actual}'")

        # Energía
        e_base   = b.get("energia", "media")
        e_actual = obs_actual.get("energia", "media")
        if e_actual == "baja" and e_base != "baja":
            cambios.append("el usuario parece más cansado/con menos energía de lo habitual")

        # Personas extra
        extra = obs_actual.get("personas_extra", False)
        if extra:
            cambios.append("hay alguien más en cámara")

        return cambios

    # ── Resumen del perfil para el system prompt ───────────────────────

    async def resumen_para_prompt(self) -> str:
        if not self._baseline:
            return "Sin perfil visual registrado."
        b = self._baseline
        ap = b.get("apariencia", {})
        lineas = [
            f"Descripción inicial del usuario: {b.get('descripcion', 'N/A')}",
            f"Ubicación habitual: {b.get('ubicacion', 'N/A')}",
            f"Apariencia habitual: cabello={ap.get('cabello','N/A')}, accesorios={ap.get('accesorios','ninguno')}",
            f"Energía habitual: {b.get('energia', 'N/A')}",
            f"Registrado: {b.get('timestamp', 'N/A')[:10]}",
        ]
        return "\n".join(lineas)

    # ── Estadísticas ───────────────────────────────────────────────────

    def estadisticas(self) -> dict:
        try:
            total = self._col.count()
            return {
                "tiene_baseline": self.tiene_baseline(),
                "total_observaciones": max(0, total - (1 if self.tiene_baseline() else 0)),
            }
        except Exception:
            return {"tiene_baseline": False, "total_observaciones": 0}


# ── Helpers ────────────────────────────────────────────────────────────

def _hora_del_dia(hora: int) -> str:
    if 6 <= hora < 12:  return "mañana"
    if 12 <= hora < 18: return "tarde"
    if 18 <= hora < 22: return "noche"
    return "madrugada"


def _similares(a: str, b: str, umbral: float = 0.5) -> bool:
    """Comparación simple de similitud entre dos strings."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return True
    palabras_a = set(a.split())
    palabras_b = set(b.split())
    if not palabras_a or not palabras_b:
        return False
    interseccion = palabras_a & palabras_b
    return len(interseccion) / max(len(palabras_a), len(palabras_b)) >= umbral
