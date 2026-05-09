import uuid
import logging
from datetime import datetime
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

    async def guardar(
        self,
        texto: str,
        coleccion: str = "conversaciones",
        metadata: dict | None = None,
    ) -> None:
        if coleccion not in self._cols:
            raise ValueError(f"Colección desconocida: {coleccion}")
        embedding = await generar_embedding(texto)
        meta = {
            "timestamp": datetime.now().isoformat(),
            "coleccion": coleccion,
        }
        if metadata:
            meta.update(metadata)
        self._cols[coleccion].add(
            ids=[str(uuid.uuid4())],
            embeddings=[embedding],
            documents=[texto],
            metadatas=[meta],
        )

    async def buscar(
        self,
        query: str,
        coleccion: str = "conversaciones",
        k: int | None = None,
    ) -> list[str]:
        if coleccion not in self._cols:
            return []
        col = self._cols[coleccion]
        total = col.count()
        if total == 0:
            return []
        try:
            embedding = await generar_embedding(query)
            n = min(k or ajustes.rag_top_k, total)
            resultados = col.query(
                query_embeddings=[embedding],
                n_results=n,
            )
            return resultados["documents"][0] if resultados["documents"] else []
        except Exception as e:
            log.warning("Fallo en búsqueda RAG: %s", e)
            return []

    async def buscar_todo(self, query: str) -> list[str]:
        fragmentos: list[str] = []
        for col in ["conversaciones", "proyectos", "preferencias"]:
            fragmentos.extend(await self.buscar(query, col, k=2))
        return fragmentos

    async def guardar_comando_exitoso(self, instruccion: str, comando: str) -> None:
        await self.guardar(
            f"Instrucción: {instruccion}\nComando: {comando}",
            coleccion="comandos",
            metadata={"tipo": "comando_exitoso"},
        )

    def estadisticas(self) -> dict[str, int]:
        return {nombre: col.count() for nombre, col in self._cols.items()}
