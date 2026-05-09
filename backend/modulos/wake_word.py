"""
Detección de wake word con openWakeWord.

  - Open source (Apache 2.0), gratis, sin cuentas.
  - Modelos pre-entrenados: "hey jarvis", "alexa", "hey mycroft", "hey rhasspy", "ok nabu".
  - ~150 MB RAM, CPU only.

Lock global de mic compartido con grabar_hasta_silencio (en audio.py).
"""

import logging
import threading
import time
import numpy as np
import sounddevice as sd
from backend.config import ajustes

log = logging.getLogger("gem.wake")

try:
    from openwakeword.model import Model as OpenWakeWordModel

    _OWW_DISPONIBLE = True
except ImportError:
    _OWW_DISPONIBLE = False
    log.warning("openwakeword no instalado")


class WakeWordDetector:
    """Detector con openWakeWord o fallback RMS."""

    def __init__(
        self,
        callback,
        loop,
        mic_lock: threading.Lock,
        procesando_event: threading.Event,
    ):
        self._callback = callback
        self._loop = loop
        self._mic_lock = mic_lock
        self._procesando = procesando_event

        self._activo = False
        self._hilo: threading.Thread | None = None
        self._modelo: OpenWakeWordModel | None = None
        self._modo: str = "rms"  # "oww" | "rms"

    def iniciar(self):
        self._activo = True
        if _OWW_DISPONIBLE and ajustes.usar_openwakeword:
            try:
                # openWakeWord descarga los modelos al primer uso
                self._modelo = OpenWakeWordModel(
                    wakeword_models=[ajustes.wake_word_modelo],
                    inference_framework="onnx",
                )
                self._modo = "oww"
                log.info(
                    "Wake word con openWakeWord: '%s' (umbral=%.2f)",
                    ajustes.wake_word_modelo,
                    ajustes.wake_word_umbral,
                )
            except Exception as e:
                log.warning(
                    "No se pudo iniciar openWakeWord: %s — usando fallback RMS", e
                )
                self._modo = "rms"
        else:
            log.info("Wake word: detector RMS (modo fallback)")

        target = self._loop_oww if self._modo == "oww" else self._loop_rms
        self._hilo = threading.Thread(target=target, daemon=True)
        self._hilo.start()

    def detener(self):
        self._activo = False
        if self._hilo:
            self._hilo.join(timeout=2.0)

    def _disparar(self):
        """Marca evento y agenda callback en el loop async."""
        import asyncio

        self._procesando.set()

        def _terminar(_future):
            self._procesando.clear()

        try:
            future = asyncio.run_coroutine_threadsafe(self._callback(), self._loop)
            future.add_done_callback(_terminar)
        except Exception as e:
            log.exception("Error disparando callback: %s", e)
            self._procesando.clear()

    # ───────── openWakeWord ─────────

    def _loop_oww(self):
        """openWakeWord espera chunks de 1280 samples a 16 kHz (80 ms)."""
        sr = 16000
        frame_length = 1280

        while self._activo:
            if self._procesando.is_set():
                time.sleep(0.1)
                continue

            try:
                with self._mic_lock:
                    if self._procesando.is_set():
                        continue
                    stream = sd.InputStream(
                        samplerate=sr,
                        channels=1,
                        dtype="int16",
                        blocksize=frame_length,
                    )
                    stream.start()
                    try:
                        # Procesa por ráfagas para liberar el lock periódicamente
                        deadline = time.time() + 1.0
                        while (
                            self._activo
                            and not self._procesando.is_set()
                            and time.time() < deadline
                        ):
                            frame, _ = stream.read(frame_length)
                            audio_i16 = frame.flatten().astype(np.int16)
                            puntajes = self._modelo.predict(audio_i16)
                            score = max(puntajes.values()) if puntajes else 0.0

                            if score >= ajustes.wake_word_umbral:
                                log.info("Wake word detectado (score=%.2f)", score)
                                stream.stop()
                                stream.close()
                                # Reset interno del modelo para evitar retriggers
                                self._modelo.reset()
                                self._disparar()
                                break
                    finally:
                        try:
                            if stream.active:
                                stream.stop()
                            stream.close()
                        except Exception:
                            pass
            except Exception as e:
                log.debug("oww loop error: %s", e)
                time.sleep(0.2)

    # ───────── Fallback RMS ─────────

    def _loop_rms(self):
        chunk_dur = 0.2
        chunk_frames = int(chunk_dur * ajustes.sample_rate)
        frames_activacion = max(1, int(ajustes.fallback_activacion_s / chunk_dur))
        cooldown_s = ajustes.fallback_cooldown_s

        cooldown_hasta = 0.0
        chunks_activos = 0

        while self._activo:
            if self._procesando.is_set():
                time.sleep(0.1)
                chunks_activos = 0
                cooldown_hasta = time.time() + cooldown_s
                continue

            try:
                with self._mic_lock:
                    if self._procesando.is_set():
                        continue
                    audio = sd.rec(
                        chunk_frames,
                        samplerate=ajustes.sample_rate,
                        channels=1,
                        dtype="float32",
                    )
                    sd.wait()

                if not self._activo:
                    break

                ahora = time.time()
                if ahora < cooldown_hasta:
                    chunks_activos = 0
                    continue

                rms = float(np.sqrt(np.mean(audio**2)))
                if rms > ajustes.fallback_rms_umbral:
                    chunks_activos += 1
                    if chunks_activos >= frames_activacion:
                        log.info("Activación por RMS (rms=%.4f)", rms)
                        chunks_activos = 0
                        cooldown_hasta = ahora + cooldown_s
                        self._disparar()
                else:
                    chunks_activos = 0
            except Exception as e:
                log.debug("rms loop error: %s", e)
                time.sleep(0.2)
