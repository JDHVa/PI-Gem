// Avatar 3D con VRM (three-vrm). Fallback automático a PNG si falla.
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { VRMLoaderPlugin, VRMUtils } from "@pixiv/three-vrm";
const VRM_PATH = "assets/avatar/AvatarSample_M.vrm";

const FRAMES_PNG = {
  alegre:    ["Happy1.png",        "Happy2.png",        "Happy3.png"],
  ansioso:   ["Tired1 copy 2.png", "Tired1 copy 3.png", "Tired1 copy 4.png"],
  confundido:["Tired1.png",        "Tired1 copy.png",   "Tired1 copy 2.png"],
  dormido:   ["Sleepy1.png",       "Sleepy2.png",       "Sleepy3.png"],
  enojado:   ["Angry1.png",        "Angry2.png",        "Angry2 copy.png"],
  hablando:  ["Speaking1.png",     "Speaking2.png",     "Speaking1.png"],
  neutro:    ["Normal1.png",       "Normal1 copy.png",  "Normal1 copy 2.png"],
  pensativo: ["Thinking1.png",     "Thinking2.png",     "Thinking3.png"],
  triste:    ["Sad1.png",          "Sad2.png",          "Sad2 copy.png"],
};

const EMOCION_A_VRM = {
  alegre:    "happy",
  ansioso:   "sad",
  confundido:"sad",
  dormido:   "relaxed",
  enojado:   "angry",
  hablando:  "neutral",
  neutro:    "neutral",
  pensativo: "relaxed",
  triste:    "sad",
};

export const EMOJI = {
  alegre:"😊", ansioso:"😰", confundido:"😕", dormido:"😴",
  enojado:"😠", hablando:"🗣️", neutro:"😐", pensativo:"🤔", triste:"😢"
};

let _modo = "png";
let _emocionActual = "alegre";
let _ttsActivo = false;

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
    canvas: _canvasEl,
    alpha: true,
    antialias: true,
    premultipliedAlpha: false,
    powerPreference: "high-performance",
  });
  _renderer.setPixelRatio(Math.min(window.devicePixelRatio * 2, 4));
  _renderer.setSize(460, 460, false);
  _renderer.setClearColor(0x000000, 0);
  _renderer.outputColorSpace = THREE.SRGBColorSpace;
  _renderer.toneMapping = THREE.ACESFilmicToneMapping;
  _renderer.toneMappingExposure = 1.1;

  _scene = new THREE.Scene();
  _camera = new THREE.PerspectiveCamera(30, 1, 0.1, 20);
  _camera.position.set(0, 1.35, 0.7);

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
  try { VRMUtils.removeUnnecessaryVertices(gltf.scene); } catch (_) {}
  try { VRMUtils.combineSkeletons?.(gltf.scene); } catch (_) {}

  _vrm.scene.rotation.y = Math.PI;
  _scene.add(_vrm.scene);
  aplicarPoseRelajada(_vrm);


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
  _vrm.update(dt);
  _renderer.render(_scene, _camera);
}

function actualizarExpresiones(dt) {
  const em = _vrm.expressionManager;
  if (!em) return;

  for (const nombre of ["happy", "angry", "sad", "relaxed", "neutral"]) {
    em.setValue(nombre, 0);
  }
  _expresionPesoActual += (_expresionPesoTarget - _expresionPesoActual) * Math.min(dt * 4, 1);
  em.setValue(_expresionActualVRM, _expresionPesoActual);

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

function mostrarFrame(emo, idx) {
  if (_modo !== "png" || !_imgEl) return;
  const lista = FRAMES_PNG[emo] || FRAMES_PNG.neutro;
  _imgEl.src = `assets/avatar/${emo}/${encodeURIComponent(lista[idx % lista.length])}`;
}

function cambiarEmocion(nuevaEmo) {
  _emocionActual = nuevaEmo;
  if (_modo === "vrm") {
    const nuevaVRM = EMOCION_A_VRM[nuevaEmo] || "neutral";
    if (nuevaVRM !== _expresionActualVRM) {
      _expresionActualVRM = nuevaVRM;
      _expresionPesoActual = 0;
      _expresionPesoTarget = nuevaVRM === "neutral" ? 0.3 : 0.9;
    }
  } else if (!_ttsActivo) {
    if (FRAMES_PNG[nuevaEmo]) mostrarFrame(nuevaEmo, 0);
  }
}

function iniciarHabla() {
  if (_ttsActivo) return;
  _ttsActivo = true;

  if (_modo === "vrm") {
    _amplitudTarget = 0.5;
  } else {
    document.getElementById("avatar")?.classList.add("talk");
    _frameIdx = 0;
    _timer = setInterval(() => {
      _frameIdx = (_frameIdx + 1) % 3;
      mostrarFrame(_emocionActual, _frameIdx);
    }, 110);
  }
}

function actualizarAmplitudHabla(rms) {
  if (_modo === "vrm" && _ttsActivo) {
    _amplitudTarget = Math.min(1, Math.max(0, rms * 8));
  }
}

function detenerHabla() {
  _ttsActivo = false;
  if (_modo === "vrm") {
    _amplitudTarget = 0;
  } else {
    document.getElementById("avatar")?.classList.remove("talk");
    if (_timer) { clearInterval(_timer); _timer = null; }
    mostrarFrame(_emocionActual, 0);
  }
}
function aplicarPoseRelajada(vrm) {
  if (!vrm.humanoid) return;
  const get = (n) => vrm.humanoid.getNormalizedBoneNode(n);

  const rotaciones = {
    leftUpperArm:  [0, 0, 1.2],
    rightUpperArm: [0, 0, -1.2],
    leftLowerArm:  [0, -0.2, 0.15],
    rightLowerArm: [0, 0.2, -0.15],
    leftHand:      [0, 0, 0.1],
    rightHand:     [0, 0, -0.1],
    leftShoulder:  [0, 0, 0.15],
    rightShoulder: [0, 0, -0.15],
  };

  for (const [hueso, [x, y, z]] of Object.entries(rotaciones)) {
    const b = get(hueso);
    if (b) b.rotation.set(x, y, z);
  }
}
export const Avatar = {
  init, mostrarFrame, cambiarEmocion,
  iniciarHabla, detenerHabla, actualizarAmplitudHabla,
  emojiDe: (emo) => EMOJI[emo] || "😐",
  FRAMES: FRAMES_PNG, EMOJI,
};