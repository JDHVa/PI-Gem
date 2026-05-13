import { BACKEND } from './main.js';
import { WS } from './ws.js';

async function enviar() {
  const ti = document.getElementById("ti");
  const sb = document.getElementById("sb");
  const txt = ti.value.trim();
  if (!txt) return;
  ti.value = ""; sb.disabled = true;
  WS.setBadge("procesando", "Pensando...");
  try {
    const r = await fetch(`${BACKEND}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ texto: txt }),
    });
    const d = await r.json();
    if (d.respuesta) document.getElementById("msg").textContent = d.respuesta;
  } catch (_) {
    document.getElementById("msg").textContent = "Error al conectar.";
  } finally {
    sb.disabled = false;
  }
}

export const Chat = { enviar };
