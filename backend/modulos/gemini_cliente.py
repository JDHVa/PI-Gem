"""
Cliente unificado de Google Gemini.

Capacidades expuestas:
  - generar_respuesta(historial, system_prompt) -> str
  - generar_embedding(texto) -> list[float]
  - transcribir_audio(audio_np, sample_rate) -> str          [STT]
  - sintetizar_voz(texto) -> (audio_np, sample_rate)         [TTS]
  - analizar_riesgo_comando(comando) -> "bajo" | "medio" | "alto"
  - generar_correccion_comando(comando, error) -> str
"""
import asyncio
import io
import re
import wave
import logging
import numpy as np
from google import genai
from google.genai import types
from backend.config import ajustes

log = logging.getLogger("gem.gemini")

_cliente: genai.Client | None = None


def _get_cliente() -> genai.Client:
    global _cliente
    if _cliente is None:
        if not ajustes.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY no configurada. Edita el archivo .env"
            )
        _cliente = genai.Client(api_key=ajustes.gemini_api_key)
    return _cliente


# ───────── Generación de texto ─────────

def _historial_a_contents(historial: list[dict]) -> list[types.Content]:
    contenidos: list[types.Content] = []
    for turno in historial:
        rol = "user" if turno["rol"] == "user" else "model"
        contenidos.append(
            types.Content(role=rol, parts=[types.Part.from_text(text=turno["texto"])])
        )
    return contenidos


async def generar_respuesta(historial: list[dict], system_prompt: str) -> str:
    cliente = _get_cliente()
    contents = _historial_a_contents(historial)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=0.7,
        max_output_tokens=1024,
    )

    def _llamar() -> str:
        respuesta = cliente.models.generate_content(
            model=ajustes.gemini_modelo,
            contents=contents,
            config=config,
        )
        return (respuesta.text or "").strip()

    return await asyncio.to_thread(_llamar)


# ───────── Embeddings ─────────

async def generar_embedding(texto: str) -> list[float]:
    cliente = _get_cliente()

    def _llamar() -> list[float]:
        respuesta = cliente.models.embed_content(
            model=ajustes.gemini_modelo_embedding,
            contents=texto,
        )
        return list(respuesta.embeddings[0].values)

    return await asyncio.to_thread(_llamar)


# ───────── STT (Speech-to-Text) ─────────

def _np_a_wav_bytes(audio: np.ndarray, sample_rate: int) -> bytes:
    """Convierte un array float32/int16 mono a WAV PCM-16 en memoria."""
    if audio.dtype != np.int16:
        audio_i16 = np.clip(audio, -1.0, 1.0)
        audio_i16 = (audio_i16 * 32767.0).astype(np.int16)
    else:
        audio_i16 = audio

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio_i16.tobytes())
    return buffer.getvalue()


async def transcribir_audio(audio: np.ndarray, sample_rate: int) -> str:
    """
    Transcribe audio usando Gemini.
    `audio`: np.ndarray float32 mono en [-1, 1] o int16.
    """
    cliente = _get_cliente()
    wav_bytes = _np_a_wav_bytes(audio, sample_rate)

    def _llamar() -> str:
        respuesta = cliente.models.generate_content(
            model=ajustes.gemini_modelo_stt,
            contents=[
                "Transcribe literalmente este audio en español. "
                "Devuelve SOLO el texto transcrito, sin comentarios, "
                "sin marcas de tiempo. "
                "Si el audio está vacío o es ininteligible, responde con cadena vacía.",
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=512,
            ),
        )
        return (respuesta.text or "").strip()

    return await asyncio.to_thread(_llamar)


# ───────── TTS (Text-to-Speech) ─────────

def _pcm_a_numpy(pcm_bytes: bytes) -> np.ndarray:
    """Gemini TTS devuelve PCM 16-bit signed little-endian a 24 kHz."""
    audio_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
    return audio_i16.astype(np.float32) / 32768.0


async def sintetizar_voz(texto: str) -> tuple[np.ndarray, int]:
    """
    Sintetiza voz con Gemini TTS.
    Devuelve (audio_float32_mono, sample_rate).
    Ante error, devuelve (array vacío, sample_rate).
    """
    if not texto.strip():
        return np.zeros(0, dtype=np.float32), ajustes.tts_sample_rate

    cliente = _get_cliente()

    def _llamar() -> tuple[np.ndarray, int]:
        try:
            respuesta = cliente.models.generate_content(
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
            pcm = respuesta.candidates[0].content.parts[0].inline_data.data
            return _pcm_a_numpy(pcm), ajustes.tts_sample_rate
        except Exception as e:
            log.error("TTS Gemini falló: %s", e)
            return np.zeros(0, dtype=np.float32), ajustes.tts_sample_rate

    return await asyncio.to_thread(_llamar)


# ───────── Análisis de riesgo de comandos PowerShell ─────────

PROMPT_RIESGO = """Clasifica el siguiente comando de PowerShell por su nivel de riesgo.
Responde SOLO con una palabra: bajo, medio o alto.

Criterios:
- bajo: lectura, listado, consultas (Get-*, Select-*, Where-*, ls, dir).
- medio: instalación de software, modificación de archivos del usuario, cambios de red.
- alto: borrado masivo (Remove-Item -Recurse), formateo, modificación del registro,
  cambios en HKLM, deshabilitar servicios críticos, sc.exe, Stop-Computer, shutdown,
  cualquier cosa con -Force sobre rutas del sistema.

Comando: {comando}

Riesgo:"""


async def analizar_riesgo_comando(comando: str) -> str:
    cliente = _get_cliente()
    prompt = PROMPT_RIESGO.format(comando=comando)

    def _llamar() -> str:
        respuesta = cliente.models.generate_content(
            model=ajustes.gemini_modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=10,
            ),
        )
        texto = (respuesta.text or "").strip().lower()
        for nivel in ("alto", "medio", "bajo"):
            if nivel in texto:
                return nivel
        return "medio"

    return await asyncio.to_thread(_llamar)


# ───────── Auto-corrección de comandos ─────────

PROMPT_CORRECCION = """Eres un experto en PowerShell. Un comando falló.
Analiza el error y devuelve SOLO el comando corregido, sin explicaciones,
sin bloques de código, sin backticks, sin comentarios.

Comando original:
{comando}

Error:
{error}

Comando corregido:"""


def _limpiar_comando(texto: str) -> str:
    texto = texto.strip()
    texto = re.sub(r"^```(?:powershell|ps1|pwsh)?\s*", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\s*```$", "", texto)
    texto = re.sub(r"^(?:powershell|pwsh|ps)\s*[:>]\s*", "", texto, flags=re.IGNORECASE)
    return texto.strip()


async def generar_correccion_comando(comando: str, error: str) -> str:
    cliente = _get_cliente()
    prompt = PROMPT_CORRECCION.format(comando=comando, error=error)

    def _llamar() -> str:
        respuesta = cliente.models.generate_content(
            model=ajustes.gemini_modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=512,
            ),
        )
        return _limpiar_comando(respuesta.text or "")

    return await asyncio.to_thread(_llamar)
