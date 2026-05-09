import asyncio
import json
import logging
from pathlib import Path
import numpy as np
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException
from backend.config import ajustes

log = logging.getLogger("gem.vtube")

EXPRESIONES: dict[str, str] = {
    "alegre": "Joy",
    "estresado": "Angry",
    "confundido": "Sorrow",
    "sorprendido": "Fun",
    "neutro": "Neutral",
}


class VTubeCliente:
    def __init__(self):
        self._uri = f"ws://localhost:{ajustes.vtube_ws_port}"
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._conectado: bool = False
        self._token: str | None = None
        self._expresion_actual: str | None = None
        self._token_path = Path(ajustes.vtube_token_path)

    def esta_conectado(self) -> bool:
        return self._conectado

    def _cargar_token(self) -> str | None:
        try:
            if self._token_path.exists():
                return self._token_path.read_text(encoding="utf-8").strip() or None
        except Exception:
            return None
        return None

    def _guardar_token(self, token: str) -> None:
        try:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(token, encoding="utf-8")
        except Exception as e:
            log.warning("No se pudo guardar token VTube: %s", e)

    async def conectar(self) -> bool:
        try:
            self._ws = await websockets.connect(
                self._uri,
                open_timeout=3,
                ping_timeout=5,
            )
            self._conectado = await self._autenticar()
            if self._conectado:
                log.info("VTube Studio conectado")
            return self._conectado
        except Exception as e:
            log.info("VTube no conectado: %s", e)
            self._conectado = False
            return False

    async def _enviar(self, payload: dict) -> None:
        if self._ws and self._conectado:
            await self._ws.send(json.dumps(payload))

    async def _recibir(self, timeout: float = 5.0) -> dict | None:
        try:
            data = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            return json.loads(data)
        except Exception:
            return None

    async def _solicitar_token(self) -> str | None:
        await self._ws.send(
            json.dumps(
                {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "gem_auth_token",
                    "messageType": "AuthenticationTokenRequest",
                    "data": {
                        "pluginName": ajustes.vtube_plugin_name,
                        "pluginDeveloper": ajustes.vtube_plugin_developer,
                        "pluginIcon": None,
                    },
                }
            )
        )
        resp = await self._recibir(timeout=30.0)
        if not resp:
            return None
        return resp.get("data", {}).get("authenticationToken")

    async def _autenticar(self) -> bool:
        try:
            self._token = self._cargar_token()
            if not self._token:
                self._token = await self._solicitar_token()
                if self._token:
                    self._guardar_token(self._token)
                else:
                    return False

            await self._ws.send(
                json.dumps(
                    {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "requestID": "gem_auth",
                        "messageType": "AuthenticationRequest",
                        "data": {
                            "pluginName": ajustes.vtube_plugin_name,
                            "pluginDeveloper": ajustes.vtube_plugin_developer,
                            "authenticationToken": self._token,
                        },
                    }
                )
            )
            resp = await self._recibir()
            autenticado = bool(
                resp and resp.get("data", {}).get("authenticated", False)
            )
            if not autenticado:
                try:
                    self._token_path.unlink(missing_ok=True)
                except Exception:
                    pass
            return autenticado
        except Exception as e:
            log.warning("Error en autenticación VTube: %s", e)
            return False

    async def set_expresion(self, emocion: str) -> None:
        if not self._conectado:
            return
        expresion_id = EXPRESIONES.get(emocion, "Neutral")
        if expresion_id == self._expresion_actual:
            return
        try:
            if self._expresion_actual is not None:
                await self._enviar(
                    {
                        "apiName": "VTubeStudioPublicAPI",
                        "apiVersion": "1.0",
                        "requestID": "gem_expr_off",
                        "messageType": "ExpressionActivationRequest",
                        "data": {
                            "expressionFile": f"{self._expresion_actual}.exp3.json",
                            "active": False,
                        },
                    }
                )
            await self._enviar(
                {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "gem_expr_on",
                    "messageType": "ExpressionActivationRequest",
                    "data": {
                        "expressionFile": f"{expresion_id}.exp3.json",
                        "active": True,
                    },
                }
            )
            self._expresion_actual = expresion_id
        except (ConnectionClosed, WebSocketException):
            self._conectado = False

    async def lip_sync_frame(self, amplitud: float) -> None:
        if not self._conectado:
            return
        valor = float(np.clip(amplitud * 4.0, 0.0, 1.0))
        try:
            await self._enviar(
                {
                    "apiName": "VTubeStudioPublicAPI",
                    "apiVersion": "1.0",
                    "requestID": "gem_lip",
                    "messageType": "InjectParameterDataRequest",
                    "data": {
                        "faceFound": True,
                        "mode": "set",
                        "parameterValues": [
                            {"id": "MouthOpen", "value": valor},
                            {"id": "MouthSmile", "value": valor * 0.3},
                        ],
                    },
                }
            )
        except (ConnectionClosed, WebSocketException):
            self._conectado = False

    async def reproducir_con_lipsync(
        self, audio: np.ndarray, sample_rate: int
    ) -> None:
        """
        Recibe el array float32 mono que ya está sonando por los altavoces
        y envía el RMS por ventanas de 50 ms a VTube para mover la boca.
        Este método NO reproduce audio (eso lo hace ModuloAudio); solo lipsync.
        """
        if not self._conectado or audio is None or audio.size == 0:
            return
        try:
            chunk_size = max(1, sample_rate // 20)  # ventanas de 50 ms
            for i in range(0, len(audio), chunk_size):
                chunk = audio[i : i + chunk_size]
                if len(chunk) == 0:
                    break
                amplitud = float(np.sqrt(np.mean(chunk**2)))
                await self.lip_sync_frame(amplitud)
                await asyncio.sleep(0.05)
            await self.lip_sync_frame(0.0)
        except Exception as e:
            log.debug("lipsync error: %s", e)

    async def desconectar(self) -> None:
        self._conectado = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
