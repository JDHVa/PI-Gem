import { BACKEND } from './main.js';
import { EMOJI } from './avatar.js';

let panelOpen = false;

function dot(id, cls, tt) {
  const d = document.getElementById(`d-${id}`);
  if (d) d.className = `d ${cls}`;
  const t = document.getElementById(`t-${id}`);
  if (t) t.textContent = tt;
}

function actualizarDots(e) {
  const v = e.vision || {}, m = e.memoria || {};
  const camOk   = v.emocion !== undefined;
  const faceOk  = !!v.rostro_detectado;
  const idReg   = !!v.identidad_activa;
  const idOk    = idReg && v.es_usuario;
  const emoUser = v.emocion || "neutro";
  const emoGEM  = e.emocion_gem || "alegre";
  const memTot  = Object.values(m).reduce((a, b) => a + b, 0);

  dot("cam",  camOk  ? "ok"   : "err",  `Cámara: ${camOk ? "activa" : "sin señal"}`);
  dot("face", faceOk ? "ok"   : "warn", `Rostro: ${faceOk ? "detectado" : "no detectado"}`);
  dot("id",   !idReg ? "warn" : (idOk ? "ok" : "err"),
              `ID: ${!idReg ? "sin registrar" : (idOk ? "reconocido ✓" : "no reconocido ✗")}`);
  dot("emo",  "info", `${EMOJI[emoUser] || "😐"} usuario · ${EMOJI[emoGEM] || "😐"} GEM`);
  dot("mem",  memTot > 0 ? "ok" : "warn", `Memoria: ${memTot} registros`);
  dot("sys",  e.silenciado ? "warn" : "ok",
              `${e.procesando ? "⚙ procesando" : "idle"} · ${e.silenciado ? "🔇" : "🔊"}`);

  if (panelOpen) renderPanel(e);
}

function renderPanel(e) {
  const v = e.vision || {}, m = e.memoria || {};
  const eu = v.emocion || "neutro", eg = e.emocion_gem || "alegre";
  const rows = [
    ["Cámara",         v.emocion !== undefined ? ["activa","ok"] : ["sin señal","err"]],
    ["Rostro",         v.rostro_detectado ? ["detectado","ok"] : ["no detectado","warn"]],
    ["Identidad",      !v.identidad_activa ? ["sin registrar","warn"] : (v.es_usuario ? ["reconocido ✓","ok"] : ["no reconocido ✗","err"])],
    ["Emo usuario",    [`${EMOJI[eu] || "😐"} ${eu}`, "info"]],
    ["Emo GEM",        [`${EMOJI[eg] || "😐"} ${eg}`, "info"]],
    ["Turnos",         [`${e.historial_turnos || 0}`, ""]],
    ["Conversaciones", [`${m.conversaciones || 0}`, m.conversaciones > 0 ? "ok" : "warn"]],
    ["Proyectos",      [`${m.proyectos || 0}`, ""]],
    ["Preferencias",   [`${m.preferencias || 0}`, ""]],
    ["Comandos",       [`${m.comandos || 0}`, ""]],
    ["Skills",         [`${e.skills || 0}`, e.skills > 0 ? "info" : ""]],
    ["Procesando",     [e.procesando ? "sí ⚙" : "no", e.procesando ? "warn" : "ok"]],
    ["Silenciado",     [e.silenciado ? "🔇 sí" : "🔊 no", e.silenciado ? "warn" : "ok"]],
  ];
  document.getElementById("pc").innerHTML = rows.map(([k, [v2, c]]) =>
    `<div class="pr"><span class="pk">${k}</span><span class="pv ${c}">${v2}</span></div>`
  ).join("");
}

async function poll() {
  try {
    const r = await fetch(`${BACKEND}/estado`);
    if (!r.ok) return;
    const estado = await r.json();
    window.GEM.state.lastEstado = estado;
    actualizarDots(estado);

    if (estado.proactivo !== undefined && estado.proactivo !== window.GEM.state.proactivoActivo) {
      window.GEM.state.proactivoActivo = estado.proactivo;
      const btn = document.getElementById("btn-proactivo");
      if (btn) btn.classList.toggle("active", estado.proactivo);
    }
  } catch (_) {}
}

function togglePanel() {
  panelOpen = !panelOpen;
  document.getElementById("panel").classList.toggle("on", panelOpen);
  if (panelOpen) renderPanel(window.GEM.state.lastEstado);
}

function cerrarPanel() {
  panelOpen = false;
  document.getElementById("panel").classList.remove("on");
}

function iniciar() {
  poll();
  setInterval(poll, 2000);
}

export const Status = {
  iniciar, poll, togglePanel, cerrarPanel,
  get panelOpen() { return panelOpen; },
};
