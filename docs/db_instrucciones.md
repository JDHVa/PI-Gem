# Guía de la base de datos vectorial (ChromaDB)

GEM usa **ChromaDB** en modo persistente local. Toda la memoria vive en `data/chromadb/`.

## Colecciones

Hay cuatro colecciones, cada una con un propósito específico:

| Colección       | Qué contiene                                              | Cuándo se llena                       |
|-----------------|-----------------------------------------------------------|---------------------------------------|
| `conversaciones`| Cada turno (Usuario + GEM) de las charlas pasadas.        | Automático, tras cada respuesta.      |
| `proyectos`     | Información de tus proyectos: stack, decisiones, TODOs.   | Manual, vía `/guardar_contexto`.      |
| `preferencias`  | Tus gustos, costumbres, datos personales relevantes.      | Manual, vía `/guardar_contexto`.      |
| `comandos`      | Comandos PowerShell que funcionaron + la instrucción.     | Automático, tras ejecución exitosa.   |

## Cómo se usa internamente

Cuando hablas con GEM:

1. Tu mensaje se convierte en embedding con `text-embedding-004` (Gemini).
2. Se busca en `conversaciones`, `proyectos` y `preferencias` los 2 fragmentos más similares de cada una.
3. Esos fragmentos se inyectan al system prompt como "Contexto relevante".
4. El modelo responde sabiendo de qué le hablas.

## Guardar contexto manualmente

### Vía HTTP

```bash
curl -X POST http://127.0.0.1:8765/guardar_contexto \
  -H "Content-Type: application/json" \
  -d '{"texto": "Mi proyecto principal es GEM, un asistente local en Python+Rust.", "coleccion": "proyectos"}'
```

### Vía WebSocket

```json
{
  "tipo": "guardar_contexto",
  "texto": "Prefiero respuestas cortas y directas, sin disculpas.",
  "coleccion": "preferencias"
}
```

## Buenas prácticas para alimentar la memoria

- **Un hecho por entrada.** No metas un tutorial entero; mete frases atómicas.
  - ✅ `"Uso PowerShell 7, no Windows PowerShell 5."`
  - ❌ Pegarle el README completo de un proyecto.
- **Lenguaje natural.** El embedding entiende mejor frases que listas.
- **Concreto > genérico.** "Trabajo con FastAPI y Tauri en GEM" pesa más que "soy programador".

## Inspeccionar la memoria

```python
import chromadb
cliente = chromadb.PersistentClient(path="data/chromadb")
col = cliente.get_collection("preferencias")
print(col.count(), "documentos")
print(col.peek(5))   # primeros 5 con embeddings
```

## Limpiar

```python
import chromadb
cliente = chromadb.PersistentClient(path="data/chromadb")
cliente.delete_collection("conversaciones")  # borra y vuelve a crearse vacía al reiniciar
```

O simplemente borra la carpeta `data/chromadb/` (¡lo pierdes todo!).

## Cambiar el `top-k` del RAG

Editar `.env`:
```
RAG_TOP_K=5
```

El default es 3. Subirlo da más contexto pero también más ruido y más tokens al prompt.

## Limitaciones conocidas

- ChromaDB usa HNSW con distancia coseno; es bueno pero no perfecto para textos muy cortos (< 5 palabras).
- No hay re-ranking; si necesitas precisión quirúrgica, considera añadir `rerank` con un cross-encoder.
- Los embeddings de Gemini cuestan llamadas a la API. Cada `guardar` y cada `buscar` consume cuota.
