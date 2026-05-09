import threading
import time
import urllib.request
import logging
from pathlib import Path
import numpy as np
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision
from backend.config import ajustes

log = logging.getLogger("gem.vision")

MEDIAPIPE_MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/"
    "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)

UMBRALES_EMOCIONES = {
    "alegre": {"mouthSmileLeft": 0.4, "mouthSmileRight": 0.4},
    "estresado": {"browDownLeft": 0.35, "browDownRight": 0.35},
    "confundido": {"browInnerUp": 0.4, "mouthPucker": 0.2},
    "sorprendido": {"jawOpen": 0.5, "eyeWideLeft": 0.4},
}


class ModuloVision:
    def __init__(self):
        self._activo = False
        self._hilo: threading.Thread | None = None
        self._landmarker: mp_vision.FaceLandmarker | None = None
        self._identidad_vec: np.ndarray | None = None
        self._estado: dict = {
            "emocion": "neutro",
            "es_usuario": False,
            "boca_abierta": 0.0,
            "identidad_activa": False,
        }
        self._lock = threading.Lock()

    def _descargar_modelo(self) -> None:
        path = Path(ajustes.mediapipe_model_path)
        if not path.exists():
            log.info("Descargando modelo de MediaPipe...")
            path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MEDIAPIPE_MODEL_URL, path)
            log.info("Modelo descargado en %s", path)

    def iniciar(self) -> None:
        self._descargar_modelo()
        opciones = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=ajustes.mediapipe_model_path
            ),
            output_face_blendshapes=True,
            num_faces=1,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(opciones)
        self._activo = True
        self._hilo = threading.Thread(target=self._loop_camara, daemon=True)
        self._hilo.start()

    def detener(self) -> None:
        self._activo = False
        if self._hilo:
            self._hilo.join(timeout=2.0)

    def _landmarks_a_vector(self, landmarks: list) -> np.ndarray:
        coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks]).flatten()
        norma = np.linalg.norm(coords)
        return coords / norma if norma > 0 else coords

    def registrar_identidad(self, landmarks: list) -> None:
        vec = self._landmarks_a_vector(landmarks)
        with self._lock:
            self._identidad_vec = vec
            self._estado["identidad_activa"] = True

    def _similitud_identidad(self, landmarks: list) -> float:
        if self._identidad_vec is None:
            return 1.0
        vec = self._landmarks_a_vector(landmarks)
        return float(np.dot(self._identidad_vec, vec))

    def _detectar_emocion(self, bs: dict[str, float]) -> str:
        for emocion, reqs in UMBRALES_EMOCIONES.items():
            if all(bs.get(k, 0.0) >= v for k, v in reqs.items()):
                return emocion
        return "neutro"

    def _procesar_resultado(self, resultado: mp_vision.FaceLandmarkerResult) -> None:
        if not resultado.face_landmarks or not resultado.face_blendshapes:
            with self._lock:
                self._estado["es_usuario"] = False
            return
        landmarks = resultado.face_landmarks[0]
        blendshapes = {
            bs.category_name: bs.score for bs in resultado.face_blendshapes[0]
        }
        similitud = self._similitud_identidad(landmarks)
        emocion = self._detectar_emocion(blendshapes)
        boca = blendshapes.get("jawOpen", 0.0)
        with self._lock:
            self._estado = {
                "emocion": emocion,
                "es_usuario": similitud >= ajustes.identidad_umbral,
                "boca_abierta": boca,
                "identidad_activa": self._identidad_vec is not None,
            }

    def _loop_camara(self) -> None:
        camara = cv2.VideoCapture(0)
        if not camara.isOpened():
            log.error("No se pudo abrir la cámara. Visión deshabilitada.")
            return

        intervalo = 1.0 / max(1, ajustes.vision_fps)
        try:
            while self._activo:
                t_inicio = time.time()
                ret, frame = camara.read()
                if not ret or self._landmarker is None:
                    time.sleep(0.1)
                    continue
                try:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                    resultado = self._landmarker.detect(imagen)
                    self._procesar_resultado(resultado)
                except Exception as e:
                    log.debug("Frame error: %s", e)

                # Throttle a vision_fps para no saturar CPU
                tiempo_restante = intervalo - (time.time() - t_inicio)
                if tiempo_restante > 0:
                    time.sleep(tiempo_restante)
        finally:
            camara.release()

    def get_estado(self) -> dict:
        with self._lock:
            return self._estado.copy()

    def registrar_desde_camara(self) -> bool:
        if self._landmarker is None:
            log.warning("Landmarker no iniciado")
            return False
        camara = cv2.VideoCapture(0)
        if not camara.isOpened():
            log.warning("No se pudo abrir cámara para registro")
            return False
        exito = False
        try:
            for _ in range(30):
                ret, frame = camara.read()
                if not ret:
                    continue
                try:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                    resultado = self._landmarker.detect(imagen)
                    if resultado.face_landmarks:
                        self.registrar_identidad(resultado.face_landmarks[0])
                        exito = True
                        break
                except Exception:
                    continue
        finally:
            camara.release()
        return exito
