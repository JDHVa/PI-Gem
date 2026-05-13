import { BACKEND } from './main.js';

let _idPendiente = null;

function abrir(id, accion, args) {
  _idPendiente = id;
  const argsTexto = Object.entries(args || {})
    .map(([k, v]) => `${k}: ${v}`)
    .join("\n");
  document.getElementById("confirm-text").textContent =
    `GEM quiere ejecutar: ${accion}\n\n${argsTexto}\n\n¿Autorizas?`;
  document.getElementById("modal-confirm").classList.add("on");
}

function cerrar() {
  document.getElementById("modal-confirm").classList.remove("on");
  _idPendiente = null;
}

async function responder(autorizado) {
  if (!_idPendiente) { cerrar(); return; }
  try {
    await fetch(`${BACKEND}/confirmar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: _idPendiente, autorizado }),
    });
  } catch (_) {}
  cerrar();
}

export const Confirm = { abrir, cerrar, responder };
