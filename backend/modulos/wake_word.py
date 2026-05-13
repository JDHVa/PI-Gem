"""
Detector por Actividad de Voz (VAD).

Usa WebRTC VAD si está disponible (pip install webrtcvad-wheels).
Fallback a RMS calibrado.

Soporta barge-in: si detecta voz durante el cooldown post-TTS,
notifica al módulo de audio para interrumpir la reproducción.
"""

import asyncio
import logging
import threading
import time
import numpy as np
import sounddevice as sd
from backend.config import ajustes

log = logging.getLogger("gem.vad")

_SILENCIO = "silencio"
_HABLANDO = "hablando"

_FRAME_MS = 20
_SAMPLE_RATE_WEBRTC = 16000


class VADDetector:
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
        self._pausado = False
        self._hilo: threading.Thread | None = None
        self._cooldown_hasta = 0.0
        self._umbral_rms = ajustes.vad_rms_umbral

        self.on_estado_vad = None
        # Callback de barge-in: se llama (sync) cuando hay voz mientras TTS suena
        self.on_voz_detectada_mientras_tts = None

        self._webrtcvad = None
        try:
            import webrtcvad

            self._webrtcvad = webrtcvad.Vad(2)
            log.info("WebRTC VAD activo (agresividad=2)")
        except ImportError:
            log.warning(
                "webrtcvad no instalado — fallback RMS. pip install webrtcvad-wheels"
            )

    def iniciar(self):
        self._activo = True
        self._hilo = threading.Thread(target=self._run, daemon=True)
        self._hilo.start()

    def detener(self):
        self._activo = False
        if self._hilo:
            self._hilo.join(timeout=2.0)

    def iniciar_cooldown(self):
        self._cooldown_hasta = time.time() + ajustes.fallback_cooldown_s

    def _es_voz(self, frame_f32: np.ndarray) -> bool:
        if self._webrtcvad is not None:
            frames_necesarios = int(_SAMPLE_RATE_WEBRTC * _FRAME_MS / 1000)
            if len(frame_f32) < frames_necesarios:
                frame_f32 = np.pad(frame_f32, (0, frames_necesarios - len(frame_f32)))
            frame_i16 = np.clip(frame_f32[:frames_necesarios], -1.0, 1.0)
            frame_i16 = (frame_i16 * 32767).astype(np.int16)
            try:
                return self._webrtcvad.is_speech(
                    frame_i16.tobytes(), _SAMPLE_RATE_WEBRTC
                )
            except Exception:
                pass
        return float(np.sqrt(np.mean(frame_f32**2))) > self._umbral_rms

    def _calibrar_rms(self) -> float:
        try:
            dur = 1.5
            frames = int(dur * ajustes.sample_rate)
            audio = sd.rec(
                frames,
                samplerate=ajustes.sample_rate,
                channels=1,
                dtype="float32",
                blocking=True,
            )
            ruido = float(np.sqrt(np.mean(audio**2)))
            umbral = max(ruido * 3.5, 0.006)
            log.info("RMS calibrado — ruido=%.4f umbral=%.4f", ruido, umbral)
            return umbral
        except Exception as e:
            log.warning("Calibración RMS falló: %s", e)
            return ajustes.vad_rms_umbral

    def _notificar(self, hablando: bool):
        cb = self.on_estado_vad
        if cb and self._loop:
            try:
                asyncio.run_coroutine_threadsafe(cb(hablando), self._loop)
            except Exception:
                pass

    def _disparar(self, audio_np: np.ndarray):
        self._procesando.set()

        def _limpiar(_):
            self._procesando.clear()

        try:
            f = asyncio.run_coroutine_threadsafe(self._callback(audio_np), self._loop)
            f.add_done_callback(_limpiar)
        except Exception as e:
            log.exception("VAD dispatch error: %s", e)
            self._procesando.clear()

    def pausar(self):
        """Mutea el micrófono: el VAD ignora todo el audio entrante."""
        self._pausado = True

    def reanudar(self):
        self._pausado = False

    def esta_pausado(self) -> bool:
        return getattr(self, "_pausado", False)

    def _run(self):
        if self._webrtcvad is None:
            self._umbral_rms = self._calibrar_rms()

        chunk_ms = _FRAME_MS if self._webrtcvad else 50
        chunk_frames = int(ajustes.sample_rate * chunk_ms / 1000)
        silencio_max = max(1, int(ajustes.silence_duration_s * 1000 / chunk_ms))
        max_chunks = int(ajustes.max_grabacion_s * 1000 / chunk_ms)
        min_chunks = max(1, int(ajustes.vad_min_frase_s * 1000 / chunk_ms))
        ventana_activacion = max(3, int(150 / chunk_ms))

        estado = _SILENCIO
        buf: list[np.ndarray] = []
        chunks_silencio = 0
        ventana: list[bool] = []
        stream = None
        barge_in_disparado = False

        while self._activo:
            en_cooldown = time.time() < self._cooldown_hasta
            if self._pausado:
                _cerrar(stream)
                stream = None
                if estado == _HABLANDO:
                    self._notificar(False)
                estado = _SILENCIO
                buf = []
                chunks_silencio = 0
                ventana = []
                time.sleep(0.15)
                continue
            if self._procesando.is_set():
                _cerrar(stream)
                stream = None
                if estado == _HABLANDO:
                    self._notificar(False)
                estado = _SILENCIO
                buf = []
                chunks_silencio = 0
                ventana = []
                barge_in_disparado = False
                time.sleep(0.08)
                continue

            if stream is None:
                try:
                    stream = sd.InputStream(
                        samplerate=ajustes.sample_rate,
                        channels=1,
                        dtype="float32",
                        blocksize=chunk_frames,
                    )
                    stream.start()
                except Exception as e:
                    log.error("VAD: no pudo abrir mic: %s", e)
                    time.sleep(1.0)
                    continue

            try:
                frame, _ = stream.read(chunk_frames)
            except Exception as e:
                log.debug("VAD read error: %s", e)
                _cerrar(stream)
                stream = None
                continue

            flat = frame.flatten()
            es_voz = self._es_voz(flat)

            # Barge-in: durante cooldown (GEM hablando), detectar voz fuerte
            if en_cooldown:
                if es_voz and not barge_in_disparado:
                    cb = self.on_voz_detectada_mientras_tts
                    if cb:
                        try:
                            cb()
                            barge_in_disparado = True
                        except Exception:
                            pass
                continue

            barge_in_disparado = False
            ventana.append(es_voz)
            if len(ventana) > ventana_activacion:
                ventana.pop(0)

            ratio_voz = sum(ventana) / max(len(ventana), 1)
            hay_voz = ratio_voz >= 0.6 if self._webrtcvad else es_voz

            if estado == _SILENCIO:
                if hay_voz:
                    estado = _HABLANDO
                    buf = [flat]
                    chunks_silencio = 0
                    self._notificar(True)

            elif estado == _HABLANDO:
                buf.append(flat)
                if hay_voz:
                    chunks_silencio = 0
                else:
                    chunks_silencio += 1
                    if chunks_silencio >= silencio_max:
                        voz_chunks = len(buf) - chunks_silencio
                        self._notificar(False)
                        if voz_chunks >= min_chunks:
                            log.info(
                                "VAD: frase %.1fs → pipeline",
                                voz_chunks * chunk_ms / 1000,
                            )
                            self._disparar(np.concatenate(buf))
                        else:
                            log.debug(
                                "VAD: descartada (%.1fs)", voz_chunks * chunk_ms / 1000
                            )
                        estado = _SILENCIO
                        buf = []
                        chunks_silencio = 0
                        ventana = []
                        continue

                if len(buf) >= max_chunks:
                    self._notificar(False)
                    self._disparar(np.concatenate(buf))
                    estado = _SILENCIO
                    buf = []
                    chunks_silencio = 0
                    ventana = []

        _cerrar(stream)


def _cerrar(stream):
    if stream is None:
        return
    try:
        if stream.active:
            stream.stop()
        stream.close()
    except Exception:
        pass
