"""
Orquestador GEM.

Cambios principales vs versión anterior:
  · Usa AgenteGEM (function calling) en lugar del flujo [CMD:...]
  · Persiste historial entre reinicios (HistorialPersistente)
  · Resume automáticamente cuando el historial supera N turnos (ahorra tokens)
  · Soporta skills (rutinas guardadas) sin gastar tokens del LLM
  · Soporta screenshot bajo demanda
  · Pide confirmación REAL al usuario para operaciones destructivas
"""

import asyncio
import re
import logging
import numpy as np
from typing import Any

from backend.config import ajustes
from backend.modulos.gemini_cliente import generar_respuesta, resumir_historial
from backend.modulos.audio import ModuloAudio
from backend.modulos.memoria import MemoriaRAG, HistorialPersistente
from backend.modulos.vision import ModuloVision
from backend.modulos.perfil_usuario import PerfilUsuario
from backend.modulos.observador import ObservadorProactivo
from backend.modulos.broadcaster import Broadcaster
from backend.modulos.agente import AgenteGEM
from backend.modulos.skills import Skills
from backend.modulos import herramientas as tools
from backend.modulos import screenshot
from backend.prompts.system_prompt import construir as construir_prompt

log = logging.getLogger("gem.orquestador")

EMOCION_INICIO = "alegre"
EMOCION_PROCESANDO = "pensativo"
EMOCION_HABLANDO = "hablando"
EMOCION_ERROR = "confundido"

MAPA_ESPEJO = {
    "alegre": "alegre",
    "neutro": "neutro",
    "triste": "triste",
    "enojado": "confundido",
    "ansioso": "ansioso",
    "confundido": "confundido",
    "dormido": "dormido",
    "pensativo": "pensativo",
}

# Frases que indican intención agéntica → enrutar al agente
_REGEX_AGENTE = re.compile(
    r"\b(crea|abre|abrir|inicia|lanza|ejecuta|corre|instala|busca en|lista|"
    r"escribe|edita|mueve|renombra|elimina|borra|cierra|"
    r"haz|hazme|carpeta|archivo|script|comando|powershell|terminal|aplicaci[oó]n|app)\b",
    re.IGNORECASE,
)

# Patrones para skills
_REGEX_GUARDAR_SKILL = re.compile(
    r"guarda(?:r)?\s+(?:la\s+)?rutina\s+([^:]+?):\s*(.+)",
    re.IGNORECASE | re.DOTALL,
)
_REGEX_EJECUTAR_SKILL = re.compile(
    r"(?:ejecuta|corre|haz)\s+(?:la\s+)?rutina\s+(.+)",
    re.IGNORECASE,
)
_REGEX_SCREENSHOT = re.compile(
    r"(?:mira|revisa|ve|analiza|que ves)\s+(?:mi\s+)?(?:pantalla|screen)",
    re.IGNORECASE,
)


class Orquestador:
    def __init__(self, broadcaster: Broadcaster):
        self._broadcaster = broadcaster
        self._loop: asyncio.AbstractEventLoop | None = None
        self._historial_persistente = HistorialPersistente()
        self._historial: list[dict] = self._historial_persistente.cargar()
        self._memoria = MemoriaRAG()
        self._vision = ModuloVision()
        self._perfil = PerfilUsuario()
        self._skills = Skills()
        self._agente = AgenteGEM()
        self._audio: ModuloAudio | None = None
        self._observador: ObservadorProactivo | None = None
        self._procesando = False
        self._silenciado = False
        self._emocion_gem = EMOCION_INICIO
        self._tarea_idle: asyncio.Task | None = None
        # Para confirmaciones interactivas
        self._confirmaciones_pendientes: dict[str, asyncio.Future] = {}

    async def iniciar(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._audio = ModuloAudio(callback_voz=self._on_voz, loop=self._loop)
        self._audio.on_tts_amplitud = self._enviar_lipsync
        self._audio.on_estado_vad = self._enviar_estado_vad

        self._observador = ObservadorProactivo(
            perfil=self._perfil,
            on_trigger=self._on_trigger_proactivo,
        )
        self._vision.on_estado_actualizado = (
            self._observador.actualizar_estado_mediapipe
        )

        try:
            self._vision.iniciar()
        except Exception as e:
            log.warning("Visión no disponible: %s", e)

        try:
            self._audio.iniciar()
        except Exception as e:
            log.error("Audio no disponible: %s", e)

        self._observador.iniciar()

        tools.set_confirmacion_callback(self._pedir_confirmacion)

        await self._set_emocion(EMOCION_INICIO)
        self._tarea_idle = asyncio.create_task(self._loop_espejo_emocion())

        if self._perfil.tiene_baseline():
            asyncio.create_task(self._saludo_inicial())

    async def detener(self) -> None:
        if self._tarea_idle:
            self._tarea_idle.cancel()
        if self._observador:
            self._observador.detener()
        if self._audio:
            self._audio.detener()
        self._vision.detener()
        self._historial_persistente.guardar(self._historial)

    async def _saludo_inicial(self):
        await asyncio.sleep(2)
        resumen = await self._perfil.resumen_para_prompt()
        await self._responder(
            f"¡Hola! Ya estoy listo. {resumen[:80] if resumen else ''}"
        )

    # ── Emociones ──────────────────────────────────────────────────────

    async def _set_emocion(self, emocion: str):
        if emocion == self._emocion_gem:
            return
        self._emocion_gem = emocion
        await self._broadcaster.broadcast({"tipo": "expresion", "emocion": emocion})

    async def _set_emocion_idle(self):
        emocion_usuario = self._vision.get_estado().get("emocion", "neutro")
        await self._set_emocion(MAPA_ESPEJO.get(emocion_usuario, "alegre"))

    async def _loop_espejo_emocion(self):
        while True:
            await asyncio.sleep(4)
            if not self._procesando and self._emocion_gem not in (
                EMOCION_HABLANDO,
                EMOCION_PROCESANDO,
            ):
                await self._set_emocion_idle()

    # ── Broadcasts ─────────────────────────────────────────────────────

    async def _enviar_lipsync(self, rms: float, terminado: bool):
        await self._broadcaster.broadcast(
            {"tipo": "lipsync", "amplitud": rms, "terminado": terminado}
        )

    async def _enviar_estado_vad(self, hablando: bool):
        await self._broadcaster.broadcast({"tipo": "vad", "hablando": hablando})

    async def _enviar_procesando(self, activo: bool):
        await self._broadcaster.broadcast({"tipo": "procesando", "activo": activo})

    async def _enviar_paso_agente(self, evento: dict):
        await self._broadcaster.broadcast({"tipo": "agente", **evento})

    async def _on_trigger_proactivo(self, mensaje: str, tipo: str):
        if self._procesando or self._silenciado:
            return
        log.info("Trigger proactivo [%s]: %s", tipo, mensaje)
        await self._broadcaster.broadcast(
            {
                "tipo": "trigger_proactivo",
                "mensaje": mensaje,
                "subtipo": tipo,
            }
        )
        await self._responder(mensaje)

    # ── VAD callback ───────────────────────────────────────────────────

    async def _on_voz(self, audio_np: np.ndarray) -> None:
        if self._procesando or self._silenciado or self._audio is None:
            return
        self._procesando = True
        await self._set_emocion(EMOCION_PROCESANDO)
        await self._enviar_procesando(True)
        try:
            texto = await self._audio.transcribir(audio_np)
            if texto.strip():
                await self._pipeline(texto.strip())
        except Exception as e:
            log.exception("Error en pipeline: %s", e)
            await self._set_emocion(EMOCION_ERROR)
        finally:
            self._procesando = False
            await self._enviar_procesando(False)
            if self._emocion_gem != EMOCION_HABLANDO:
                await self._set_emocion_idle()

    # ── Pipeline ───────────────────────────────────────────────────────

    async def _pipeline(self, texto_usuario: str) -> str:
        estado = self._vision.get_estado()
        if estado.get("identidad_activa") and not estado.get("es_usuario"):
            await self._responder("No reconozco quién está frente a la cámara.")
            return ""

        # 1. Skill guardado?
        m = _REGEX_GUARDAR_SKILL.match(texto_usuario)
        if m:
            return await self._guardar_skill(m.group(1), m.group(2))

        m = _REGEX_EJECUTAR_SKILL.match(texto_usuario)
        if m:
            return await self._ejecutar_skill(m.group(1))

        # 2. Screenshot?
        if _REGEX_SCREENSHOT.search(texto_usuario):
            return await self._flujo_screenshot(texto_usuario)

        # 3. Agente o conversación?
        self._historial.append({"rol": "user", "texto": texto_usuario})
        await self._compactar_historial_si_excede()

        if _REGEX_AGENTE.search(texto_usuario):
            return await self._flujo_agente(texto_usuario)
        return await self._flujo_conversacion(texto_usuario)

    async def _flujo_conversacion(self, texto_usuario: str) -> str:
        fragmentos = await self._memoria.buscar_todo(texto_usuario)
        resumen_perfil = await self._perfil.resumen_para_prompt()

        prompt = construir_prompt(
            emocion=self._vision.get_estado().get("emocion", "neutro"),
            es_usuario=self._vision.get_estado().get("es_usuario", False),
            turnos=len(self._historial) // 2,
            memoria=self._memoria.estadisticas(),
            silenciado=self._silenciado,
            fragmentos_rag=fragmentos,
            perfil_visual=resumen_perfil,
        )

        await self._set_emocion(EMOCION_PROCESANDO)
        try:
            respuesta = await generar_respuesta(self._historial, system_prompt=prompt)
        except Exception as e:
            log.exception("Error generando respuesta: %s", e)
            await self._responder("Tuve un problema generando la respuesta.")
            await self._set_emocion(EMOCION_ERROR)
            return ""

        self._historial.append({"rol": "model", "texto": respuesta})
        self._historial_persistente.guardar(self._historial)

        await asyncio.gather(
            self._guardar_conversacion(texto_usuario, respuesta),
            self._responder(respuesta),
            return_exceptions=True,
        )
        return respuesta

    async def _flujo_agente(self, texto_usuario: str) -> str:
        fragmentos = await self._memoria.buscar(texto_usuario, "comandos", k=3)
        contexto = "\n".join(fragmentos) if fragmentos else ""

        await self._set_emocion(EMOCION_PROCESANDO)
        try:
            respuesta = await self._agente.ejecutar(
                tarea=texto_usuario,
                historial_gem=self._historial,
                contexto_rag=contexto,
                on_paso=self._enviar_paso_agente,
            )
        except Exception as e:
            log.exception("Agente falló: %s", e)
            await self._responder("El agente tuvo un problema.")
            await self._set_emocion(EMOCION_ERROR)
            return ""

        self._historial.append({"rol": "model", "texto": respuesta})
        self._historial_persistente.guardar(self._historial)

        await asyncio.gather(
            self._guardar_conversacion(texto_usuario, respuesta),
            self._responder(respuesta),
            return_exceptions=True,
        )
        return respuesta

    async def _flujo_screenshot(self, texto_usuario: str) -> str:
        await self._set_emocion(EMOCION_PROCESANDO)
        respuesta = await screenshot.analizar_pantalla(texto_usuario)
        self._historial.append({"rol": "user", "texto": texto_usuario})
        self._historial.append({"rol": "model", "texto": respuesta})
        self._historial_persistente.guardar(self._historial)
        await self._responder(respuesta)
        return respuesta

    # ── Skills ─────────────────────────────────────────────────────────

    async def _guardar_skill(self, nombre: str, contenido: str) -> str:
        comandos = [c.strip() for c in re.split(r"[;\n]", contenido) if c.strip()]
        if not comandos:
            return "No detecté comandos para guardar."
        self._skills.guardar(nombre.strip(), comandos, descripcion=nombre.strip())
        msg = f"Rutina '{nombre.strip()}' guardada con {len(comandos)} pasos."
        await self._responder(msg)
        return msg

    async def _ejecutar_skill(self, nombre: str) -> str:
        skill = self._skills.obtener(nombre)
        if not skill:
            msg = f"No tengo una rutina llamada '{nombre.strip()}'."
            await self._responder(msg)
            return msg

        await self._responder(f"Ejecutando rutina '{nombre.strip()}'.")
        errores = []
        for cmd in skill.get("comandos", []):
            r = await tools.bash(cmd)
            if not r.get("exito"):
                errores.append(f"{cmd}: {r.get('error', 'falló')}")
        if errores:
            msg = f"Terminé con {len(errores)} errores: {'; '.join(errores[:2])}"
        else:
            msg = "Rutina completada."
        await self._responder(msg)
        return msg

    # ── Compactación de historial ──────────────────────────────────────

    async def _compactar_historial_si_excede(self) -> None:
        if len(self._historial) <= ajustes.historial_resumen_turnos * 2:
            return
        # Tomar los más antiguos, resumirlos, mantener los últimos N turnos completos
        n_recientes = ajustes.historial_resumen_turnos
        antiguos = self._historial[: -n_recientes * 2]
        if not antiguos:
            return
        log.info("Compactando %d turnos antiguos", len(antiguos) // 2)
        resumen = await resumir_historial(antiguos)
        if resumen:
            self._historial = [
                {"rol": "user", "texto": "(resumen previo)"},
                {"rol": "model", "texto": resumen},
            ] + self._historial[-n_recientes * 2 :]

    # ── Confirmación de operaciones destructivas ───────────────────────

    async def _pedir_confirmacion(self, accion: str, args: dict) -> bool:
        """Envía petición al frontend, espera respuesta vía /confirmar."""
        import uuid

        id_req = str(uuid.uuid4())
        fut = self._loop.create_future()
        self._confirmaciones_pendientes[id_req] = fut

        await self._broadcaster.broadcast(
            {
                "tipo": "confirmar",
                "id": id_req,
                "accion": accion,
                "args": args,
            }
        )

        try:
            return await asyncio.wait_for(fut, timeout=30)
        except asyncio.TimeoutError:
            return False
        finally:
            self._confirmaciones_pendientes.pop(id_req, None)

    def responder_confirmacion(self, id_req: str, autorizado: bool) -> bool:
        fut = self._confirmaciones_pendientes.get(id_req)
        if fut and not fut.done():
            fut.set_result(autorizado)
            return True
        return False

    # ── TTS ────────────────────────────────────────────────────────────

    async def _responder(self, texto: str) -> None:
        await self._broadcaster.broadcast({"tipo": "respuesta", "texto": texto})
        if not self._audio or not texto.strip():
            return
        await self._set_emocion(EMOCION_HABLANDO)
        try:
            await self._audio.sintetizar_y_reproducir(texto)
        except Exception as e:
            log.exception("Error reproduciendo: %s", e)
        finally:
            await self._set_emocion_idle()

    async def _guardar_conversacion(self, p: str, r: str) -> None:
        try:
            await self._memoria.guardar(
                f"Usuario: {p}\nGEM: {r}", coleccion="conversaciones"
            )
        except Exception as e:
            log.warning("No se pudo guardar conversación: %s", e)

    # ── API pública ────────────────────────────────────────────────────

    async def procesar_texto(self, texto: str) -> str:
        return await self._pipeline(texto)

    async def registrar_identidad(
        self, muestras: int = 10, timeout_s: float = 8.0
    ) -> dict:
        import asyncio

        return await asyncio.to_thread(
            self._vision.registrar_desde_camara, muestras, timeout_s
        )

    async def borrar_identidad(self) -> None:
        self._vision.borrar_identidad()

    async def registrar_perfil_inicial(self, descripcion: str) -> dict:
        frame = self._vision.get_frame_actual()
        if frame is None:
            return {"exito": False, "mensaje": "No hay frame de cámara disponible."}
        obs: dict[str, Any] = {}
        if self._observador:
            obs = await self._observador._gemini_vision(frame) or {}
        await self._perfil.registrar_inicial(descripcion, obs)
        return {"exito": True, "mensaje": "Perfil visual registrado correctamente."}

    async def guardar_contexto(self, texto: str, coleccion: str = "proyectos") -> None:
        await self._memoria.guardar(texto, coleccion=coleccion)

    def silenciar(self, valor: bool = True) -> None:
        self._silenciado = valor

    def mutear_microfono(self, valor: bool = True) -> None:
        if self._audio:
            self._audio.mutear_microfono(valor)

    def microfono_muteado(self) -> bool:
        return self._audio.microfono_muteado() if self._audio else False

    def set_proactivo(self, valor: bool) -> None:
        if self._observador:
            self._observador.set_proactivo(valor)

    def get_proactivo(self) -> bool:
        return self._observador.get_proactivo() if self._observador else False

    def listar_skills(self) -> list[dict]:
        return self._skills.listar()

    def eliminar_skill(self, nombre: str) -> bool:
        return self._skills.eliminar(nombre)

    def limpiar_historial(self) -> None:
        self._historial.clear()
        self._historial_persistente.limpiar()

    def get_estado(self) -> dict:
        return {
            "vision": self._vision.get_estado(),
            "procesando": self._procesando,
            "silenciado": self._silenciado,
            "proactivo": self.get_proactivo(),
            "historial_turnos": len(self._historial) // 2,
            "memoria": self._memoria.estadisticas(),
            "emocion_gem": self._emocion_gem,
            "perfil": self._perfil.estadisticas(),
            "skills": len(self._skills.listar()),
        }
