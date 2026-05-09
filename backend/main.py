import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from backend.orquestador import Orquestador
from backend.config import ajustes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("gem.main")

orquestador = Orquestador()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Iniciando GEM en %s:%s", ajustes.fastapi_host, ajustes.fastapi_port)
    await orquestador.iniciar()
    yield
    log.info("Deteniendo GEM")
    await orquestador.detener()


app = FastAPI(title="GEM Backend", version="1.0.0", lifespan=lifespan)


class PeticionTexto(BaseModel):
    texto: str


class PeticionContexto(BaseModel):
    texto: str
    coleccion: str = "proyectos"


class PeticionSilenciar(BaseModel):
    silenciado: bool = True


@app.get("/health")
async def health():
    return {"status": "ok", "puerto": ajustes.fastapi_port}


@app.get("/estado")
async def estado():
    return orquestador.get_estado()


@app.post("/chat")
async def chat(peticion: PeticionTexto):
    if not peticion.texto.strip():
        raise HTTPException(status_code=400, detail="Texto vacío")
    respuesta = await orquestador.procesar_texto(peticion.texto)
    return {"respuesta": respuesta}


@app.post("/registrar_identidad")
async def registrar_identidad():
    exito = await orquestador.registrar_identidad()
    return {
        "exito": exito,
        "mensaje": "Identidad registrada." if exito else "No se detectó rostro.",
    }


@app.post("/guardar_contexto")
async def guardar_contexto(peticion: PeticionContexto):
    await orquestador.guardar_contexto(peticion.texto, peticion.coleccion)
    return {"guardado": True, "coleccion": peticion.coleccion}


@app.post("/silenciar")
async def silenciar(peticion: PeticionSilenciar):
    orquestador.silenciar(peticion.silenciado)
    return {"silenciado": peticion.silenciado}


@app.delete("/historial")
async def limpiar_historial():
    orquestador._historial.clear()
    return {"limpiado": True}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            tipo = data.get("tipo")

            if tipo == "chat":
                respuesta = await orquestador.procesar_texto(data.get("texto", ""))
                await ws.send_json({"tipo": "respuesta", "texto": respuesta})

            elif tipo == "estado":
                await ws.send_json({"tipo": "estado", **orquestador.get_estado()})

            elif tipo == "registrar_identidad":
                exito = await orquestador.registrar_identidad()
                await ws.send_json({"tipo": "identidad", "exito": exito})

            elif tipo == "guardar_contexto":
                await orquestador.guardar_contexto(
                    data.get("texto", ""),
                    data.get("coleccion", "proyectos"),
                )
                await ws.send_json({"tipo": "guardado", "exito": True})

            elif tipo == "silenciar":
                orquestador.silenciar(bool(data.get("silenciado", True)))
                await ws.send_json(
                    {"tipo": "silenciado", "valor": bool(data.get("silenciado", True))}
                )

            elif tipo == "ping":
                await ws.send_json({"tipo": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.exception("Error en websocket")
        try:
            await ws.send_json({"tipo": "error", "detalle": str(e)})
        except Exception:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=ajustes.fastapi_host,
        port=ajustes.fastapi_port,
        log_level="info",
    )
