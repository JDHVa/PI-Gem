import asyncio
import json
import uuid
import logging
from datetime import datetime
from pathlib import Path
import chromadb
from backend.config import ajustes
from backend.modulos.gemini_cliente import generar_embedding

log = logging.getLogger("gem.memoria")

COLECCIONES = ["conversaciones", "proyectos", "preferencias", "comandos"]


class MemoriaRAG:
    def __init__(self):
        self._cliente = chromadb.PersistentClient(path=ajustes.chromadb_path)
        self._cols: dict[str, chromadb.Collection] = {
            nombre: self._cliente.get_or_create_collection(
                name=nombre,
                metadata={"hnsw:space": "cosine"},
            )
            for nombre in COLECCIONES
        }
        self._vault_path = Path(ajustes.obsidian_vault_path)
        for nombre in COLECCIONES:
            (self._vault_path / nombre).mkdir(parents=True, exist_ok=True)

    async def guardar(
        self,
        texto: str,
        coleccion: str = "conversaciones",
        metadata: dict | None = None,
        titulo: str | None = None,
    ) -> None:
        if coleccion not in self._cols:
            raise ValueError(f"Colección desconocida: {coleccion}")
        
        doc_id = str(uuid.uuid4())
        nombre_archivo = f"{titulo}.md" if titulo else f"nota_{doc_id[:8]}.md"
        ruta_archivo = self._vault_path / coleccion / nombre_archivo
        
        meta = {
            "timestamp": datetime.now().isoformat(),
            "coleccion": coleccion,
            "archivo": nombre_archivo,
        }
        if metadata:
            meta.update(metadata)
            
        # Escribir en la bóveda de Obsidian
        contenido_md = "---\n"
        for k, v in meta.items():
            contenido_md += f"{k}: {v}\n"
        contenido_md += f"---\n\n{texto}\n"
        try:
            with ruta_archivo.open("w", encoding="utf-8") as f:
                f.write(contenido_md)
        except Exception as e:
            log.warning("No se pudo guardar en Obsidian: %s", e)

        embedding = await generar_embedding(texto)
        self._cols[coleccion].add(
            ids=[doc_id],
            embeddings=[embedding],
            documents=[texto],
            metadatas=[meta],
        )

    async def sincronizar_desde_obsidian(self) -> None:
        """Lee la bóveda de Obsidian y actualiza ChromaDB con notas nuevas."""
        for coleccion in COLECCIONES:
            ruta_col = self._vault_path / coleccion
            if not ruta_col.exists():
                continue
            
            col_db = self._cols[coleccion]
            existentes = col_db.get()
            ids_existentes = set(existentes["ids"]) if existentes and "ids" in existentes else set()
            
            for archivo in ruta_col.glob("*.md"):
                doc_id = f"obs_{archivo.stem}"
                if doc_id in ids_existentes:
                    continue
                
                try:
                    contenido = archivo.read_text(encoding="utf-8")
                    partes = contenido.split("---\n")
                    texto_puro = partes[-1].strip() if len(partes) > 2 else contenido.strip()
                    if not texto_puro:
                        continue
                    
                    emb = await generar_embedding(texto_puro)
                    col_db.add(
                        ids=[doc_id],
                        embeddings=[emb],
                        documents=[texto_puro],
                        metadatas=[{"fuente": "obsidian", "archivo": archivo.name}]
                    )
                    log.info("Indexado desde Obsidian: %s/%s", coleccion, archivo.name)
                except Exception as e:
                    log.warning("Error sincronizando %s: %s", archivo.name, e)

    async def _buscar_con_embedding(
        self, embedding: list[float], coleccion: str, k: int,
    ) -> list[str]:
        col = self._cols.get(coleccion)
        if col is None:
            return []
        total = col.count()
        if total == 0:
            return []
        try:
            n = min(k, total)
            res = col.query(query_embeddings=[embedding], n_results=n)
            return res["documents"][0] if res["documents"] else []
        except Exception as e:
            log.warning("Búsqueda en %s falló: %s", coleccion, e)
            return []

    async def buscar(
        self, query: str, coleccion: str = "conversaciones", k: int | None = None,
    ) -> list[str]:
        if coleccion not in self._cols:
            return []
        try:
            emb = await generar_embedding(query)
            return await self._buscar_con_embedding(emb, coleccion, k or ajustes.rag_top_k)
        except Exception as e:
            log.warning("Embedding query falló: %s", e)
            return []

    async def buscar_todo(self, query: str) -> list[str]:
        """Calcula el embedding UNA vez y busca en paralelo en todas las colecciones."""
        try:
            emb = await generar_embedding(query)
        except Exception as e:
            log.warning("Embedding query falló: %s", e)
            return []

        cols_a_buscar = ["conversaciones", "proyectos", "preferencias"]
        tareas = [self._buscar_con_embedding(emb, c, 2) for c in cols_a_buscar]
        resultados = await asyncio.gather(*tareas, return_exceptions=True)

        fragmentos: list[str] = []
        for r in resultados:
            if isinstance(r, list):
                fragmentos.extend(r)
        return fragmentos

    async def guardar_comando_exitoso(self, instruccion: str, comando: str) -> None:
        await self.guardar(
            f"Instrucción: {instruccion}\nComando: {comando}",
            coleccion="comandos",
            metadata={"tipo": "comando_exitoso"},
        )

    def estadisticas(self) -> dict[str, int]:
        return {nombre: col.count() for nombre, col in self._cols.items()}


# ── Persistencia de historial (no requiere embeddings) ─────────────────

class HistorialPersistente:
    """
    Mantiene el historial de la sesión actual en disco.
    Al reiniciar se recupera el contexto previo.
    """
    def __init__(self, path: str | None = None):
        self._path = Path(path or ajustes.historial_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def cargar(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception as e:
            log.warning("Historial inválido: %s — empezando vacío", e)
            return []

    def guardar(self, historial: list[dict]) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as f:
                json.dump(historial[-ajustes.historial_max_turnos * 2:], f, ensure_ascii=False)
        except Exception as e:
            log.warning("No se pudo persistir historial: %s", e)

    def limpiar(self) -> None:
        try:
            if self._path.exists():
                self._path.unlink()
        except Exception:
            pass
