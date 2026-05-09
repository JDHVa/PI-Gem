"""
Módulo de audio.

  - Wake word: delegado a backend.modulos.wake_word.WakeWordDetector
  - STT: Gemini (transcribir_audio)
  - TTS: Gemini (sintetizar_voz)
  - VAD para fin de comando: umbral RMS local
"""

import asyncio
import logging
import threading
import numpy as np
import sounddevice as sd
from backend.config import ajustes
from backend.modulos.gemini_cliente import transcribir_audio, sintetizar_voz
from backend.modulos.wake_word import WakeWordDetector

log = logging.getLogger("gem.audio")


class ModuloAudio:
    def __init__(self, callback_activado, loop: asyncio.AbstractEventLoop):
        self._callback = callback_activado
        self._loop = loop
        self._mic_lock = threading.Lock()
        self._procesando_comando = threading.Event()
        self._wake = WakeWordDetector(
            callback=callback_activado,
            loop=loop,
            mic_lock=self._mic_lock,
            procesando_event=self._procesando_comando,
        )
        # Callback opcional para notificar al avatar/UI sobre el RMS del TTS
        # firma: callback(rms: float, terminado: bool)
        self.on_tts_amplitud = None

    def iniciar(self):
        self._wake.iniciar()

    def detener(self):
        self._wake.detener()

    # ───────── grabación de comandos ─────────

    def grabar_hasta_silencio(self) -> np.ndarray:
        """
        Graba hasta detectar silence_duration_s de silencio o max_grabacion_s.
        Toma el lock del mic compartido con el wake word.
        """
        chunk_dur = 0.1
        chunk_frames = int(chunk_dur * ajustes.sample_rate)
        silencio_max = max(1, int(ajustes.silence_duration_s / chunk_dur))
        max_duracion_chunks = int(ajustes.max_grabacion_s / chunk_dur)
        grabacion: list[np.ndarray] = []
        chunks_silencio = 0

        with self._mic_lock:
            try:
                stream = sd.InputStream(
                    samplerate=ajustes.sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=chunk_frames,
                )
                stream.start()
            except Exception as e:
                log.error("No se pudo abrir mic: %s", e)
                return np.zeros(0, dtype=np.float32)

            try:
                while len(grabacion) < max_duracion_chunks:
                    frame, _ = stream.read(chunk_frames)
                    flat = frame.flatten()
                    grabacion.append(flat)
                    rms = float(np.sqrt(np.mean(flat**2)))
                    if rms < ajustes.silence_threshold:
                        chunks_silencio += 1
                        if chunks_silencio >= silencio_max and len(grabacion) > 5:
                            break
                    else:
                        chunks_silencio = 0
            finally:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

        if not grabacion:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(grabacion)

    # ───────── STT / TTS (Gemini) ─────────

    async def transcribir(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        try:
            return await transcribir_audio(audio, ajustes.sample_rate)
        except Exception as e:
            log.warning("Transcripción falló: %s", e)
            return ""

    async def sintetizar_y_reproducir(self, texto: str) -> np.ndarray:
        """
        Sintetiza con Gemini TTS, reproduce por bocinas, y mientras suena
        invoca self.on_tts_amplitud(rms, terminado=False) para que el
        avatar mueva la boca. Al final llama on_tts_amplitud(0, True).
        """
        audio_f32, sr = await sintetizar_voz(texto)
        if audio_f32.size == 0:
            if self.on_tts_amplitud:
                try:
                    await self._invocar_amplitud(0.0, terminado=True)
                except Exception:
                    pass
            return audio_f32

        try:
            sd.play(audio_f32, samplerate=sr)

            # En paralelo a la reproducción, mando muestras de RMS al avatar
            ventana = max(1, sr // 20)  # 50 ms
            duracion_total = len(audio_f32) / sr

            t_chunk = 0.05
            i = 0
            inicio = asyncio.get_event_loop().time()
            while True:
                trans = asyncio.get_event_loop().time() - inicio
                if trans >= duracion_total:
                    break
                if i + ventana <= len(audio_f32):
                    chunk = audio_f32[i : i + ventana]
                    rms = float(np.sqrt(np.mean(chunk**2)))
                else:
                    rms = 0.0
                if self.on_tts_amplitud:
                    await self._invocar_amplitud(rms, terminado=False)
                i += ventana
                await asyncio.sleep(t_chunk)

            # Espera a que el audio termine realmente
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, sd.wait)

            if self.on_tts_amplitud:
                await self._invocar_amplitud(0.0, terminado=True)
        except Exception as e:
            log.warning("Reproducción falló: %s", e)
        return audio_f32

    async def _invocar_amplitud(self, rms: float, terminado: bool):
        cb = self.on_tts_amplitud
        if cb is None:
            return
        try:
            r = cb(rms, terminado)
            if asyncio.iscoroutine(r):
                await r
        except Exception as e:
            log.debug("on_tts_amplitud callback error: %s", e)

    async def sintetizar_a_array(self, texto: str) -> tuple[np.ndarray, int]:
        return await sintetizar_voz(texto)
