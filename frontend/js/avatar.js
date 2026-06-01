import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
import { Jarvis } from './jarvis.js';
import { BACKEND } from './main.js';

// Voces TTS para cada modo
const VOZ_GEM    = "es-US-Chirp3-HD-Leda";   // femenina
const VOZ_JARVIS = "es-US-Chirp3-HD-Orus";   // masculina

const VRM_PATH = "assets/avatar/AvatarSample_M.vrm";

const FRAMES_PNG = {
  alegre:    ["Happy1.png", "Happy2.png", "Happy3.png"],
  ansioso:   ["Tired1 copy 2.png", "Tired1 copy 3.png", "Tired1 copy 4.png"],
  confundido:["Tired1.png", "Tired1 copy.png", "Tired1 copy 2.png"],
  dormido:   ["Sleepy1.png", "Sleepy2.png", "Sleepy3.png"],
  enojado:   ["Angry1.png", "Angry2.png", "Angry2 copy.png"],
  hablando:  ["Speaking1.png", "Speaking2.png", "Speaking1.png"],
  neutro:    ["Normal1.png", "Normal1 copy.png", "Normal1 copy 2.png"],
  pensativo: ["Thinking1.png", "Thinking2.png", "Thinking3.png"],
  triste:    ["Sad1.png", "Sad2.png", "Sad2 copy.png"],
};

const EMOCION_A_VRM = {
  alegre:"happy", ansioso:"sad", confundido:"sad", dormido:"relaxed",
  enojado:"angry", hablando:"neutral", neutro:"neutral",
  pensativo:"relaxed", triste:"sad",
};

export const EMOJI = {
  alegre:"😊", ansioso:"😰", confundido:"😕", dormido:"😴",
  enojado:"😠", hablando:"🗣️", neutro:"😐", pensativo:"🤔", triste:"😢"
};

// ━━━━━ CATÁLOGO DE GESTOS ━━━━━
// Cada gesto es lista de keyframes: { t: tiempo_seg, poses: { hueso: [x,y,z] } }
// El sistema interpola con easing entre keyframes.
const GESTOS = {
  saludar: {
    duracion: 3.5,
    keys: [
      { t: 0.0, poses: {} },
      { t: 0.6, poses: {
        upperChest: [0.06, 0, 0],
        rightShoulder: [-0.04, 0.01, -0.04],
        rightUpperArm: [0.26, 0.06, -1.04],
        rightLowerArm: [-0.69, 0.16, -1.14],
        rightHand: [0.76, 0.96, 1.31],
      } },
      { t: 3.0, poses: {
        upperChest: [0.06, 0, 0],
        rightShoulder: [-0.04, 0.01, -0.04],
        rightUpperArm: [0.26, 0.06, -1.04],
        rightLowerArm: [-0.69, 0.16, -1.14],
        rightHand: [0.76, 0.96, 1.31],
      } },
      { t: 3.5, poses: {} },
    ],
  },

  saludar_izquierda: {
    duracion: 3.5,
    keys: [
      { t: 0.0, poses: {} },
      { t: 0.6, poses: {
        leftShoulder: [0.41, 0.51, 0.36],
        leftUpperArm: [0.21, 0.51, 0.81],
        rightShoulder: [1.21, -0.19, -0.29],
        rightUpperArm: [-0.39, 0.31, 0.71],
        rightLowerArm: [-1.19, 2.61, 1.66],
        rightHand: [-0.34, 0.01, -0.09],
      } },
      { t: 3.0, poses: {
        leftShoulder: [0.41, 0.51, 0.36],
        leftUpperArm: [0.21, 0.51, 0.81],
        rightShoulder: [1.21, -0.19, -0.29],
        rightUpperArm: [-0.39, 0.31, 0.71],
        rightLowerArm: [-1.19, 2.61, 1.66],
        rightHand: [-0.34, 0.01, -0.09],
      } },
      { t: 3.5, poses: {} },
    ],
  },

  celebrar: {
    duracion: 3.8,
    keys: [
      { t: 0.0, poses: {} },
      { t: 0.5, poses: {
        upperChest: [0.01, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 0.76, 0.46],
        leftLowerArm: [0.91, -0.44, 0.11],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [-2.19, 0.11, -0.09],
        rightUpperArm: [0.81, -0.19, 0.46],
        rightLowerArm: [0.96, -0.34, 0.11],
        rightHand: [0.71, 0.26, 0.41],
      } },
      { t: 3.3, poses: {
        upperChest: [0.01, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 0.76, 0.46],
        leftLowerArm: [0.91, -0.44, 0.11],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [-2.19, 0.11, -0.09],
        rightUpperArm: [0.81, -0.19, 0.46],
        rightLowerArm: [0.96, -0.34, 0.11],
        rightHand: [0.71, 0.26, 0.41],
      } },
      { t: 3.8, poses: {} },
    ],
  },

  facepalm: {
    duracion: 4.5,
    keys: [
      { t: 0.0, poses: {} },
      { t: 0.6, poses: {
        head: [0, 0, -0.29],
        neck: [-0.29, -0.64, 0],
        chest: [0.01, 0, 0],
        upperChest: [-0.09, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 1.26, 0.61],
        leftLowerArm: [0.56, 1.46, -0.19],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [1.11, -0.09, -0.34],
        rightUpperArm: [1.31, 0.06, 1.06],
        rightLowerArm: [0.06, 2.46, 1.96],
        rightHand: [3.11, -0.49, -0.19],
      } },
      { t: 4.0, poses: {
        head: [0, 0, -0.29],
        neck: [-0.29, -0.64, 0],
        chest: [0.01, 0, 0],
        upperChest: [-0.09, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 1.26, 0.61],
        leftLowerArm: [0.56, 1.46, -0.19],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [1.11, -0.09, -0.34],
        rightUpperArm: [1.31, 0.06, 1.06],
        rightLowerArm: [0.06, 2.46, 1.96],
        rightHand: [3.11, -0.49, -0.19],
      } },
      { t: 4.5, poses: {} },
    ],
  },

  pensar: {
    duracion: 5.0,
    keys: [
      { t: 0.0, poses: {} },
      { t: 0.7, poses: {
        upperChest: [-0.09, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 1.26, 0.61],
        leftLowerArm: [0.56, 1.46, -0.19],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [-2.19, 0.11, -0.09],
        rightUpperArm: [1.41, 0.41, 0.51],
        rightLowerArm: [0.96, -0.29, 2.26],
        rightHand: [3.11, -0.49, -0.19],
      } },
      { t: 4.4, poses: {
        upperChest: [-0.09, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 1.26, 0.61],
        leftLowerArm: [0.56, 1.46, -0.19],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [-2.19, 0.11, -0.09],
        rightUpperArm: [1.41, 0.41, 0.51],
        rightLowerArm: [0.96, -0.29, 2.26],
        rightHand: [3.11, -0.49, -0.19],
      } },
      { t: 5.0, poses: {} },
    ],
  },

  absolute_cinema: {
    duracion: 3.5,
    keys: [
      { t: 0.0, poses: {} },
      { t: 0.5, poses: {
        upperChest: [0.06, 0, 0],
        leftShoulder: [0.91, -0.19, -0.34],
        leftUpperArm: [0.26, 0.56, 0.36],
        leftLowerArm: [-0.34, -1.94, -0.14],
        leftHand: [0, 0, -0.04],
        rightShoulder: [0.91, -0.44, -0.24],
        rightUpperArm: [-0.54, 0.91, -0.14],
        rightLowerArm: [-0.29, 0.71, 1.66],
        rightHand: [0.16, 0.01, -0.09],
      } },
      { t: 3.0, poses: {
        upperChest: [0.06, 0, 0],
        leftShoulder: [0.91, -0.19, -0.34],
        leftUpperArm: [0.26, 0.56, 0.36],
        leftLowerArm: [-0.34, -1.94, -0.14],
        leftHand: [0, 0, -0.04],
        rightShoulder: [0.91, -0.44, -0.24],
        rightUpperArm: [-0.54, 0.91, -0.14],
        rightLowerArm: [-0.29, 0.71, 1.66],
        rightHand: [0.16, 0.01, -0.09],
      } },
      { t: 3.5, poses: {} },
    ],
  },

  tapar_ojo: {
    duracion: 3.2,
    keys: [
      { t: 0.0, poses: {} },
      { t: 0.5, poses: {
        upperChest: [-0.09, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 1.26, 0.61],
        leftLowerArm: [0.56, 1.46, -0.19],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [-2.19, 0.11, -0.09],
        rightUpperArm: [0.81, -0.19, 0.46],
        rightLowerArm: [0.96, -0.29, 2.26],
        rightHand: [0.71, 0.26, 0.41],
      } },
      { t: 2.7, poses: {
        upperChest: [-0.09, 0, 0],
        leftShoulder: [0.26, 0.11, -0.09],
        leftUpperArm: [0.81, 1.26, 0.61],
        leftLowerArm: [0.56, 1.46, -0.19],
        leftHand: [0.86, 0, 0.71],
        rightShoulder: [-2.19, 0.11, -0.09],
        rightUpperArm: [0.81, -0.19, 0.46],
        rightLowerArm: [0.96, -0.29, 2.26],
        rightHand: [0.71, 0.26, 0.41],
      } },
      { t: 3.2, poses: {} },
    ],
  },

  asentir: {
    duracion: 2.0,
    keys: [
      { t: 0.0, poses: { head: [0, 0, 0] } },
      { t: 0.35, poses: { head: [0.3, 0, 0] } },
      { t: 0.7, poses: { head: [-0.05, 0, 0] } },
      { t: 1.05, poses: { head: [0.25, 0, 0] } },
      { t: 1.4, poses: { head: [-0.02, 0, 0] } },
      { t: 1.75, poses: { head: [0.2, 0, 0] } },
      { t: 2.0, poses: { head: [0, 0, 0] } },
    ],
  },

  negar: {
    duracion: 2.0,
    keys: [
      { t: 0.0, poses: { head: [0, 0, 0] } },
      { t: 0.3, poses: { head: [0, 0.4, 0] } },
      { t: 0.6, poses: { head: [0, -0.4, 0] } },
      { t: 0.9, poses: { head: [0, 0.4, 0] } },
      { t: 1.2, poses: { head: [0, -0.4, 0] } },
      { t: 1.5, poses: { head: [0, 0.3, 0] } },
      { t: 2.0, poses: { head: [0, 0, 0] } },
    ],
  },

  ladear_cabeza: {
    duracion: 3.0,
    keys: [
      { t: 0.0, poses: { head: [0, 0, 0] } },
      { t: 0.6, poses: { head: [0, 0, 0.3] } },
      { t: 2.4, poses: { head: [0, 0, 0.3] } },
      { t: 3.0, poses: { head: [0, 0, 0] } },
    ],
  },
};

// ━━━━━ Estado global ━━━━━
let _modo = "png";
let _emocionActual = "alegre";
let _ttsActivo = false;
let _modoAvatar = "vrm";  // "vrm" | "jarvis" | "png"

let _imgEl = null;
let _canvasEl = null;
let _frameIdx = 0;
let _timer = null;

let _scene, _camera, _renderer, _vrm, _clock;
let _expresionActualVRM = "neutral";
let _expresionPesoActual = 0;
let _expresionPesoTarget = 1;
let _blinkTimer = 0;
let _blinkActive = false;
let _amplitudActual = 0;
let _amplitudTarget = 0;

let _gestoTiempo = 0;
let _gestoActual = null;
let _gestoTiempoLocal = 0;
let _gestoIntensidad = 1.0;

// Easing cubic in-out (lo que quita el "plasticoso")
function ease(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function init() {
  _imgEl = document.getElementById("avatar");
  iniciarVRM().catch(err => {
    console.warn("VRM no disponible, usando PNG fallback:", err);
    _modo = "png";
    if (_imgEl) _imgEl.style.display = "";
    if (_canvasEl) _canvasEl.style.display = "none";
    mostrarFrame(_emocionActual, 0);
  });
}

async function iniciarVRM() {
  const wrap = document.getElementById("av-wrap");
  if (!wrap) throw new Error("no av-wrap");

  _canvasEl = document.createElement("canvas");
  _canvasEl.id = "avatar3d";
  _canvasEl.style.width  = "175px";
  _canvasEl.style.height = "175px";
  _canvasEl.style.display = "none";
  wrap.appendChild(_canvasEl);

  _renderer = new THREE.WebGLRenderer({
    canvas: _canvasEl, alpha: true, antialias: true,
    premultipliedAlpha: false, powerPreference: "high-performance",
  });
  _renderer.setPixelRatio(Math.min(window.devicePixelRatio * 2, 4));
  _renderer.setSize(460, 460, false);
  _renderer.setClearColor(0x000000, 0);
  _renderer.outputColorSpace = THREE.SRGBColorSpace;
  _renderer.toneMapping = THREE.ACESFilmicToneMapping;
  _renderer.toneMappingExposure = 1.1;

  _scene = new THREE.Scene();
  _camera = new THREE.PerspectiveCamera(30, 1, 0.1, 20);

  const luzAmbiente = new THREE.AmbientLight(0xffffff, 0.7);
  const luzFrontal = new THREE.DirectionalLight(0xffffff, 1.0);
  luzFrontal.position.set(0, 1, 2);
  const luzRelleno = new THREE.DirectionalLight(0xaaccff, 0.4);
  luzRelleno.position.set(-1, 0.5, 1);
  const luzContraluz = new THREE.DirectionalLight(0xffeecc, 0.3);
  luzContraluz.position.set(0, 1, -1);
  _scene.add(luzAmbiente, luzFrontal, luzRelleno, luzContraluz);

  _clock = new THREE.Clock();

  const loader = new GLTFLoader();
  loader.register(parser => new VRMLoaderPlugin(parser));

  const gltf = await loader.loadAsync(VRM_PATH);
  _vrm = gltf.userData.vrm;
  window.__GEM_VRM__ = _vrm;
  try { VRMUtils.removeUnnecessaryVertices(gltf.scene); } catch (_) {}
  try { VRMUtils.combineSkeletons?.(gltf.scene); } catch (_) {}

  _vrm.scene.rotation.y = Math.PI;
  _scene.add(_vrm.scene);

  if (_vrm.humanoid) {
    const head  = _vrm.humanoid.getNormalizedBoneNode("head");
    const chest = _vrm.humanoid.getNormalizedBoneNode("chest")
               || _vrm.humanoid.getNormalizedBoneNode("upperChest")
               || _vrm.humanoid.getNormalizedBoneNode("spine");
    if (head) {
      const headPos  = new THREE.Vector3();
      const chestPos = new THREE.Vector3();
      head.getWorldPosition(headPos);
      (chest || head).getWorldPosition(chestPos);
      const targetY = (headPos.y + chestPos.y) / 2;
      _camera.position.set(headPos.x, targetY, headPos.z + 1.6);
      _camera.lookAt(headPos.x, targetY, headPos.z);
    }
  }

  _modo = "vrm";
  if (_imgEl) _imgEl.style.display = "none";
  _canvasEl.style.display = "";

  loop();
  console.log("Avatar VRM cargado");
}

function loop() {
  if (_modo !== "vrm" || !_vrm) return;
  requestAnimationFrame(loop);
  const dt = _clock.getDelta();
  actualizarExpresiones(dt);
  if (!window.__GEM_CALIBRANDO__) {
    aplicarMovimientos(dt);
  }
  _vrm.update(dt);
  _renderer.render(_scene, _camera);
}

function actualizarExpresiones(dt) {
  const em = _vrm.expressionManager;
  if (!em) return;

  for (const nombre of ["happy", "angry", "sad", "relaxed", "neutral"]) {
    em.setValue(nombre, 0);
  }
  _expresionPesoActual += (_expresionPesoTarget - _expresionPesoActual) * Math.min(dt * 8, 1);
  const peso = Math.min(_expresionPesoActual, 1.5);
  em.setValue(_expresionActualVRM, peso);

  _amplitudActual += (_amplitudTarget - _amplitudActual) * Math.min(dt * 12, 1);
  em.setValue("aa", _amplitudActual);

  _blinkTimer -= dt;
  if (_blinkTimer <= 0 && !_blinkActive) {
    _blinkActive = true;
    _blinkTimer = 0.15;
    em.setValue("blink", 1);
  } else if (_blinkActive && _blinkTimer <= 0) {
    _blinkActive = false;
    _blinkTimer = 2.5 + Math.random() * 3.5;
    em.setValue("blink", 0);
  } else if (_blinkActive) {
    em.setValue("blink", 1);
  }
}

// ━━━━━ Movimiento corporal: idle + gesto activo ━━━━━
function aplicarMovimientos(dt) {
  if (!_vrm.humanoid) return;
  _gestoTiempo += dt;

  const get = (n) => _vrm.humanoid.getNormalizedBoneNode(n);
  const head     = get("head");
  const chest    = get("chest") || get("upperChest");
  const spine    = get("spine");
  const brazoIzq = get("leftUpperArm");
  const brazoDer = get("rightUpperArm");
  const antIzq   = get("leftLowerArm");
  const antDer   = get("rightLowerArm");

  // ── 1) Pose base + idle (siempre activo) ──
  const respiracion = Math.sin(_gestoTiempo * 1.2) * 0.012;
  const sway        = Math.sin(_gestoTiempo * 0.4) * 0.015;
  const microIzq    = Math.sin(_gestoTiempo * 0.5) * 0.015;
  const microDer    = Math.sin(_gestoTiempo * 0.5 + 0.7) * 0.015;

  const shoulderIzq = get("leftShoulder");
  const shoulderDer = get("rightShoulder");
  const manoIzq     = get("leftHand");
  const manoDer     = get("rightHand");

  if (head)     head.rotation.set(
    Math.sin(_gestoTiempo * 0.4) * 0.015,
    Math.sin(_gestoTiempo * 0.6) * 0.01,
    0,
  );
  if (spine)    spine.rotation.set(respiracion * 0.5, 0, sway);
  if (chest)    chest.rotation.set(respiracion, 0, 0);

  if (shoulderIzq) shoulderIzq.rotation.set(0.41, 0.51, 0.36);
  if (brazoIzq)    brazoIzq.rotation.set(0.21, 0.51, 0.81 + microIzq);
  if (antIzq)      antIzq.rotation.set(0, 0, 0);
  if (manoIzq)     manoIzq.rotation.set(0, 0, 0);

  if (shoulderDer) shoulderDer.rotation.set(-1.94, 0.76, -0.29);
  if (brazoDer)    brazoDer.rotation.set(-0.39, 0.31, 0.71 + microDer);
  if (antDer)      antDer.rotation.set(-1.19, 2.61, 1.66);
  if (manoDer)     manoDer.rotation.set(-0.34, 0.01, -0.09);

  // ── 2) Capa de habla (encima del idle, si hay TTS) ──
  if (_ttsActivo) {
    const f = Math.min(_amplitudActual * 2, 1);
    if (brazoIzq) brazoIzq.rotation.z += Math.sin(_gestoTiempo * 3.5) * 0.08 * f;
    if (brazoDer) brazoDer.rotation.z += Math.sin(_gestoTiempo * 3.5 + 1.5) * 0.08 * f;
    if (head)     head.rotation.y    += Math.sin(_gestoTiempo * 2.5) * 0.05 * f;
  }

  // ── 3) Capa de gesto activo (encima de todo, con easing) ──
  if (_gestoActual) {
    _gestoTiempoLocal += dt;
    const gesto = GESTOS[_gestoActual];
    if (!gesto) { _gestoActual = null; return; }

    if (_gestoTiempoLocal >= gesto.duracion) {
      _gestoActual = null;
      _gestoTiempoLocal = 0;
      return;
    }

    // Encontrar keyframes alrededor del tiempo actual
    let kA = gesto.keys[0], kB = gesto.keys[0];
    for (let i = 0; i < gesto.keys.length - 1; i++) {
      if (gesto.keys[i].t <= _gestoTiempoLocal && gesto.keys[i+1].t >= _gestoTiempoLocal) {
        kA = gesto.keys[i];
        kB = gesto.keys[i+1];
        break;
      }
    }

    const span = Math.max(kB.t - kA.t, 0.001);
    const tNorm = (_gestoTiempoLocal - kA.t) / span;
    const t = ease(Math.max(0, Math.min(1, tNorm)));

    // Fade in/out del gesto (entra rápido, mantiene, sale suave)
    let intensidad = _gestoIntensidad;
    if (_gestoTiempoLocal < 0.15) {
      intensidad *= _gestoTiempoLocal / 0.15;
    } else if (_gestoTiempoLocal > gesto.duracion - 0.25) {
      intensidad *= (gesto.duracion - _gestoTiempoLocal) / 0.25;
    }

    const huesos = new Set([
      ...Object.keys(kA.poses || {}),
      ...Object.keys(kB.poses || {}),
    ]);
    for (const nombreHueso of huesos) {
      const a = (kA.poses && kA.poses[nombreHueso]) || [0,0,0];
      const b = (kB.poses && kB.poses[nombreHueso]) || a;
      const x = a[0] + (b[0] - a[0]) * t;
      const y = a[1] + (b[1] - a[1]) * t;
      const z = a[2] + (b[2] - a[2]) * t;
      const hueso = get(nombreHueso);
      if (hueso) {
        // Mezcla entre pose neutra actual y pose del gesto, con la intensidad
        hueso.rotation.x = hueso.rotation.x * (1 - intensidad) + x * intensidad;
        hueso.rotation.y = hueso.rotation.y * (1 - intensidad) + y * intensidad;
        hueso.rotation.z = hueso.rotation.z * (1 - intensidad) + z * intensidad;
      }
    }
  }
}

// ━━━━━ API pública para gestos ━━━━━
function ejecutarGesto(nombre, intensidad = 1.0) {
  if (!GESTOS[nombre]) {
    console.warn("Gesto desconocido:", nombre);
    return false;
  }
  _gestoActual = nombre;
  _gestoTiempoLocal = 0;
  _gestoIntensidad = Math.max(0, Math.min(1.5, intensidad));
  return true;
}

function gestosDisponibles() {
  return Object.keys(GESTOS);
}

// ━━━━━ Resto (PNG fallback, emoción, habla) ━━━━━
function mostrarFrame(emo, idx) {
  if (_modo !== "png" || !_imgEl) return;
  const lista = FRAMES_PNG[emo] || FRAMES_PNG.neutro;
  _imgEl.src = `assets/avatar/${emo}/${encodeURIComponent(lista[idx % lista.length])}`;
}

function cambiarEmocion(nuevaEmo) {
  _emocionActual = nuevaEmo;
  if (_modoAvatar === "jarvis") {
    Jarvis.cambiarEmocion(nuevaEmo);
    return;
  }
  if (_modo === "vrm") {
    const nuevaVRM = EMOCION_A_VRM[nuevaEmo] || "neutral";
    if (nuevaVRM !== _expresionActualVRM) {
      _expresionActualVRM = nuevaVRM;
      _expresionPesoActual = 0;
      _expresionPesoTarget = nuevaVRM === "neutral" ? 0.4 : 1.2;
    }
  } else if (!_ttsActivo) {
    if (FRAMES_PNG[nuevaEmo]) mostrarFrame(nuevaEmo, 0);
  }
}

function iniciarHabla() {
  if (_ttsActivo) return;
  _ttsActivo = true;
  if (_modoAvatar === "jarvis") {
    Jarvis.iniciarHabla();
    return;
  }
  if (_modo === "vrm") _amplitudTarget = 0.5;
  else {
    document.getElementById("avatar")?.classList.add("talk");
    _frameIdx = 0;
    _timer = setInterval(() => {
      _frameIdx = (_frameIdx + 1) % 3;
      mostrarFrame(_emocionActual, _frameIdx);
    }, 110);
  }
}

function actualizarAmplitudHabla(rms) {
  if (_modoAvatar === "jarvis") {
    Jarvis.setAmplitud(rms);
    return;
  }
  if (_modo === "vrm" && _ttsActivo) {
    _amplitudTarget = Math.min(1, Math.max(0, rms * 8));
  }
}
function detenerHabla() {
  _ttsActivo = false;
  if (_modoAvatar === "jarvis") {
    Jarvis.detenerHabla();
    return;
  }
  if (_modo === "vrm") _amplitudTarget = 0;
  else {
    document.getElementById("avatar")?.classList.remove("talk");
    if (_timer) { clearInterval(_timer); _timer = null; }
    mostrarFrame(_emocionActual, 0);
  }
}
async function _cambiarVozBackend(voz) {
  try {
    await fetch(`${BACKEND}/voz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ voz }),
    });
  } catch (_) { /* silencioso */ }
}

function toggleModo() {
  const wrap = document.getElementById("av-wrap");
  // Transición suave
  wrap.classList.add("switching");
  setTimeout(() => wrap.classList.remove("switching"), 600);

  if (_modoAvatar === "vrm" || _modoAvatar === "png") {
    // Cambiar a Jarvis
    _modoAvatar = "jarvis";
    if (_imgEl) _imgEl.style.display = "none";
    if (_canvasEl) _canvasEl.style.display = "none";
    if (!Jarvis.estaActivo()) {
      Jarvis.init(wrap);
    }
    Jarvis.activar();
    Jarvis.cambiarEmocion(_emocionActual);
    document.getElementById("btn-modo-avatar")?.setAttribute("title", "Cambiar a GEM");
    document.getElementById("btn-modo-avatar").textContent = "🔮";
    // Cambiar a voz masculina
    _cambiarVozBackend(VOZ_JARVIS);
    document.getElementById("msg").textContent = "Modo Jarvis activado 🔮";
  } else {
    // Cambiar a VRM (o PNG si no hay VRM)
    Jarvis.desactivar();
    if (_modo === "vrm" && _canvasEl) {
      _modoAvatar = "vrm";
      _canvasEl.style.display = "";
    } else if (_imgEl) {
      _modoAvatar = "png";
      _imgEl.style.display = "";
      mostrarFrame(_emocionActual, 0);
    }
    document.getElementById("btn-modo-avatar")?.setAttribute("title", "Cambiar a Jarvis");
    document.getElementById("btn-modo-avatar").textContent = "👤";
    // Restaurar voz femenina
    _cambiarVozBackend(VOZ_GEM);
    document.getElementById("msg").textContent = "Modo GEM activado 👤";
  }
}

function getModoAvatar() {
  return _modoAvatar;
}
export const Avatar = {
  init, mostrarFrame, cambiarEmocion,
  iniciarHabla, detenerHabla, actualizarAmplitudHabla,
  ejecutarGesto, gestosDisponibles,
  toggleModo, getModoAvatar,
  emojiDe: (emo) => EMOJI[emo] || "😐",
  FRAMES: FRAMES_PNG, EMOJI,
};