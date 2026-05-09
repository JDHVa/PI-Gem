import asyncio
import re
import logging
from backend.modulos.gemini_cliente import generar_respuesta
from backend.modulos.audio import ModuloAudio
from backend.modulos.memoria import MemoriaRAG
from backend.modulos.powershell import clasificar_riesgo, ejecutar, auto_healing
from backend.modulos.vision import ModuloVision
from backend.modulos.vtube import VTubeCliente
from backend.prompts.system_prompt import construir as construir_prompt

log = logging.getLogger("gem.orquestador")

PATRON_CMD = re.compile(r"^\[CMD:(.+?)\](.*)", re.DOTALL | re.IGNORECASE)


class Orquestador:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._historial: list[dict] = []
        self._memoria = MemoriaRAG()
        self._vision = ModuloVision()
        self._vtube = VTubeCliente()
        self._audio: ModuloAudio | None = None
        self._procesando = False
        self._silenciado = False

    async def iniciar(self) -> None:
        self._loop = asyncio.get_event_loop()
        self._audio = ModuloAudio(
            callback_activado=self._on_wake_word,
            loop=self._loop,
        )
        try:
            self._vision.iniciar()
        except Exception as e:
            log.warning("Visión no disponible: %s", e)

        try:
            vtube_ok = await self._vtube.conectar()
            if vtube_ok:
                await self._vtube.set_expresion("neutro")
        except Exception as e:
            log.warning("VTube no disponible: %s", e)

        try:
            self._audio.iniciar()
        except Exception as e:
            log.error("Audio no disponible: %s", e)

    async def detener(self) -> None:
        if self._audio:
            self._audio.detener()
        self._vision.detener()
        await self._vtube.desconectar()

    async def _on_wake_word(self) -> None:
        if self._procesando or self._silenciado or self._audio is None:
            return
        self._procesando = True
        try:
            audio_np = await self._loop.run_in_executor(
                None, self._audio.grabar_hasta_silencio
            )
            texto = await self._audio.transcribir(audio_np)
            if texto.strip():
                await self._pipeline(texto.strip())
        except Exception as e:
            log.exception("Error en wake-word pipeline: %s", e)
        finally:
            self._procesando = False

    def _construir_prompt(self, fragmentos: list[str]) -> str:
        estado = self._vision.get_estado()
        return construir_prompt(
            emocion=estado["emocion"],
            es_usuario=estado["es_usuario"],
            vtube_activo=self._vtube.esta_conectado(),
            fragmentos_rag=fragmentos or [],
        )

    async def _pipeline(self, texto_usuario: str) -> str:
        estado = self._vision.get_estado()
        if estado["identidad_activa"] and not estado["es_usuario"]:
            await self._responder("No reconozco quién está frente a la cámara.")
            return ""

        fragmentos = await self._memoria.buscar_todo(texto_usuario)
        prompt = self._construir_prompt(fragmentos)

        self._historial.append({"rol": "user", "texto": texto_usuario})
        if len(self._historial) > 24:
            self._historial = self._historial[-24:]

        await self._vtube.set_expresion(estado["emocion"])

        try:
            respuesta_raw = await generar_respuesta(
                self._historial, system_prompt=prompt
            )
        except Exception as e:
            log.exception("Error generando respuesta: %s", e)
            error_msg = "Tuve un problema al generar la respuesta. Revisa la API key."
            await self._responder(error_msg)
            return error_msg

        match = PATRON_CMD.match(respuesta_raw.strip())
        if match:
            comando = match.group(1).strip()
            texto_respuesta = match.group(2).strip() or "Ejecutando..."
            await self._flujo_comando(comando, texto_usuario)
        else:
            texto_respuesta = respuesta_raw

        self._historial.append({"rol": "model", "texto": texto_respuesta})

        await asyncio.gather(
            self._guardar_conversacion(texto_usuario, texto_respuesta),
            self._responder(texto_respuesta),
            return_exceptions=True,
        )
        return texto_respuesta

    async def _flujo_comando(self, comando: str, instruccion_original: str) -> None:
        riesgo = await clasificar_riesgo(comando)
        log.info("Comando: %s | riesgo=%s", comando, riesgo)

        if riesgo == "alto":
            await self._responder(
                f"Comando de alto riesgo detectado. ¿Confirmas ejecutar: {comando}? Di sí o no."
            )
            if self._audio:
                audio_confirm = await self._loop.run_in_executor(
                    None, self._audio.grabar_hasta_silencio
                )
                confirmacion = await self._audio.transcribir(audio_confirm)
                conf_lower = confirmacion.lower()
                if "sí" not in conf_lower and "si" not in conf_lower:
                    await self._responder("Comando cancelado.")
                    return

        resultado = await ejecutar(comando)
        if resultado["exito"]:
            await self._memoria.guardar_comando_exitoso(instruccion_original, comando)
        else:
            log.info("Comando falló, intentando auto-healing")
            resultado_fix = await auto_healing(comando, resultado["stderr"])
            if resultado_fix["exito"]:
                await self._memoria.guardar_comando_exitoso(
                    instruccion_original, resultado_fix["comando_final"]
                )

    async def _responder(self, texto: str) -> None:
        if self._audio is None or not texto.strip():
            return
        try:
            audio_np = await self._audio.sintetizar_y_reproducir(texto)
            if audio_np.size > 0:
                from backend.config import ajustes

                await self._vtube.reproducir_con_lipsync(
                    audio_np, ajustes.tts_sample_rate
                )
        except Exception as e:
            log.exception("Error reproduciendo: %s", e)

    async def _guardar_conversacion(self, pregunta: str, respuesta: str) -> None:
        try:
            await self._memoria.guardar(
                f"Usuario: {pregunta}\nGEM: {respuesta}",
                coleccion="conversaciones",
            )
        except Exception as e:
            log.warning("No se pudo guardar conversación: %s", e)

    async def procesar_texto(self, texto: str) -> str:
        return await self._pipeline(texto)

    async def registrar_identidad(self) -> bool:
        return self._vision.registrar_desde_camara()

    async def guardar_contexto(self, texto: str, coleccion: str = "proyectos") -> None:
        await self._memoria.guardar(texto, coleccion=coleccion)

    def silenciar(self, valor: bool = True) -> None:
        self._silenciado = valor

    def get_estado(self) -> dict:
        return {
            "vision": self._vision.get_estado(),
            "vtube_conectado": self._vtube.esta_conectado(),
            "procesando": self._procesando,
            "silenciado": self._silenciado,
            "historial_turnos": len(self._historial),
            "memoria": self._memoria.estadisticas(),
        }
