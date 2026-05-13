"""
Módulo de Visión de GEM.

Mejoras:
  · Identidad robusta: promedia N muestras durante T segundos
  · Frame anotado con overlays (rostro, identidad, emoción)
  · Snapshot JPEG bajo demanda + stream MJPEG
"""

import logging
import threading
import time
import urllib.request
from pathlib import Path
from typing import Generator

import cv2
import mediapipe as mp
import numpy as np
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
    "ansioso": {"browInnerUp": 0.5, "mouthStretchLeft": 0.2, "mouthStretchRight": 0.2},
    "confundido": {"browInnerUp": 0.4, "mouthPucker": 0.2},
    "dormido": {"eyeBlinkLeft": 0.8, "eyeBlinkRight": 0.8},
    "enojado": {"browDownLeft": 0.5, "browDownRight": 0.5, "mouthFrownLeft": 0.3},
    "triste": {"browInnerUp": 0.4, "mouthFrownLeft": 0.3, "mouthFrownRight": 0.3},
    "pensativo": {"eyeLookUpLeft": 0.5, "eyeLookUpRight": 0.5},
}

MUESTRAS_OBJETIVO = 10


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
            "rostro_detectado": False,
            "similitud": 0.0,
        }
        self._lock = threading.Lock()

        self._frame_actual: np.ndarray | None = None
        self._frame_anotado: np.ndarray | None = None
        self._frame_lock = threading.Lock()

        self._capturando_identidad = False
        self._muestras_identidad: list[np.ndarray] = []

        self.on_estado_actualizado = None

    def _descargar_modelo(self) -> None:
        path = Path(ajustes.mediapipe_model_path)
        if not path.exists():
            log.info("Descargando modelo MediaPipe...")
            path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(MEDIAPIPE_MODEL_URL, path)

    def iniciar(self) -> None:
        self._descargar_modelo()
        opciones = mp_vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(
                model_asset_path=ajustes.mediapipe_model_path
            ),
            output_face_blendshapes=True,
            num_faces=2,
            running_mode=mp_vision.RunningMode.IMAGE,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(opciones)
        self._activo = True
        self._hilo = threading.Thread(target=self._loop_camara, daemon=True)
        self._hilo.start()
        log.info("Módulo de visión iniciado")

    def detener(self) -> None:
        self._activo = False
        if self._hilo:
            self._hilo.join(timeout=2.0)

    def _landmarks_a_vector(self, landmarks: list) -> np.ndarray:
        coords = np.array([[lm.x, lm.y, lm.z] for lm in landmarks]).flatten()
        norma = np.linalg.norm(coords)
        return coords / norma if norma > 0 else coords

    def _similitud_identidad(self, landmarks: list) -> float:
        if self._identidad_vec is None:
            return 1.0
        return float(np.dot(self._identidad_vec, self._landmarks_a_vector(landmarks)))

    def _detectar_emocion(self, bs: dict[str, float]) -> str:
        for emocion, reqs in UMBRALES_EMOCIONES.items():
            if all(bs.get(k, 0.0) >= v for k, v in reqs.items()):
                return emocion
        return "neutro"

    def _dibujar_overlays(
        self,
        frame: np.ndarray,
        landmarks_list: list,
        estado: dict,
        capturando: bool,
        progreso: int,
        objetivo: int,
    ) -> np.ndarray:
        anotado = frame.copy()
        h, w = anotado.shape[:2]

        es_usuario = estado.get("es_usuario", False)
        id_activa = estado.get("identidad_activa", False)

        if not id_activa:
            color = (255, 200, 0)
        elif es_usuario:
            color = (0, 255, 100)
        else:
            color = (0, 80, 255)

        for landmarks in landmarks_list or []:
            xs = [lm.x for lm in landmarks]
            ys = [lm.y for lm in landmarks]
            x1, y1 = int(min(xs) * w), int(min(ys) * h)
            x2, y2 = int(max(xs) * w), int(max(ys) * h)
            cv2.rectangle(anotado, (x1, y1), (x2, y2), color, 2)
            for lm in landmarks[::15]:
                cv2.circle(anotado, (int(lm.x * w), int(lm.y * h)), 1, color, -1)

        sim = estado.get("similitud", 0.0)
        emo = estado.get("emocion", "neutro")
        n = estado.get("num_caras", 0)

        if not id_activa:
            etiqueta_id = "SIN REGISTRO"
        elif es_usuario:
            etiqueta_id = f"USUARIO ({sim:.2f})"
        else:
            etiqueta_id = f"DESCONOCIDO ({sim:.2f})"

        textos = [
            ("ID:  " + etiqueta_id, color),
            ("Emo: " + emo, (255, 255, 255)),
            ("Caras: " + str(n), (255, 255, 255)),
        ]
        y0 = 24
        for txt, c in textos:
            cv2.putText(
                anotado, txt, (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3
            )
            cv2.putText(anotado, txt, (10, y0), cv2.FONT_HERSHEY_SIMPLEX, 0.55, c, 1)
            y0 += 22

        if capturando:
            barra_w = int((w - 40) * (progreso / max(objetivo, 1)))
            cv2.rectangle(anotado, (20, h - 40), (w - 20, h - 20), (60, 60, 60), -1)
            cv2.rectangle(
                anotado, (20, h - 40), (20 + barra_w, h - 20), (0, 220, 255), -1
            )
            cv2.putText(
                anotado,
                f"Registrando rostro {progreso}/{objetivo}",
                (20, h - 50),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 220, 255),
                2,
            )

        return anotado

    def _procesar_resultado(
        self, resultado: mp_vision.FaceLandmarkerResult, frame_bgr: np.ndarray
    ) -> None:
        num_caras = len(resultado.face_landmarks) if resultado.face_landmarks else 0

        if num_caras == 0:
            with self._lock:
                self._estado.update(
                    {
                        "rostro_detectado": False,
                        "es_usuario": False,
                        "emocion": "neutro",
                        "boca_abierta": 0.0,
                        "personas_extra": False,
                        "similitud": 0.0,
                        "num_caras": 0,
                    }
                )
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
                "rostro_detectado": True,
                "personas_extra": num_caras > 1,
                "num_caras": num_caras,
                "similitud": round(similitud, 3),
            }

        if self._capturando_identidad:
            self._muestras_identidad.append(self._landmarks_a_vector(landmarks))

        cb = self.on_estado_actualizado
        if cb:
            try:
                cb(self._estado.copy(), frame_bgr)
            except Exception:
                pass

    def _loop_camara(self) -> None:
        camara = cv2.VideoCapture(0)
        if not camara.isOpened():
            log.error("No se pudo abrir la cámara")
            return

        intervalo = 1.0 / max(1, ajustes.vision_fps)
        try:
            while self._activo:
                t0 = time.time()
                ret, frame = camara.read()
                if not ret or self._landmarker is None:
                    time.sleep(0.1)
                    continue

                ultimos_landmarks_list = []
                try:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    imagen = mp.Image(image_format=mp.ImageFormat.SRGB, data=frame_rgb)
                    resultado = self._landmarker.detect(imagen)
                    self._procesar_resultado(resultado, frame)
                    ultimos_landmarks_list = resultado.face_landmarks or []
                except Exception as e:
                    log.debug("Frame error: %s", e)

                with self._lock:
                    estado_copia = self._estado.copy()
                capturando = self._capturando_identidad
                progreso = len(self._muestras_identidad)

                anotado = self._dibujar_overlays(
                    frame,
                    ultimos_landmarks_list,
                    estado_copia,
                    capturando,
                    progreso,
                    MUESTRAS_OBJETIVO,
                )

                with self._frame_lock:
                    self._frame_actual = frame.copy()
                    self._frame_anotado = anotado

                restante = intervalo - (time.time() - t0)
                if restante > 0:
                    time.sleep(restante)
        finally:
            camara.release()

    def get_estado(self) -> dict:
        with self._lock:
            return self._estado.copy()

    def get_frame_actual(self) -> np.ndarray | None:
        with self._frame_lock:
            return self._frame_actual.copy() if self._frame_actual is not None else None

    def get_snapshot_jpeg(
        self, anotado: bool = True, quality: int = 75
    ) -> bytes | None:
        with self._frame_lock:
            frame = self._frame_anotado if anotado else self._frame_actual
            if frame is None:
                return None
            frame = frame.copy()
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return bytes(buf) if ok else None

    def stream_mjpeg(
        self, fps: int = 8, anotado: bool = True
    ) -> Generator[bytes, None, None]:
        intervalo = 1.0 / max(1, fps)
        while self._activo:
            jpeg = self.get_snapshot_jpeg(anotado=anotado, quality=70)
            if jpeg is None:
                time.sleep(0.1)
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                b"Content-Length: "
                + str(len(jpeg)).encode()
                + b"\r\n\r\n"
                + jpeg
                + b"\r\n"
            )
            time.sleep(intervalo)

    def registrar_desde_camara(
        self,
        muestras_objetivo: int = 10,
        timeout_s: float = 8.0,
    ) -> dict:
        global MUESTRAS_OBJETIVO
        MUESTRAS_OBJETIVO = muestras_objetivo

        if self._landmarker is None or not self._activo:
            return {"exito": False, "mensaje": "El módulo de visión no está activo."}

        self._muestras_identidad = []
        self._capturando_identidad = True

        try:
            t0 = time.time()
            while time.time() - t0 < timeout_s:
                if len(self._muestras_identidad) >= muestras_objetivo:
                    break
                time.sleep(0.1)
        finally:
            self._capturando_identidad = False

        n = len(self._muestras_identidad)
        if n < 3:
            return {
                "exito": False,
                "mensaje": f"Solo capturé {n} muestras (necesito al menos 3). "
                "Asegúrate de estar bien iluminado y frente a la cámara.",
                "muestras": n,
            }

        promedio = np.mean(self._muestras_identidad, axis=0)
        norma = np.linalg.norm(promedio)
        if norma > 0:
            promedio = promedio / norma

        similitudes_inter = [
            float(np.dot(promedio, m / max(np.linalg.norm(m), 1e-9)))
            for m in self._muestras_identidad
        ]
        consistencia = float(np.mean(similitudes_inter))

        with self._lock:
            self._identidad_vec = promedio
            self._estado["identidad_activa"] = True

        log.info(
            "Identidad registrada con %d muestras (consistencia=%.3f)", n, consistencia
        )
        return {
            "exito": True,
            "muestras": n,
            "consistencia": round(consistencia, 3),
            "mensaje": f"Rostro registrado con {n} muestras "
            f"(consistencia {consistencia:.2f}).",
        }

    def borrar_identidad(self) -> None:
        with self._lock:
            self._identidad_vec = None
            self._estado["identidad_activa"] = False
