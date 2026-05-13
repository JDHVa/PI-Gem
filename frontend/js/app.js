import { BACKEND } from './main.js';

async function toggleProactivo() {
  const nuevo = !window.GEM.state.proactivoActivo;
  window.GEM.state.proactivoActivo = nuevo;
  document.getElementById("btn-proactivo").classList.toggle("active", nuevo);
  try {
    await fetch(`${BACKEND}/proactivo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activo: nuevo }),
    });
  } catch (_) {}
}

function abrirModalPerfil() {
  document.getElementById("modal-perfil").classList.add("on");
}

function cerrarModalPerfil() {
  document.getElementById("modal-perfil").classList.remove("on");
}

async function registrarPerfil() {
  const desc = document.getElementById("perfil-desc").value.trim();
  cerrarModalPerfil();
  document.getElementById("msg").textContent = "📷 Registrando perfil visual...";
  try {
    const r = await fetch(`${BACKEND}/registrar_perfil`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ descripcion: desc || "Sin descripción" }),
    });
    const d = await r.json();
    document.getElementById("msg").textContent = d.mensaje || "Perfil registrado.";
  } catch (_) {
    document.getElementById("msg").textContent = "Error registrando perfil.";
  }
}
async function registrarIdentidad() {
  document.getElementById("msg").textContent = "👤 Capturando rostro...";
  try {
    const r = await fetch(`${BACKEND}/registrar_identidad`, { method: "POST" });
    const d = await r.json();
    document.getElementById("msg").textContent = d.exito
      ? "Rostro registrado. Ahora te reconozco."
      : "No pude detectar tu rostro. Asegúrate de estar frente a la cámara.";
  } catch (_) {
    document.getElementById("msg").textContent = "Error al registrar rostro.";
  }
}
async function toggleMute() {
  const nuevo = !window.GEM.state.microfonoMuteado;
  window.GEM.state.microfonoMuteado = nuevo;
  const btn = document.getElementById("btn-mute");
  btn.classList.toggle("muted", nuevo);
  btn.textContent = nuevo ? "🔇" : "🎤";
  btn.title = nuevo ? "Micrófono silenciado — click para reactivar" : "Silenciar micrófono";
  try {
    await fetch(`${BACKEND}/mute_microfono`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ muteado: nuevo }),
    });
  } catch (_) {}
}

export const App = {
  toggleProactivo,
  abrirModalPerfil,
  cerrarModalPerfil,
  registrarPerfil,
  ocultarVentana,
  toggleMute,
  registrarIdentidad,
};
function ocultarVentana() {
  if (window.__TAURI__) window.__TAURI__.window.getCurrent().hide();
}
