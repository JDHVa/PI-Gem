import asyncio
import logging
import threading
import time
import numpy as np
import sounddevice as sd
from backend.config import ajustes
from backend.modulos.gemini_cliente import transcribir_audio, sintetizar_voz
from backend.modulos.wake_word import VADDetector

log = logging.getLogger("gem.audio")


class ModuloAudio:
    def __init__(self, callback_voz, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._mic_lock = threading.Lock()
        self._procesando = threading.Event()
        self._reproduciendo = threading.Event()
        self._interrumpir = threading.Event()
        self._vad = VADDetector(
            callback=callback_voz,
            loop=loop,
            mic_lock=self._mic_lock,
            procesando_event=self._procesando,
        )
        # Conectar barge-in: VAD detecta voz mientras GEM habla → interrumpir TTS
        self._vad.on_voz_detectada_mientras_tts = self._barge_in
        self.on_tts_amplitud = None

    @property
    def on_estado_vad(self):
        return self._vad.on_estado_vad

    @on_estado_vad.setter
    def on_estado_vad(self, value):
        self._vad.on_estado_vad = value

    def iniciar(self):
        self._vad.iniciar()

    def detener(self):
        self._vad.detener()

    def _barge_in(self):
        """Llamado desde el VAD cuando detecta voz mientras GEM habla."""
        if not ajustes.barge_in_activo:
            return
        if self._reproduciendo.is_set():
            log.info("Barge-in: usuario interrumpió, deteniendo TTS")
            self._interrumpir.set()
            try:
                sd.stop()
            except Exception:
                pass

    def mutear_microfono(self, valor: bool = True):
        if valor:
            self._vad.pausar()
        else:
            self._vad.reanudar()

    def microfono_muteado(self) -> bool:
        return self._vad.esta_pausado()

    def grabar_hasta_silencio(self) -> np.ndarray:
        """Grabación manual sincrónica para confirmaciones."""
        chunk_dur = 0.1
        chunk_frames = int(chunk_dur * ajustes.sample_rate)
        silencio_max = max(1, int(ajustes.silence_duration_s / chunk_dur))
        max_chunks = int(ajustes.max_grabacion_s / chunk_dur)
        grabacion: list[np.ndarray] = []
        chunks_silencio = 0

        with self._mic_lock:
            stream = None
            try:
                stream = sd.InputStream(
                    samplerate=ajustes.sample_rate,
                    channels=1,
                    dtype="float32",
                    blocksize=chunk_frames,
                )
                stream.start()
                while len(grabacion) < max_chunks:
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
            except Exception as e:
                log.error("Error grabando: %s", e)
                return np.zeros(0, dtype=np.float32)
            finally:
                if stream:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass

        return np.concatenate(grabacion) if grabacion else np.zeros(0, dtype=np.float32)

    async def transcribir(self, audio: np.ndarray) -> str:
        if audio.size == 0:
            return ""
        try:
            texto = await transcribir_audio(audio, ajustes.sample_rate)
            log.info("STT: '%s'", texto[:80] if texto else "(vacío)")
            return texto
        except Exception as e:
            log.warning("Transcripción falló: %s", e)
            return ""

    async def sintetizar_y_reproducir(self, texto: str) -> np.ndarray:
        audio_f32, sr = await sintetizar_voz(texto)
        if audio_f32.size == 0:
            await self._invocar_amplitud(0.0, terminado=True)
            return audio_f32

        self._vad.iniciar_cooldown()
        self._reproduciendo.set()
        self._interrumpir.clear()
        try:
            sd.play(audio_f32, samplerate=sr)
            ventana = max(1, sr // 20)
            duracion = len(audio_f32) / sr
            i = 0
            loop = asyncio.get_running_loop()
            inicio = loop.time()
            while loop.time() - inicio < duracion:
                if self._interrumpir.is_set():
                    log.info("TTS interrumpido")
                    break
                chunk = (
                    audio_f32[i : i + ventana]
                    if i + ventana <= len(audio_f32)
                    else None
                )
                rms = float(np.sqrt(np.mean(chunk**2))) if chunk is not None else 0.0
                await self._invocar_amplitud(rms, False)
                i += ventana
                await asyncio.sleep(0.05)
            if not self._interrumpir.is_set():
                await loop.run_in_executor(None, _sd_wait_timeout, duracion + 1.5)
            await self._invocar_amplitud(0.0, True)
        except Exception as e:
            log.warning("Reproducción falló: %s", e)
            try:
                sd.stop()
            except Exception:
                pass
            await self._invocar_amplitud(0.0, True)
        finally:
            self._reproduciendo.clear()
            self._interrumpir.clear()

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
            log.debug("on_tts_amplitud error: %s", e)

    async def sintetizar_a_array(self, texto: str) -> tuple[np.ndarray, int]:
        return await sintetizar_voz(texto)


def _sd_wait_timeout(timeout_s: float):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            if not sd.get_stream().active:
                break
        except Exception:
            break
        time.sleep(0.05)
    try:
        sd.wait()
    except Exception:
        pass
