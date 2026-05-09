# GEM — Asistente de IA personal

Asistente local con voz, visión y control de PowerShell. Vive en el system tray, te escucha por wake-word, te ve por la cámara (detecta tu emoción), tiene memoria a largo plazo (RAG sobre ChromaDB) y puede mover un avatar de VTube Studio mientras habla.

**Todo el procesamiento pesado se delega a Gemini API** (LLM, STT, TTS, embeddings). La PC solo corre lo estrictamente necesario:
- Captura de audio (sounddevice)
- Wake word (pvporcupine, ~20 MB)
- Visión (MediaPipe FaceMesh, ~180 MB)
- Memoria vectorial (ChromaDB)

**RAM esperada: ~470 MB sin VTube, ~770 MB con VTube.**

## Arquitectura

```
  ┌─────────────────┐
  │  Tauri (Rust)   │  ← system tray, lanza el backend
  └────────┬────────┘
           │ HTTP / WebSocket
  ┌────────▼─────────────────────────────────────┐
  │  FastAPI (Python)                            │
  │  ┌───────────────────────────────────────┐   │
  │  │           Orquestador                 │   │
  │  └────┬─────────┬────────────┬───────────┘   │
  │       │         │            │               │
  │  ┌────▼──┐ ┌────▼─────┐  ┌──▼─────┐          │
  │  │ Audio │ │  Visión  │  │Memoria │          │
  │  │Wake-W │ │MediaPipe │  │ Chroma │          │
  │  │capture│ │ Emoción  │  │  RAG   │          │
  │  │       │ │ Identidad│  │        │          │
  │  └───┬───┘ └──────────┘  └────────┘          │
  │      │                                       │
  │  ┌───▼───────────────────────────────────┐   │
  │  │         Gemini API                    │   │
  │  │  - LLM (gemini-2.5-flash)             │   │
  │  │  - STT (audio → texto)                │   │
  │  │  - TTS (texto → audio PCM 24kHz)      │   │
  │  │  - Embeddings (text-embedding-004)    │   │
  │  └───────────────────────────────────────┘   │
  │                                              │
  │  ┌────────┐ ┌──────────┐                     │
  │  │PowerSh.│ │ VTube    │                     │
  │  │+heal AI│ │ Lipsync  │                     │
  │  └────────┘ └──────────┘                     │
  └──────────────────────────────────────────────┘
```

## Instalación

### Requisitos

- Windows 10/11 (PowerShell)
- Python 3.11 o superior
- Rust + Cargo (solo si quieres compilar Tauri)
- Cámara web y micrófono
- API key de **Google AI Studio** (gratis): https://aistudio.google.com/apikey
- (Opcional) Access key de **Picovoice** para wake word real: https://console.picovoice.ai/
- (Opcional) **VTube Studio** corriendo con su API habilitada

### Pasos

```powershell
# 1. Entrar al proyecto
cd Gem

# 2. Crear venv
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Inicializar (crea .env, descarga modelo MediaPipe)
python inicializar.py

# 5. Editar .env y poner tu GEMINI_API_KEY
notepad .env

# 6. Arrancar el backend
python -m backend.main

# 7. (Alternativa) Compilar Tauri y arrancar todo desde el tray
cd src-tauri
cargo tauri dev
```

## Wake word

Hay dos modos:

| Modo | Cómo activar | Requiere | Frase |
|------|--------------|----------|-------|
| **Porcupine** (recomendado) | `PICOVOICE_ACCESS_KEY=...` en `.env` | Cuenta gratis Picovoice | "jarvis" |
| **RMS fallback** | Default sin access key | Nada | Cualquier voz sostenida (umbral configurable) |

El modo Porcupine usa los keywords built-in: `alexa`, `computer`, `hey google`, `hey siri`, `jarvis`, `picovoice`, `terminator`, etc. Para una keyword custom como "gem" hay que entrenarla en Picovoice Console y modificar el código para apuntar al `.ppn` (no soportado directamente vía `.env` aún).

## Endpoints (FastAPI en `127.0.0.1:8765`)

| Método | Ruta                   | Descripción                                   |
|--------|------------------------|-----------------------------------------------|
| GET    | `/health`              | Status simple                                  |
| GET    | `/estado`              | Estado completo (visión, vtube, memoria…)      |
| POST   | `/chat`                | `{ "texto": "..." }` → respuesta de GEM        |
| POST   | `/registrar_identidad` | Guarda tu cara como referencia                 |
| POST   | `/guardar_contexto`    | Guarda info en una colección RAG               |
| POST   | `/silenciar`           | `{ "silenciado": true }` ignora wake-word     |
| DELETE | `/historial`           | Limpia el historial conversacional             |
| WS     | `/ws`                  | WebSocket bidireccional                        |

## Voces de Gemini TTS

Las voces prebuilt actuales (cambiar en `.env` con `TTS_VOZ=...`):

| Voz | Estilo |
|-----|--------|
| Aoede | Suave, melódica |
| Charon | Grave, autoritaria |
| Fenrir | Agresiva, marcada |
| **Kore** (default) | Neutra, clara |
| Leda | Joven, ligera |
| Orus | Profesional |
| Puck | Animada, juguetona |
| Zephyr | Brillante |

Todas hablan español de México con el modelo `gemini-2.5-flash-preview-tts`.

## Documentos

- `docs/db_instrucciones.md` — cómo usar las colecciones de la memoria RAG
- `docs/guia_avatar_blender_vrm.md` — cómo crear tu avatar para VTube Studio

## Estructura

```
Gem/
├── src-tauri/        # App de escritorio (Rust)
├── backend/          # FastAPI + módulos (Python)
│   ├── modulos/      # audio, vision, vtube, memoria, powershell, gemini_cliente
│   └── prompts/
├── frontend/         # HTML mínimo para Tauri
├── assets/           # Modelo de MediaPipe (descargado)
├── data/             # ChromaDB y token de VTube (generados)
├── docs/
├── inicializar.py
├── requirements.txt
└── .env
```

## Licencia

Personal.
