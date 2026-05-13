"""
Cliente unificado — AI Studio y Vertex AI.

Optimizaciones de costo (importantes para Vertex):
  · Cache LRU de embeddings: evita recomputar queries RAG repetidas
  · Modelo ligero (flash-lite) para clasificación de riesgo y correcciones cortas
  · Redimensionado de imágenes antes de Vision (max 1024px → ~5x menos tokens)
  · Caps duros de max_output_tokens por tarea

Capacidades:
  - generar_respuesta          → LLM normal
  - generar_respuesta_ligero   → LLM barato (flash-lite)
  - generar_embedding          → RAG (con cache)
  - transcribir_audio          → STT (Gemini)
  - sintetizar_voz             → TTS (Cloud / Gemini / Edge)
  - analizar_imagen            → Vision (con redimensionado)
  - analizar_riesgo_comando
  - generar_correccion_comando
"""

import asyncio
import io
import re
import wave
import logging
import numpy as np
from collections import OrderedDict
from google import genai
from google.genai import types
from backend.config import ajustes

log = logging.getLogger("gem.gemini")

_cliente: genai.Client | None = None


# ───────── Cliente (inyectable para tests) ─────────

def _get_cliente() -> genai.Client:
    global _cliente
    if _cliente is None:
        if ajustes.usar_vertex:
            log.info("Conectando a Vertex AI — proyecto=%s región=%s",
                     ajustes.vertex_project, ajustes.vertex_location)
            _cliente = genai.Client(
                vertexai=True,
                project=ajustes.vertex_project,
                location=ajustes.vertex_location,
            )
        else:
            log.info("Conectando a AI Studio")
            _cliente = genai.Client(api_key=ajustes.gemini_api_key)
    return _cliente


def set_cliente(cliente) -> None:
    """Inyecta un cliente para testing."""
    global _cliente
    _cliente = cliente


# ───────── LLM ─────────

def _historial_a_contents(historial: list[dict]) -> list[types.Content]:
    return [
        types.Content(
            role="user" if t["rol"] == "user" else "model",
            parts=[types.Part.from_text(text=t["texto"])],
        )
        for t in historial
    ]


async def generar_respuesta(historial: list[dict], system_prompt: str) -> str:
    cliente = _get_cliente()
    contents = _historial_a_contents(historial)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7,
        max_output_tokens=1024,
    )

    def _llamar() -> str:
        resp = cliente.models.generate_content(
            model=ajustes.gemini_modelo,
            contents=contents,
            config=config,
        )
        return (resp.text or "").strip()

    return await asyncio.to_thread(_llamar)


async def generar_respuesta_ligero(prompt: str, max_tokens: int = 256) -> str:
    """Versión barata con flash-lite. Para clasificación, resúmenes cortos, etc."""
    cliente = _get_cliente()

    def _llamar() -> str:
        resp = cliente.models.generate_content(
            model=ajustes.gemini_modelo_ligero,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=max_tokens),
        )
        return (resp.text or "").strip()

    return await asyncio.to_thread(_llamar)


async def resumir_historial(turnos: list[dict]) -> str:
    """Comprime N turnos en un resumen para reducir tokens enviados."""
    if not turnos:
        return ""
    texto = "\n".join(f"{t['rol']}: {t['texto'][:200]}" for t in turnos)
    prompt = (
        "Resume en máximo 3 frases el siguiente diálogo, manteniendo nombres, "
        "decisiones y hechos importantes. Sin preámbulo.\n\n" + texto
    )
    try:
        return await generar_respuesta_ligero(prompt, max_tokens=200)
    except Exception as e:
        log.warning("Resumen falló: %s", e)
        return ""


# ───────── Embeddings (con cache LRU) ─────────

class _CacheLRU:
    def __init__(self, max_size: int):
        self._data: OrderedDict[str, list[float]] = OrderedDict()
        self._max = max_size

    def get(self, k: str) -> list[float] | None:
        if k in self._data:
            self._data.move_to_end(k)
            return self._data[k]
        return None

    def put(self, k: str, v: list[float]) -> None:
        self._data[k] = v
        self._data.move_to_end(k)
        if len(self._data) > self._max:
            self._data.popitem(last=False)


_emb_cache = _CacheLRU(ajustes.embedding_cache_size)


async def generar_embedding(texto: str) -> list[float]:
    clave = texto[:512]
    cached = _emb_cache.get(clave)
    if cached is not None:
        return cached

    cliente = _get_cliente()

    def _llamar() -> list[float]:
        resp = cliente.models.embed_content(
            model=ajustes.gemini_modelo_embedding,
            contents=texto,
        )
        if not resp.embeddings:
            raise RuntimeError("No se recibió embedding")
        return list(resp.embeddings[0].values)

    emb = await asyncio.to_thread(_llamar)
    _emb_cache.put(clave, emb)
    return emb


# ───────── STT ─────────

def _np_a_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    if audio.dtype != np.int16:
        audio_i16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16)
    else:
        audio_i16 = audio
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(audio_i16.tobytes())
    return buf.getvalue()


async def transcribir_audio(audio: np.ndarray, sample_rate: int) -> str:
    cliente = _get_cliente()
    wav_bytes = _np_a_wav_bytes(audio, sample_rate)

    def _llamar() -> str:
        resp = cliente.models.generate_content(
            model=ajustes.gemini_modelo_stt,
            contents=[
                "Transcribe literalmente este audio en español. "
                "Devuelve SOLO el texto transcrito, sin comentarios ni marcas de tiempo. "
                "Si el audio está vacío o es ininteligible, responde con cadena vacía.",
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=512),
        )
        return (resp.text or "").strip()

    return await asyncio.to_thread(_llamar)


# ───────── Vision (con redimensionado para ahorrar tokens) ─────────

def _reducir_imagen(jpeg_bytes: bytes) -> bytes:
    """Redimensiona si excede vision_max_pixels y recomprime."""
    try:
        import cv2
        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return jpeg_bytes
        h, w = img.shape[:2]
        pixels = h * w
        if pixels > ajustes.vision_max_pixels:
            factor = (ajustes.vision_max_pixels / pixels) ** 0.5
            nw, nh = int(w * factor), int(h * factor)
            img = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img,
                                [cv2.IMWRITE_JPEG_QUALITY, ajustes.vision_jpeg_quality])
        return bytes(buf) if ok else jpeg_bytes
    except Exception as e:
        log.debug("Reducir imagen falló: %s", e)
        return jpeg_bytes


async def analizar_imagen(jpeg_bytes: bytes, prompt: str, max_tokens: int = 512) -> str:
    cliente = _get_cliente()
    reducido = _reducir_imagen(jpeg_bytes)

    def _llamar() -> str:
        resp = cliente.models.generate_content(
            model=ajustes.gemini_modelo_vision,
            contents=[
                types.Part.from_bytes(data=reducido, mime_type="image/jpeg"),
                prompt,
            ],
            config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=max_tokens),
        )
        return (resp.text or "").strip()

    return await asyncio.to_thread(_llamar)


# ───────── TTS ─────────

def _cloud_tts(texto: str) -> tuple[np.ndarray, int]:
    try:
        from google.cloud import texttospeech
    except ImportError:
        raise RuntimeError("Falta google-cloud-texttospeech. pip install google-cloud-texttospeech")

    client = texttospeech.TextToSpeechClient()
    resp = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=texto),
        voice=texttospeech.VoiceSelectionParams(
            language_code=ajustes.tts_idioma,
            name=ajustes.tts_voz_cloud,
        ),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.LINEAR16,
            sample_rate_hertz=ajustes.tts_sample_rate,
        ),
    )
    buf = io.BytesIO(resp.audio_content)
    with wave.open(buf, "rb") as w:
        pcm = w.readframes(w.getnframes())
        sr  = w.getframerate()
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0, sr


def _gemini_tts(texto: str) -> tuple[np.ndarray, int]:
    cliente = _get_cliente()
    resp = cliente.models.generate_content(
        model=ajustes.gemini_modelo_tts,
        contents=texto,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=ajustes.tts_voz,
                    )
                )
            ),
        ),
    )
    pcm = resp.candidates[0].content.parts[0].inline_data.data
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0, ajustes.tts_sample_rate


async def _edge_tts(texto: str) -> tuple[np.ndarray, int]:
    try:
        import edge_tts
    except ImportError:
        raise RuntimeError("Instala edge-tts:  pip install edge-tts")

    voz = getattr(ajustes, "tts_voz_edge", "es-MX-DaliaNeural")
    communicate = edge_tts.Communicate(texto, voz)

    mp3_chunks: list[bytes] = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            mp3_chunks.append(chunk["data"])

    mp3_bytes = b"".join(mp3_chunks)
    if not mp3_bytes:
        return np.zeros(0, dtype=np.float32), ajustes.tts_sample_rate

    import subprocess, shutil
    if shutil.which("ffmpeg"):
        proc = subprocess.run(
            ["ffmpeg", "-i", "pipe:0",
             "-f", "s16le", "-ar", str(ajustes.tts_sample_rate),
             "-ac", "1", "pipe:1"],
            input=mp3_bytes, capture_output=True,
        )
        if proc.returncode == 0:
            audio_i16 = np.frombuffer(proc.stdout, dtype=np.int16)
            return audio_i16.astype(np.float32) / 32768.0, ajustes.tts_sample_rate

    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
        seg = seg.set_channels(1).set_frame_rate(ajustes.tts_sample_rate)
        pcm = np.array(seg.get_array_of_samples(), dtype=np.int16)
        return pcm.astype(np.float32) / 32768.0, ajustes.tts_sample_rate
    except ImportError:
        pass

    raise RuntimeError("edge-tts requiere ffmpeg o pydub para decodificar MP3.")


async def sintetizar_voz(texto: str) -> tuple[np.ndarray, int]:
    if not texto.strip():
        return np.zeros(0, dtype=np.float32), ajustes.tts_sample_rate

    proveedor = getattr(ajustes, "tts_proveedor", "edge").lower()

    try:
        if proveedor == "edge":
            return await _edge_tts(texto)
        elif proveedor in ("google", "vertex"):
            return await asyncio.to_thread(_cloud_tts, texto)
        else:
            return await asyncio.to_thread(_gemini_tts, texto)
    except Exception as e:
        log.error("TTS (%s) falló: %s", proveedor, e)
        return np.zeros(0, dtype=np.float32), ajustes.tts_sample_rate


# ───────── Riesgo de comandos (modelo ligero) ─────────

_PROMPT_RIESGO = """Clasifica el riesgo del siguiente comando PowerShell.
Responde SOLO con una palabra: bajo, medio o alto.

bajo: lecturas, listados (Get-*, ls, dir).
medio: instalar software, modificar archivos del usuario.
alto: borrado masivo, registro, servicios críticos, -Force en rutas del sistema.

Comando: {comando}
Riesgo:"""


async def analizar_riesgo_comando(comando: str) -> str:
    try:
        texto = await generar_respuesta_ligero(
            _PROMPT_RIESGO.format(comando=comando), max_tokens=10
        )
        texto = texto.lower()
        for nivel in ("alto", "medio", "bajo"):
            if nivel in texto:
                return nivel
        return "medio"
    except Exception as e:
        log.warning("Riesgo fallback (medio): %s", e)
        return "medio"


# ───────── Auto-corrección PowerShell ─────────

_PROMPT_CORRECCION = """Eres experto en PowerShell. Un comando falló.
Devuelve SOLO el comando corregido, sin explicaciones ni backticks.

Comando original:
{comando}

Error:
{error}

Comando corregido:"""


def _limpiar_cmd(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r"^```(?:powershell|ps1|pwsh)?\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s*```$", "", texto)
    return texto.strip()


async def generar_correccion_comando(comando: str, error: str) -> str:
    try:
        texto = await generar_respuesta_ligero(
            _PROMPT_CORRECCION.format(comando=comando, error=error[:500]),
            max_tokens=300,
        )
        return _limpiar_cmd(texto)
    except Exception as e:
        log.warning("Corrección falló: %s", e)
        return ""
