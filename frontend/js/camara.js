import { BACKEND } from './main.js';

let _activo = false;
let _pollTimer = null;

function abrir() {
  const modal = document.getElementById("modal-camara");
  const img   = document.getElementById("cam-stream");
  img.src = `${BACKEND}/camara/stream?anotado=true&fps=8&_=${Date.now()}`;
  modal.classList.add("on");
  _activo = true;
  actualizarInfo();
  _pollTimer = setInterval(actualizarInfo, 1000);
}

function cerrar() {
  document.getElementById("modal-camara").classList.remove("on");
  document.getElementById("cam-stream").src = "";
  _activo = false;
  if (_pollTimer) { clearInterval(_pollTimer); _pollTimer = null; }
}

async function actualizarInfo() {
  if (!_activo) return;
  try {
    const r = await fetch(`${BACKEND}/estado`);
    const e = await r.json();
    const v = e.vision || {};
    const idTxt = !v.identidad_activa
      ? "sin registrar"
      : (v.es_usuario ? `usuario ✓ (sim ${v.similitud})` : `desconocido (sim ${v.similitud})`);
    document.getElementById("cam-info").textContent =
      `Rostro: ${v.rostro_detectado ? "detectado" : "no"} · ID: ${idTxt} · Emo: ${v.emocion || "?"} · Caras: ${v.num_caras || 0}`;
  } catch (_) {}
}

async function registrar() {
  const info = document.getElementById("cam-info");
  info.textContent = "Capturando muestras durante ~8s. Quédate quieto, mira a la cámara, mueve un poco la cabeza...";
  try {
    const r = await fetch(`${BACKEND}/registrar_identidad`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ muestras: 10, timeout_s: 8.0 }),
    });
    const d = await r.json();
    info.textContent = d.mensaje || "Listo.";
  } catch (_) {
    info.textContent = "Error registrando.";
  }
}

export const Camara = { abrir, cerrar, registrar };