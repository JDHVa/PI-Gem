"""
Script de inicialización de GEM.
Ejecutar UNA SOLA VEZ tras instalar las dependencias:

  python inicializar.py

Hace:
  1. Verifica versión de Python (>=3.11).
  2. Crea .env si no existe.
  3. Crea las carpetas data/, assets/.
  4. Descarga el modelo de MediaPipe (face_landmarker.task).
  5. Inicializa las colecciones de ChromaDB.
  6. Valida la API key de Gemini y avisa sobre Picovoice.
"""
import os
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

PLANTILLA_ENV = """# ───── GEM — variables de entorno ─────

# ▼ Obligatoria
# Obtén tu key gratis en https://aistudio.google.com/apikey
GEMINI_API_KEY=

# ───── Modelos Gemini (opcional) ─────
# GEMINI_MODELO=gemini-2.5-flash
# GEMINI_MODELO_STT=gemini-2.5-flash
# GEMINI_MODELO_TTS=gemini-2.5-flash-preview-tts

# Voz prebuilt: Aoede, Charon, Fenrir, Kore, Leda, Orus, Puck, Zephyr
TTS_VOZ=Kore

# ───── Servidor FastAPI ─────
FASTAPI_HOST=127.0.0.1
FASTAPI_PORT=8765

# ───── Wake word ─────
# Crea cuenta gratis en https://console.picovoice.ai/ para obtener AccessKey.
# Si lo dejas vacío, GEM usa detector RMS como fallback.
PICOVOICE_ACCESS_KEY=

# ───── VTube Studio ─────
VTUBE_WS_PORT=8001
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


def crear_carpetas() -> None:
    for carpeta in ["data", "data/chromadb", "assets"]:
        ruta = RAIZ / carpeta
        ruta.mkdir(parents=True, exist_ok=True)
        print(f"✓ {carpeta}/")


def descargar_modelo_mediapipe() -> None:
    destino = RAIZ / "assets" / "face_landmarker.task"
    if destino.exists():
        print(f"✓ MediaPipe model: {destino.name} ({destino.stat().st_size // 1024} KB)")
        return
    print("⏳ Descargando modelo MediaPipe...")
    try:
        urllib.request.urlretrieve(MEDIAPIPE_URL, destino)
        print(f"✓ Descargado en {destino} ({destino.stat().st_size // 1024} KB)")
    except Exception as e:
        print(f"❌ No se pudo descargar el modelo: {e}")
        print("   Se descargará automáticamente al primer arranque.")


def inicializar_chromadb() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(RAIZ / ".env")
        sys.path.insert(0, str(RAIZ))
        from backend.modulos.memoria import MemoriaRAG, COLECCIONES

        m = MemoriaRAG()
        stats = m.estadisticas()
        print("✓ ChromaDB inicializado:")
        for col in COLECCIONES:
            print(f"    {col}: {stats.get(col, 0)} documentos")
    except Exception as e:
        print(f"⚠  ChromaDB no se pudo inicializar todavía: {e}")
        print("   (Se inicializará al primer arranque.)")


def validar_gemini() -> None:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        print("⚠  GEMINI_API_KEY no configurada en .env")
        print("   Edita el archivo .env y agrega tu key antes de ejecutar GEM.")
        return
    if len(key) < 20:
        print("⚠  GEMINI_API_KEY parece inválida (muy corta)")
        return
    print(f"✓ GEMINI_API_KEY configurada ({key[:6]}...{key[-4:]})")


def informar_picovoice() -> None:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
    pv = os.getenv("PICOVOICE_ACCESS_KEY", "").strip()
    if pv:
        print(f"✓ PICOVOICE_ACCESS_KEY configurada — wake word: 'jarvis'")
    else:
        print("ℹ  PICOVOICE_ACCESS_KEY vacía — usando detector RMS como fallback")
        print("   Para wake word real ('jarvis'), regístrate en https://console.picovoice.ai/")


def main() -> None:
    print("═" * 50)
    print("  GEM — Inicialización")
    print("═" * 50)
    chequear_python()
    crear_carpetas()
    crear_env()
    descargar_modelo_mediapipe()
    inicializar_chromadb()
    validar_gemini()
    informar_picovoice()
    print()
    print("═" * 50)
    print("  Setup completo")
    print("═" * 50)
    print()
    print("Próximos pasos:")
    print("  1. Edita .env y agrega tu GEMINI_API_KEY")
    print("  2. (Opcional) agrega PICOVOICE_ACCESS_KEY para wake word real")
    print("  3. Ejecuta:               python -m backend.main")
    print("  4. (Opcional) Tauri:      cd src-tauri && cargo tauri dev")
    print()


if __name__ == "__main__":
    main()
