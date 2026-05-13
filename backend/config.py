"""
Configuración central de GEM.

Modos LLM:
  · AI Studio  → USAR_VERTEX=false  +  GEMINI_API_KEY=<key>
  · Vertex AI  → USAR_VERTEX=true   +  VERTEX_PROJECT=<project-id>

Proveedores TTS (TTS_PROVEEDOR):
  · edge        → Microsoft Edge TTS (gratis, sin API key)  ← recomendado
  · google      → Google Cloud TTS (Chirp3-HD, Neural2…)
  · gemini      → Gemini TTS preview (solo AI Studio)
  · elevenlabs  → ElevenLabs
  · openai      → OpenAI TTS
"""

import logging
from pathlib import Path
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent
_ENV_PATH = RAIZ_PROYECTO / ".env"

log = logging.getLogger("gem.config")


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    usar_vertex: bool    = Field(default=False)
    vertex_project: str  = Field(default="")
    vertex_location: str = Field(default="us-central1")
    gemini_api_key: str  = Field(default="")

    gemini_modelo: str           = "gemini-2.0-flash-001"
    gemini_modelo_stt: str       = "gemini-2.0-flash-001"
    gemini_modelo_ligero: str    = "gemini-2.0-flash-lite-001"
    gemini_modelo_tts: str       = "gemini-2.5-flash-preview-tts"
    gemini_modelo_embedding: str = "text-embedding-004"
    gemini_modelo_vision: str    = "gemini-2.0-flash-001"

    embedding_cache_size: int = 256
    historial_resumen_turnos: int = 16
    historial_max_turnos: int     = 24
    vision_max_pixels: int = 786_432
    vision_jpeg_quality: int = 70

    tts_proveedor: str   = "edge"
    tts_sample_rate: int = 24000
    tts_voz_edge: str  = "es-MX-DaliaNeural"
    tts_idioma: str    = "es-US"
    tts_voz_cloud: str = "es-US-Chirp3-HD-Aoede"
    tts_voz: str       = "Kore"

    elevenlabs_api_key: str  = Field(default="")
    elevenlabs_voice_id: str = "cjVigY5qzO86Huf0OWal"
    elevenlabs_modelo: str   = "eleven_multilingual_v2"

    openai_api_key: str  = Field(default="")
    openai_tts_voz: str  = "nova"
    openai_tts_model: str = "tts-1-hd"

    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8765

    sample_rate: int          = 16000
    silence_duration_s: float = 1.4
    silence_threshold: float  = 0.012
    max_grabacion_s: float    = 15.0

    vad_rms_umbral: float    = 0.012
    vad_min_frase_s: float   = 0.5
    fallback_cooldown_s: float = 5.0
    barge_in_activo: bool = True

    mediapipe_model_path: str = str(RAIZ_PROYECTO / "assets" / "face_landmarker.task")
    identidad_umbral: float   = 0.85
    vision_fps: int           = 10

    chromadb_path: str = str(RAIZ_PROYECTO / "data" / "chromadb")
    rag_top_k: int     = 4
    historial_path: str = str(RAIZ_PROYECTO / "data" / "historial.json")

    ps_max_retries: int = 3
    ps_timeout_s: int   = 60
    agente_max_pasos: int = 20

    avatar_path: str = str(RAIZ_PROYECTO / "assets" / "avatar")

    @model_validator(mode="after")
    def validar(self) -> "Ajustes":
        if not _ENV_PATH.exists():
            log.warning(".env NO encontrado en %s", _ENV_PATH)

        if self.usar_vertex:
            if not self.vertex_project:
                raise ValueError(
                    "\n\n  ERROR: USAR_VERTEX=true pero VERTEX_PROJECT está vacío.\n"
                    "  Agrega en .env:\n    VERTEX_PROJECT=tu-proyecto-gcp\n"
                    "  Autentícate:\n    gcloud auth application-default login\n"
                )
            log.info("LLM: Vertex AI — proyecto=%s región=%s",
                     self.vertex_project, self.vertex_location)
        else:
            if not self.gemini_api_key:
                raise ValueError(
                    "\n\n  ERROR: GEMINI_API_KEY vacía.\n"
                    "  Opción A — AI Studio:\n    GEMINI_API_KEY=AIza...\n"
                    "  Opción B — Vertex AI:\n    USAR_VERTEX=true\n"
                    "             VERTEX_PROJECT=tu-proyecto\n"
                )
            log.info("LLM: AI Studio")

        proveedor = self.tts_proveedor.lower()
        if proveedor == "elevenlabs" and not self.elevenlabs_api_key:
            raise ValueError("TTS_PROVEEDOR=elevenlabs pero ELEVENLABS_API_KEY vacía.")
        if proveedor == "openai" and not self.openai_api_key:
            raise ValueError("TTS_PROVEEDOR=openai pero OPENAI_API_KEY vacía.")

        log.info("TTS: %s", proveedor)
        return self


ajustes = Ajustes()
