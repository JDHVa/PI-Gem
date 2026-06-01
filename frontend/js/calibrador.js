// Calibrador visual de poses VRM.
// Abre con: window.GEM.calibrador.abrir()

const HUESOS_PRINCIPALES = [
  "head", "neck",
  "spine", "chest", "upperChest",
  "leftShoulder", "leftUpperArm", "leftLowerArm", "leftHand",
  "rightShoulder", "rightUpperArm", "rightLowerArm", "rightHand",
];

const EJES = ["x", "y", "z"];
const RANGO = 3.14;

let _abierto = false;
let _panel = null;
let _vrm = null;
let _valores = {};
let _aplicarLoop = null;

function setVRM(vrm) {
  _vrm = vrm;
}
function abrir() {
  window.__GEM_CALIBRANDO__ = true;

  if (_abierto) return;
  if (!_vrm) {
    alert("VRM no cargado todavía. Espera unos segundos.");
    return;
  }
  _abierto = true;

  _panel = document.createElement("div");
  _panel.id = "calibrador-panel";
  _panel.innerHTML = `
    <div class="cal-header">
      <span>🎛 Calibrador de poses</span>
      <button id="cal-reset">↻ Reset</button>
      <button id="cal-export">📋 Exportar</button>
      <button id="cal-cerrar">✕</button>
    </div>
    <div class="cal-body" id="cal-body"></div>
    <pre id="cal-output"></pre>
  `;
  document.body.appendChild(_panel);

  const body = _panel.querySelector("#cal-body");
  const huesosDisponibles = [];
  const huesosFaltantes = [];

  for (const hueso of HUESOS_PRINCIPALES) {
    const existe = !!_vrm.humanoid?.getNormalizedBoneNode(hueso);
    if (!existe) {
      huesosFaltantes.push(hueso);
      continue;
    }
    huesosDisponibles.push(hueso);
    _valores[hueso] = { x: 0, y: 0, z: 0 };
    const grupo = document.createElement("div");
    grupo.className = "cal-grupo";
    grupo.innerHTML = `<div class="cal-hueso">${hueso}</div>`;
    for (const eje of EJES) {
      const fila = document.createElement("div");
      fila.className = "cal-fila";
      fila.innerHTML = `
        <span class="cal-eje">${eje}</span>
        <input type="range" min="${-RANGO}" max="${RANGO}" step="0.05" value="0"
               data-hueso="${hueso}" data-eje="${eje}">
        <span class="cal-val" data-val="${hueso}-${eje}">0.00</span>
      `;
      grupo.appendChild(fila);
    }
    body.appendChild(grupo);
  }

  console.log("Huesos disponibles:", huesosDisponibles);
  if (huesosFaltantes.length) {
    console.warn("Huesos NO encontrados (se ocultaron del calibrador):", huesosFaltantes);
    const aviso = document.createElement("div");
    aviso.style.cssText = "color:#ffaa00; font-size:10px; padding:8px; border-bottom:1px solid var(--bord);";
    aviso.textContent = "Huesos faltantes: " + huesosFaltantes.join(", ");
    body.insertBefore(aviso, body.firstChild);
  }

  _panel.querySelectorAll("input[type=range]").forEach(input => {
    input.addEventListener("input", (e) => {
      const h = e.target.dataset.hueso;
      const eje = e.target.dataset.eje;
      const v = parseFloat(e.target.value);
      _valores[h][eje] = v;
      _panel.querySelector(`[data-val="${h}-${eje}"]`).textContent = v.toFixed(2);
    });
  });

  _panel.querySelector("#cal-reset").addEventListener("click", reset);
  _panel.querySelector("#cal-export").addEventListener("click", exportar);
  _panel.querySelector("#cal-cerrar").addEventListener("click", cerrar);

  _aplicarLoop = setInterval(aplicarPoses, 1000 / 30);
}

function aplicarPoses() {
  if (!_vrm?.humanoid) return;
  for (const hueso of HUESOS_PRINCIPALES) {
    const b = _vrm.humanoid.getNormalizedBoneNode(hueso);
    if (!b) continue;
    const v = _valores[hueso];
    b.rotation.x = v.x;
    b.rotation.y = v.y;
    b.rotation.z = v.z;
  }
}

function reset() {
  for (const hueso of HUESOS_PRINCIPALES) {
    _valores[hueso] = { x: 0, y: 0, z: 0 };
  }
  _panel.querySelectorAll("input[type=range]").forEach(input => {
    input.value = 0;
    const h = input.dataset.hueso;
    const eje = input.dataset.eje;
    _panel.querySelector(`[data-val="${h}-${eje}"]`).textContent = "0.00";
  });
}

function exportar() {
  const obj = {};
  for (const [hueso, v] of Object.entries(_valores)) {
    if (v.x !== 0 || v.y !== 0 || v.z !== 0) {
      obj[hueso] = [
        Math.round(v.x * 100) / 100,
        Math.round(v.y * 100) / 100,
        Math.round(v.z * 100) / 100,
      ];
    }
  }
  const json = JSON.stringify(obj, null, 2);
  _panel.querySelector("#cal-output").textContent = json;
  navigator.clipboard?.writeText(json);
  console.log("Pose copiada al portapapeles:", obj);
}

function cerrar() {
  window.__GEM_CALIBRANDO__ = false;
  if (_aplicarLoop) { clearInterval(_aplicarLoop); _aplicarLoop = null; }
  _panel?.remove();
  _abierto = false;
}

export const Calibrador = { abrir, cerrar, setVRM };