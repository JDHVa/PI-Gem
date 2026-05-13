import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.orquestador import Orquestador
from backend.config import ajustes
from backend.modulos.broadcaster import broadcaster
from fastapi.responses import StreamingResponse, Response

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
log = logging.getLogger("gem.main")

orquestador = Orquestador(broadcaster)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Iniciando GEM en %s:%s", ajustes.fastapi_host, ajustes.fastapi_port)
    await orquestador.iniciar()
    yield
    await orquestador.detener()


app = FastAPI(title="GEM Backend", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


class PeticionTexto(BaseModel):
    texto: str


class PeticionContexto(BaseModel):
    texto: str
    coleccion: str = "proyectos"


class PeticionSilenciar(BaseModel):
    silenciado: bool = True


class PeticionProactivo(BaseModel):
    activo: bool


class PeticionPerfil(BaseModel):
    descripcion: str


class PeticionConfirmacion(BaseModel):
    id: str
    autorizado: bool


class PeticionSkill(BaseModel):
    nombre: str
    comandos: list[str]
    descripcion: str = ""


class PeticionMute(BaseModel):
    muteado: bool


class PeticionIdentidad(BaseModel):
    muestras: int = 10
    timeout_s: float = 8.0


@app.get("/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}


@app.get("/estado")
async def estado():
    return orquestador.get_estado()


@app.post("/chat")
async def chat(p: PeticionTexto):
    if not p.texto.strip():
        raise HTTPException(400, "Texto vacío")
    respuesta = await orquestador.procesar_texto(p.texto)
    return {"respuesta": respuesta}


@app.post("/mute_microfono")
async def mute_microfono(p: PeticionMute):
    orquestador.mutear_microfono(p.muteado)
    return {"muteado": p.muteado}


@app.post("/registrar_identidad")
async def registrar_identidad(p: PeticionIdentidad = None):
    p = p or PeticionIdentidad()
    return await orquestador.registrar_identidad(p.muestras, p.timeout_s)


@app.delete("/identidad")
async def borrar_identidad():
    await orquestador.borrar_identidad()
    return {"borrado": True}


@app.get("/camara/snapshot")
async def camara_snapshot(anotado: bool = True):
    jpeg = orquestador._vision.get_snapshot_jpeg(anotado=anotado)
    if jpeg is None:
        raise HTTPException(503, "Cámara no disponible")
    return Response(content=jpeg, media_type="image/jpeg")


@app.get("/camara/stream")
async def camara_stream(anotado: bool = True, fps: int = 8):
    gen = orquestador._vision.stream_mjpeg(fps=fps, anotado=anotado)
    return StreamingResponse(
        gen,
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.post("/registrar_perfil")
async def registrar_perfil(p: PeticionPerfil):
    return await orquestador.registrar_perfil_inicial(p.descripcion)


@app.post("/proactivo")
async def set_proactivo(p: PeticionProactivo):
    orquestador.set_proactivo(p.activo)
    return {"proactivo": p.activo}


@app.post("/guardar_contexto")
async def guardar_contexto(p: PeticionContexto):
    await orquestador.guardar_contexto(p.texto, p.coleccion)
    return {"guardado": True}


@app.post("/silenciar")
async def silenciar(p: PeticionSilenciar):
    orquestador.silenciar(p.silenciado)
    return {"silenciado": p.silenciado}


@app.delete("/historial")
async def limpiar_historial():
    orquestador.limpiar_historial()
    return {"limpiado": True}


@app.post("/confirmar")
async def confirmar(p: PeticionConfirmacion):
    ok = orquestador.responder_confirmacion(p.id, p.autorizado)
    if not ok:
        raise HTTPException(404, "ID de confirmación desconocido o expirado")
    return {"recibido": True}


@app.get("/skills")
async def listar_skills():
    return {"skills": orquestador.listar_skills()}


@app.post("/skills")
async def guardar_skill(p: PeticionSkill):
    orquestador._skills.guardar(p.nombre, p.comandos, p.descripcion)
    return {"guardado": True}


@app.delete("/skills/{nombre}")
async def eliminar_skill(nombre: str):
    ok = orquestador.eliminar_skill(nombre)
    return {"eliminado": ok}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await broadcaster.connect(ws)
    try:
        while True:
            data = await ws.receive_json()
            tipo = data.get("tipo")
            if tipo == "chat":
                r = await orquestador.procesar_texto(data.get("texto", ""))
                await ws.send_json({"tipo": "respuesta", "texto": r})
            elif tipo == "estado":
                await ws.send_json({"tipo": "estado", **orquestador.get_estado()})
            elif tipo == "proactivo":
                orquestador.set_proactivo(bool(data.get("activo", False)))
                await ws.send_json({"tipo": "proactivo", "activo": data.get("activo")})
            elif tipo == "confirmar":
                orquestador.responder_confirmacion(
                    data.get("id", ""), bool(data.get("autorizado", False))
                )
            elif tipo == "ping":
                await ws.send_json({"tipo": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        log.exception("WS error")
    finally:
        broadcaster.disconnect(ws)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.main:app",
        host=ajustes.fastapi_host,
        port=ajustes.fastapi_port,
        log_level="info",
    )
