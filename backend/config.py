"""
Configuración central de GEM.
Lee variables de entorno desde .env y expone un objeto `ajustes`
que todos los módulos importan.
"""
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ_PROYECTO = Path(__file__).resolve().parent.parent


class Ajustes(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(RAIZ_PROYECTO / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ───── Gemini / Google GenAI ─────
    gemini_api_key: str = Field(default="", description="API key de Google AI Studio")
    gemini_modelo: str = "gemini-2.5-flash"             # LLM principal
    gemini_modelo_stt: str = "gemini-2.5-flash"         # transcripción de audio
    gemini_modelo_tts: str = "gemini-2.5-flash-preview-tts"
    gemini_modelo_embedding: str = "text-embedding-004"

    # Voz prebuilt para Gemini TTS. Otras: Aoede, Charon, Fenrir, Kore, Leda, Orus, Puck, Zephyr...
    tts_voz: str = "Kore"
    tts_sample_rate: int = 24000  # Gemini TTS devuelve 24 kHz fijo

    # ───── FastAPI ─────
    fastapi_host: str = "127.0.0.1"
    fastapi_port: int = 8765

    # ───── Captura de audio ─────
    sample_rate: int = 16000          # tasa de captura del micrófono
    silence_duration_s: float = 1.2
    silence_threshold: float = 0.012
    max_grabacion_s: float = 15.0

    # ───── Wake word: Porcupine ─────
    picovoice_access_key: str = ""    # https://console.picovoice.ai/ (gratis)
    porcupine_keywords: list[str] = ["jarvis"]   # built-ins: alexa, americano, blueberry, bumblebee, computer, grapefruit, grasshopper, hey google, hey siri, jarvis, ok google, picovoice, porcupine, terminator
    porcupine_sensibilidad: float = 0.5

    # ───── Wake word: fallback RMS (sin Porcupine) ─────
    fallback_rms_umbral: float = 0.15         # más alto = menos falsos positivos
    fallback_activacion_s: float = 0.6        # tiempo de voz sostenida
    fallback_cooldown_s: float = 5.0          # tras activar, ignorar (evita auto-trigger por TTS)

    # ───── Visión ─────
    mediapipe_model_path: str = str(RAIZ_PROYECTO / "assets" / "face_landmarker.task")
    identidad_umbral: float = 0.85
    vision_fps: int = 10

    # ───── Memoria / ChromaDB ─────
    chromadb_path: str = str(RAIZ_PROYECTO / "data" / "chromadb")
    rag_top_k: int = 5

    # ───── PowerShell ─────
    ps_max_retries: int = 3
    ps_timeout_s: int = 60

    # ───── VTube Studio ─────
    vtube_ws_port: int = 8001
    vtube_plugin_name: str = "GEM Assistant"
    vtube_plugin_developer: str = "Jesus"
    vtube_token_path: str = str(RAIZ_PROYECTO / "data" / "vtube_token.txt")


ajustes = Ajustes()
