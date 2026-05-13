# GEM v3 — Asistente de IA Personal

Asistente de voz local con avatar animado, agente con function calling, memoria RAG,
visión por cámara, ejecución de comandos y rutinas guardadas.

Backend en Python (FastAPI + Gemini), frontend en HTML/JS modular dentro de Tauri.

## Arquitectura

```
                           ┌── Conversación ── Gemini Flash + RAG ─┐
Usuario habla → VAD → STT ─┤                                       ├── TTS → Bocinas
                           ├── Agente   ───── function calling ────┤    (con barge-in)
                           ├── Skills   ───── bash directo ────────┤
                           └── Pantalla ───── Gemini Vision ───────┘
                                              ↕
                                       Memoria RAG (ChromaDB)
                                       Historial persistente
                                       Perfil visual del usuario
```

## Quickstart

```bash
git clone <repo>
cd gem
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python inicializar.py             # crea .env, descarga modelo MediaPipe
# editar .env con tu GEMINI_API_KEY
python -m backend.main
```

Frontend: abrir `frontend/index.html` con Tauri, o servirlo y abrirlo en el navegador.

## Modos de operación

### A) Google AI Studio (gratis)
```env
USAR_VERTEX=false
GEMINI_API_KEY=AIza...
```
Obtén tu key en https://aistudio.google.com/apikey

### B) Vertex AI (recomendado para uso prolongado)
```env
USAR_VERTEX=true
VERTEX_PROJECT=tu-proyecto
VERTEX_LOCATION=us-central1
```
```bash
gcloud auth application-default login
```

## Capacidades

### 1. Conversación con memoria
Cada conversación se vectoriza en ChromaDB. GEM recupera contexto relevante de
conversaciones previas, proyectos y preferencias en cada turno.

El historial se persiste entre reinicios en `data/historial.json`. Al pasar de
N turnos se resume automáticamente para mantener tokens bajos.

### 2. Agente (function calling)
Cuando dices algo como "crea una carpeta llamada X y mueve los .py adentro",
GEM enruta al agente, que decide qué herramientas usar (escribir_archivo,
mover_archivo, listar_directorio, etc.) hasta completar la tarea.

Herramientas disponibles: `bash`, `leer_archivo`, `escribir_archivo`,
`editar_archivo`, `listar_directorio`, `crear_directorio`,
`buscar_en_archivos`, `mover_archivo`, `eliminar`.

`eliminar` requiere confirmación explícita del usuario en un modal.

### 3. Skills (rutinas guardadas)
```
Tú: "guarda rutina mañana: code; spotify; chrome github.com"
GEM: Rutina 'mañana' guardada con 3 pasos.

Tú: "ejecuta rutina mañana"
GEM: Ejecutando... Rutina completada.
```

Las rutinas viven en `data/skills.json` y se ejecutan como bash directo,
**sin gastar tokens del LLM**.

### 4. Visión por cámara
MediaPipe detecta tu emoción y presencia continuamente (sin gastar tokens).
GEM espeja tu emoción en el avatar.

### 5. Visión de pantalla bajo demanda
```
Tú: "mira mi pantalla, ¿qué error tiene este código?"
```
GEM captura tu pantalla y la manda a Gemini Vision con tu pregunta.

### 6. Modo proactivo
Si lo activas (botón 👁 o `/proactivo`), GEM analiza tu cámara con Vision
**solo** cuando MediaPipe detecta pre-triggers reales: emoción sostenida,
cambio de fondo, ausencia prolongada, etc. Nunca en intervalos ciegos.

### 7. Barge-in
Si hablas mientras GEM responde, GEM se calla. Lo controla `BARGE_IN_ACTIVO`.

## Optimización de costos (Vertex AI)

GEM v3 está diseñado para minimizar tokens enviados a Vertex:

| Optimización | Variable | Default |
|---|---|---|
| Cache LRU de embeddings RAG | `EMBEDDING_CACHE_SIZE` | 256 |
| Resumen del historial al exceder N turnos | `HISTORIAL_RESUMEN_TURNOS` | 16 |
| Redimensionado de imágenes Vision | `VISION_MAX_PIXELS` | 786432 |
| Calidad JPEG Vision | `VISION_JPEG_QUALITY` | 70 |
| Modelo ligero para tareas baratas | `GEMINI_MODELO_LIGERO` | flash-lite |
| Cooldown observador proactivo (s) | (constante) | 900 |
| Pasos máximos del agente | `AGENTE_MAX_PASOS` | 20 |

Detalles en `CHANGELOG.md`.

## Tests

```bash
v
pytest -v
```

Cubre: herramientas (incluido el blindaje contra auto-confirmación del LLM),
skills, persistencia de historial, cache de embeddings, regex del orquestador.

## Estructura del proyecto

```
gem/
├── backend/
│   ├── main.py              FastAPI app
│   ├── config.py            Pydantic settings
│   ├── orquestador.py       Routing: conversación / agente / skills / screenshot
│   ├── modulos/
│   │   ├── gemini_cliente.py   LLM + embeddings + STT + TTS + Vision (con cache)
│   │   ├── agente.py           Function calling loop
│   │   ├── herramientas.py     Tools del agente
│   │   ├── memoria.py          ChromaDB + historial persistente
│   │   ├── skills.py           Rutinas guardadas
│   │   ├── screenshot.py       Captura + análisis de pantalla
│   │   ├── audio.py            STT + TTS + barge-in
│   │   ├── wake_word.py        VAD (WebRTC o RMS)
│   │   ├── vision.py           MediaPipe (emociones, rostro)
│   │   ├── observador.py       Modo proactivo
│   │   ├── perfil_usuario.py   Memoria visual del usuario
│   │   └── broadcaster.py      WebSocket broadcast
│   └── prompts/system_prompt.py
├── frontend/
│   ├── index.html           Shell HTML modular
│   ├── css/main.css
│   ├── js/                  Módulos ES6
│   │   ├── main.js          Entry point + namespace window.GEM
│   │   ├── ws.js            WebSocket + reconexión
│   │   ├── avatar.js        Animación por emoción
│   │   ├── chat.js          Envío de texto
│   │   ├── status.js        Dots + panel
│   │   ├── skills.js        Modal de rutinas
│   │   ├── confirm.js       Modal de confirmación
│   │   ├── agent.js         Trazas en vivo del agente
│   │   └── app.js           Handlers misc
│   └── assets/avatar/       Frames pixel-art (tú los pones)
├── tests/                   pytest
├── src-tauri/               Wrapper de escritorio
├── inicializar.py
├── requirements.txt
├── .env.example
└── CHANGELOG.md
```

## Frases que entiende GEM (además de conversación)

| Frase | Qué hace |
|---|---|
| "crea/instala/ejecuta/mueve/lista/busca..." | Activa el agente |
| "guarda rutina <nombre>: cmd1; cmd2; cmd3" | Crea una skill |
| "ejecuta rutina <nombre>" | Corre los comandos guardados |
| "mira/revisa/analiza mi pantalla" | Screenshot + Vision |
| "elimina/borra <ruta>" | Pide confirmación en el frontend |

## Licencia

MIT
