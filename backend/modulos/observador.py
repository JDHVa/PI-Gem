"""
Observador Proactivo de GEM.

Usa Gemini Vision SOLO cuando MediaPipe detecta pre-triggers reales.
Nunca en intervalos ciegos.

Cambios:
  · Usa analizar_imagen() que redimensiona antes de enviar → -70% tokens.
  · Cooldown más conservador para Vertex (15 min entre triggers).
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Callable

import cv2
import numpy as np

from backend.config import ajustes
from backend.modulos.perfil_usuario import PerfilUsuario
from backend.modulos.gemini_cliente import analizar_imagen

log = logging.getLogger("gem.observador")

MIN_INTERVALO_ANALISIS = 180
MAX_ANALISIS_POR_HORA  = 15

PROMPT_ANALISIS = """\
Analiza esta imagen y devuelve SOLO un objeto JSON válido, sin texto adicional.

{
  "persona_presente": true,
  "emocion": "neutro",
  "energia": "media",
  "apariencia": {
    "cabello": "descripción corta",
    "ropa": "color y tipo",
    "accesorios": "gafas/audífonos/ninguno"
  },
  "ubicacion": "ambiente visible",
  "iluminacion": "natural",
  "actividad": "trabajando",
  "postura": "erguido",
  "personas_extra": false,
  "notable": null
}

Valores:
- emocion: alegre|triste|enojado|ansioso|confundido|neutro|pensativo|dormido
- energia: alta|media|baja
- iluminacion: natural|artificial|oscura|mixta
- actividad: trabajando|descansando|comiendo|leyendo|jugando|hablando|otro
- postura: erguido|reclinado|inclinado_adelante|acostado
- notable: string si hay algo inusual, null si nada
"""


class ObservadorProactivo:
    def __init__(self, perfil: PerfilUsuario, on_trigger: Callable):
        self._perfil      = perfil
        self._on_trigger  = on_trigger
        self._activo      = False
        self._proactivo   = False
        self._tarea: asyncio.Task | None = None

        self._ultimo_analisis    = 0.0
        self._analisis_esta_hora = deque(maxlen=MAX_ANALISIS_POR_HORA)
        self._ultimo_trigger     = 0.0
        self._cooldown_trigger   = 900    # 15 min (era 10)

        self._emocion_actual     = "neutro"
        self._emocion_desde      = time.time()
        self._face_ausente_desde: float | None = None
        self._ultimo_histograma: np.ndarray | None = None
        self._hist_timestamp = 0.0
        self._razones_pendientes: list[str] = []

        self.frame_actual: np.ndarray | None = None

    def iniciar(self):
        self._activo = True
        self._tarea = asyncio.create_task(self._loop())

    def detener(self):
        self._activo = False
        if self._tarea:
            self._tarea.cancel()

    def set_proactivo(self, valor: bool):
        self._proactivo = valor
        log.info("Modo proactivo: %s", "ON" if valor else "OFF")

    def get_proactivo(self) -> bool:
        return self._proactivo

    def actualizar_estado_mediapipe(self, estado: dict, frame_bgr: np.ndarray | None = None):
        if frame_bgr is not None:
            self.frame_actual = frame_bgr.copy()

        emocion_nueva   = estado.get("emocion", "neutro")
        rostro_presente = estado.get("rostro_detectado", False)

        if emocion_nueva != self._emocion_actual:
            self._emocion_actual = emocion_nueva
            self._emocion_desde  = time.time()

        if not rostro_presente:
            if self._face_ausente_desde is None:
                self._face_ausente_desde = time.time()
        else:
            if self._face_ausente_desde is not None:
                ausencia = time.time() - self._face_ausente_desde
                if ausencia > 120:
                    self._face_ausente_desde = None
                    if self._proactivo:
                        asyncio.create_task(
                            self._disparar_trigger("¡Bienvenido de vuelta!", "regreso")
                        )
                else:
                    self._face_ausente_desde = None

        if frame_bgr is not None:
            self._chequear_cambio_fondo(frame_bgr)

    def _chequear_cambio_fondo(self, frame: np.ndarray):
        h = frame.shape[0]
        fondo = frame[:h//2, :]
        hist  = cv2.calcHist([cv2.cvtColor(fondo, cv2.COLOR_BGR2HSV)],
                             [0, 1], None, [30, 32], [0, 180, 0, 256])
        hist  = cv2.normalize(hist, hist).flatten()

        if self._ultimo_histograma is not None:
            correlacion = cv2.compareHist(
                self._ultimo_histograma.reshape(30, 32),
                hist.reshape(30, 32),
                cv2.HISTCMP_CORREL,
            )
            if correlacion < 0.4:
                log.info("Cambio de fondo (corr=%.2f)", correlacion)
                self._razones_pendientes.append("cambio_fondo")

        if time.time() - self._hist_timestamp > 30:
            self._ultimo_histograma = hist
            self._hist_timestamp    = time.time()

    async def _loop(self):
        while self._activo:
            await asyncio.sleep(15)

            if not self._proactivo or self.frame_actual is None:
                continue

            razon = self._evaluar_trigger()
            if razon is None:
                continue

            ahora = time.time()
            if ahora - self._ultimo_analisis < MIN_INTERVALO_ANALISIS:
                continue

            analisis_recientes = [t for t in self._analisis_esta_hora if ahora - t < 3600]
            if len(analisis_recientes) >= MAX_ANALISIS_POR_HORA:
                log.warning("Límite de análisis/hora alcanzado")
                continue

            await self._analizar_y_trigger(razon)

    def _evaluar_trigger(self) -> str | None:
        if self._razones_pendientes:
            return self._razones_pendientes.pop(0)

        if self._emocion_actual in ("triste", "ansioso", "enojado"):
            if time.time() - self._emocion_desde > 90:
                return f"emocion_sostenida_{self._emocion_actual}"

        if self._face_ausente_desde and time.time() - self._face_ausente_desde > 180:
            return "face_ausente"

        return None

    async def _analizar_y_trigger(self, razon: str):
        log.info("Analizando con Gemini Vision (razón: %s)", razon)
        self._ultimo_analisis = time.time()
        self._analisis_esta_hora.append(self._ultimo_analisis)

        obs = await self._gemini_vision(self.frame_actual)
        if obs is None:
            return

        await self._perfil.guardar_observacion(obs)
        cambios = await self._perfil.detectar_cambios(obs)
        await self._generar_mensaje(obs, cambios, razon)

    async def _gemini_vision(self, frame_bgr: np.ndarray) -> dict | None:
        try:
            ok, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                return None
            jpeg_bytes = bytes(buf)

            texto = await analizar_imagen(jpeg_bytes, PROMPT_ANALISIS, max_tokens=400)
            texto = texto.replace("```json", "").replace("```", "").strip()
            return json.loads(texto)
        except json.JSONDecodeError as e:
            log.warning("Gemini Vision JSON inválido: %s", e)
            return None
        except Exception as e:
            log.error("Gemini Vision falló: %s", e)
            return None

    async def _generar_mensaje(self, obs: dict, cambios: list[str], razon: str):
        ahora = time.time()
        if ahora - self._ultimo_trigger < self._cooldown_trigger:
            return

        tipo, mensaje = "notable", None

        if obs.get("personas_extra"):
            tipo, mensaje = "persona_extra", "Oye, veo que hay alguien más contigo. ¿Me presentas?"
        elif any("ubicación" in c for c in cambios):
            tipo = "cambio_ubicacion"
            ub = obs.get("ubicacion", "otro lugar")
            mensaje = f"Veo que cambiaste de lugar. Parece que estás en {ub}. ¿Todo bien?"
        elif any("cabello" in c or "accesorios" in c for c in cambios):
            tipo = "cambio_apariencia"
            detalle = next((c for c in cambios if "cabello" in c or "accesorios" in c), "")
            mensaje = f"Noto algo diferente en ti — {detalle}. ¿Te hiciste algo?"
        elif "emocion_sostenida" in razon:
            tipo = "estado_animo"
            msgs = {
                "triste":  "Llevas un rato con cara de pocos amigos. ¿Estás bien?",
                "ansioso": "Te noto un poco ansioso. ¿Todo en orden?",
                "enojado": "Pareces molesto con algo. ¿Quieres contarme?",
            }
            mensaje = msgs.get(self._emocion_actual, f"Te noto {self._emocion_actual}. ¿Todo bien?")
        elif obs.get("energia") == "baja":
            tipo, mensaje = "cansancio", "Pareces cansado. ¿Quieres tomar un descanso?"
        elif obs.get("notable"):
            tipo, mensaje = "notable", f"Oye, noté algo: {obs['notable']}. ¿Todo bien?"

        if mensaje:
            self._ultimo_trigger = ahora
            log.info("Trigger proactivo (%s): %s", tipo, mensaje)
            await self._disparar_trigger(mensaje, tipo)

    async def _disparar_trigger(self, mensaje: str, tipo: str):
        try:
            await self._on_trigger(mensaje, tipo)
        except Exception as e:
            log.error("Error en on_trigger: %s", e)
