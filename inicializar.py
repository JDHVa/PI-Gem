"""
Script de inicialización de GEM v3 (con soporte Vertex AI).

Ejecutar UNA SOLA VEZ tras instalar las dependencias:
  python inicializar.py

Hace:
  1. Verifica versión de Python (>=3.11).
  2. Crea .env si no existe.
  3. Crea las carpetas data/, assets/.
  4. Descarga el modelo de MediaPipe.
  5. Inicializa las colecciones de ChromaDB.
  6. Valida credenciales (API key o ADC para Vertex).
"""
import os
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

PLANTILLA_ENV = """\
# ═══════════════════════════════════════════════════
#   GEM v3 — variables de entorno
# ═══════════════════════════════════════════════════

# ──────────────────────────────────────────────────
#  MODO 1: Google AI Studio (más fácil para empezar)
#  → Obtén tu key gratis en https://aistudio.google.com/apikey
# ──────────────────────────────────────────────────
USAR_VERTEX=false
GEMINI_API_KEY=

# ──────────────────────────────────────────────────
#  MODO 2: Vertex AI (recomendado para uso prolongado)
#  → Requiere proyecto GCP + ADC:
#       gcloud auth application-default login
# ──────────────────────────────────────────────────
# USAR_VERTEX=true
# VERTEX_PROJECT=mi-proyecto-gcp
# VERTEX_LOCATION=us-central1

# ───── Modelos Gemini ─────
GEMINI_MODELO=gemini-2.0-flash-001
GEMINI_MODELO_STT=gemini-2.0-flash-001
GEMINI_MODELO_VISION=gemini-2.0-flash-001
# Modelo barato para clasificación de riesgo y correcciones cortas:
GEMINI_MODELO_LIGERO=gemini-2.0-flash-lite-001

# ───── TTS ─────
# Opciones: edge (gratis, recomendado) | google | gemini | elevenlabs | openai
TTS_PROVEEDOR=edge
TTS_VOZ_EDGE=es-MX-DaliaNeural

# Google Cloud TTS (cuando TTS_PROVEEDOR=google)
TTS_IDIOMA=es-US
TTS_VOZ_CLOUD=es-US-Chirp3-HD-Aoede

# Gemini TTS (cuando TTS_PROVEEDOR=gemini, solo AI Studio)
TTS_VOZ=Kore

# Otros proveedores (opcional)
ELEVENLABS_API_KEY=
OPENAI_API_KEY=

# ───── Servidor FastAPI ─────
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=8765

# ───── Audio / VAD ─────
SAMPLE_RATE=16000
SILENCE_DURATION_S=1.4
SILENCE_THRESHOLD=0.012
VAD_RMS_UMBRAL=0.012
VAD_MIN_FRASE_S=0.5
FALLBACK_COOLDOWN_S=5.0
# Barge-in: GEM se calla si tú hablas mientras responde
BARGE_IN_ACTIVO=true

# ───── Optimización de costos (Vertex) ─────
# Cache LRU de embeddings RAG
EMBEDDING_CACHE_SIZE=256
# Resumir historial al pasar de N turnos (ahorra tokens en cada turno)
HISTORIAL_RESUMEN_TURNOS=16
HISTORIAL_MAX_TURNOS=24
# Cap a imágenes Vision (redimensiona antes de enviar)
VISION_MAX_PIXELS=786432
VISION_JPEG_QUALITY=70

# ───── Agente ─────
AGENTE_MAX_PASOS=20
"""

MEDIAPIPE_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)


def chequear_python() -> None:
    if sys.version_info < (3, 11):
        print(f"❌ Python 3.11+ requerido. Tienes {sys.version}")
        sys.exit(1)
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")


def crear_env() -> None:
    env_path = RAIZ / ".env"
    if env_path.exists():
        print(f"✓ .env ya existe en {env_path}")
        return
    env_path.write_text(PLANTILLA_ENV, encoding="utf-8")
    print(f"✓ .env creado en {env_path}")
    print("  ⚠  Edita .env y configura tus credenciales antes de ejecutar GEM.")


def crear_carpetas() -> None:
    for carpeta in ["data", "data/chromadb", "assets", "assets/avatar"]:
        ruta = RAIZ / carpeta
        ruta.mkdir(parents=True, exist_ok=True)
        print(f"✓ {carpeta}/")


def descargar_modelo_mediapipe() -> None:
    destino = RAIZ / "assets" / "face_landmarker.task"
    if destino.exists():
        print(f"✓ MediaPipe model: {destino.name} ({destino.stat().st_size // 1024} KB)")
        return
    print("⏳ Descargando modelo MediaPipe face_landmarker...")
    try:
        urllib.request.urlretrieve(MEDIAPIPE_URL, destino)
        print(f"✓ Descargado en {destino} ({destino.stat().st_size // 1024} KB)")
    except Exception as e:
        print(f"⚠  No se pudo descargar el modelo: {e}")
        print("   Se intentará al primer arranque.")


def inicializar_chromadb() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(RAIZ / ".env")
        sys.path.insert(0, str(RAIZ))
        import chromadb
        from backend.config import ajustes
        cliente = chromadb.PersistentClient(path=ajustes.chromadb_path)
        colecciones = ["conversaciones", "proyectos", "preferencias", "comandos"]
        print("✓ ChromaDB inicializado:")
        for nombre in colecciones:
            col = cliente.get_or_create_collection(nombre)
            print(f"    {nombre}: {col.count()} documentos")
    except Exception as e:
        print(f"⚠  ChromaDB: {e}")
        print("   (Se inicializará al primer arranque.)")


def validar_credenciales() -> None:
    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")

    usar_vertex = os.getenv("USAR_VERTEX", "false").lower() in ("true", "1", "yes")

    if usar_vertex:
        project = os.getenv("VERTEX_PROJECT", "").strip()
        location = os.getenv("VERTEX_LOCATION", "us-central1").strip()
        if not project:
            print("⚠  VERTEX_PROJECT no configurado en .env")
            return
        print(f"✓ Modo Vertex AI — proyecto={project}, región={location}")

        creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
        if creds_file:
            if Path(creds_file).exists():
                print(f"✓ GOOGLE_APPLICATION_CREDENTIALS={creds_file}")
            else:
                print(f"❌ GOOGLE_APPLICATION_CREDENTIALS apunta a archivo inexistente: {creds_file}")
        else:
            print("ℹ  Sin GOOGLE_APPLICATION_CREDENTIALS — se usará gcloud ADC")
            print("   Si no has ejecutado 'gcloud auth application-default login', hazlo ahora.")
    else:
        key = os.getenv("GEMINI_API_KEY", "").strip()
        if not key:
            print("⚠  GEMINI_API_KEY no configurada en .env")
            print("   Obtén una gratis en https://aistudio.google.com/apikey")
            return
        if len(key) < 20:
            print("⚠  GEMINI_API_KEY parece inválida (muy corta)")
            return
        print(f"✓ Modo AI Studio — GEMINI_API_KEY configurada ({key[:6]}...{key[-4:]})")


def verificar_dependencias() -> None:
    paquetes = {
        "google.genai":      "google-genai",
        "sounddevice":       "sounddevice",
        "numpy":             "numpy",
        "chromadb":          "chromadb",
        "fastapi":           "fastapi",
        "pydantic_settings": "pydantic-settings",
        "cv2":               "opencv-python",
        "mediapipe":         "mediapipe",
        "edge_tts":          "edge-tts",
    }
    opcionales = {
        "webrtcvad": "webrtcvad-wheels",
        "mss":       "mss",
        "PIL":       "Pillow",
        "pytest":    "pytest",
    }

    faltantes = []
    for modulo, paquete in paquetes.items():
        try:
            __import__(modulo)
            print(f"✓ {paquete}")
        except ImportError:
            print(f"❌ {paquete}")
            faltantes.append(paquete)

    print()
    for modulo, paquete in opcionales.items():
        try:
            __import__(modulo)
            print(f"✓ {paquete} (opcional)")
        except ImportError:
            print(f"·  {paquete} (opcional, recomendado)")

    from dotenv import load_dotenv
    load_dotenv(RAIZ / ".env")
    if os.getenv("USAR_VERTEX", "false").lower() in ("true", "1", "yes"):
        try:
            from google.cloud import texttospeech  # noqa
            print("✓ google-cloud-texttospeech")
        except ImportError:
            print("❌ google-cloud-texttospeech")
            faltantes.append("google-cloud-texttospeech")

    if faltantes:
        print(f"\nInstala los faltantes:\n  pip install {' '.join(faltantes)}")


def main() -> None:
    print("═" * 55)
    print("  GEM v3 — Inicialización")
    print("═" * 55)
    chequear_python()
    crear_carpetas()
    crear_env()
    print()
    print("── Dependencias ──────────────────────────────────────")
    verificar_dependencias()
    print()
    print("── Assets ────────────────────────────────────────────")
    descargar_modelo_mediapipe()
    print()
    print("── Base de datos ─────────────────────────────────────")
    inicializar_chromadb()
    print()
    print("── Credenciales ──────────────────────────────────────")
    validar_credenciales()
    print()
    print("═" * 55)
    print("  Setup completo")
    print("═" * 55)
    print()
    print("Próximos pasos:")
    print("  1. Edita .env con tus credenciales")
    print()
    print("  ── Opción A: AI Studio (gratis) ──")
    print("     USAR_VERTEX=false")
    print("     GEMINI_API_KEY=<tu key de aistudio.google.com>")
    print()
    print("  ── Opción B: Vertex AI ──")
    print("     USAR_VERTEX=true")
    print("     VERTEX_PROJECT=<project-id>")
    print("     gcloud auth application-default login")
    print()
    print("  2. Pon los frames del avatar en assets/avatar/<emocion>/")
    print("  3. Ejecuta: python -m backend.main")
    print()


if __name__ == "__main__":
    main()
