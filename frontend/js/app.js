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
let _compacto = false;

function toggleCompacto() {
  _compacto = !_compacto;
  const ocultar = ["#drag", "#badge", "#vad", "#msg", "#dots", "#input-row"];

  if (_compacto) {
    ocultar.forEach(sel => {
      const el = document.querySelector(sel);
      if (el) el.style.display = "none";
    });

    // Botón flotante para regresar
    let fab = document.getElementById("fab-regresar");
    if (!fab) {
      fab = document.createElement("button");
      fab.id = "fab-regresar";
      fab.textContent = "✦";
      fab.title = "Mostrar interfaz";
      fab.onclick = toggleCompacto;
      document.body.appendChild(fab);
    }
    fab.style.display = "flex";

    document.body.style.pointerEvents = "none";
    fab.style.pointerEvents = "auto";
    document.getElementById("av-wrap").style.pointerEvents = "auto";
  } else {
    ocultar.forEach(sel => {
      const el = document.querySelector(sel);
      if (el) el.style.display = "";
    });
    const fab = document.getElementById("fab-regresar");
    if (fab) fab.style.display = "none";
    document.body.style.pointerEvents = "";
  }
}

export const App = {
  toggleProactivo,
  abrirModalPerfil,
  cerrarModalPerfil,
  registrarPerfil,
  ocultarVentana,
  toggleMute,
  registrarIdentidad,
  toggleCompacto,
  toggleSoloTexto,
  toggleAvatarMinimizado,
};
function ocultarVentana() {
  if (window.__TAURI__) window.__TAURI__.window.getCurrent().hide();
}

let _soloTexto = false;
async function toggleSoloTexto() {
  _soloTexto = !_soloTexto;
  const body = document.body;
  body.classList.toggle("solo-texto", _soloTexto);

  if (!_soloTexto) {
    body.classList.remove("avatar-visible");
    const btnA = document.getElementById("btn-toggle-avatar");
    if (btnA) btnA.classList.remove("active");
  }

  const btn = document.getElementById("btn-solotexto");
  if (btn) {
    btn.classList.toggle("active", _soloTexto);
  }

  // Redimensionar la ventana de Tauri si está disponible
  if (window.__TAURI__) {
    try {
      const { LogicalSize, getCurrent } = window.__TAURI__.window;
      const win = getCurrent();
      if (_soloTexto) {
        // Redimensionar a una barra de texto compacta (altura 80px)
        await win.setMinSize(new LogicalSize(380, 80));
        await win.setSize(new LogicalSize(480, 80));
      } else {
        // Restaurar el tamaño estándar
        await win.setMinSize(new LogicalSize(380, 600));
        await win.setSize(new LogicalSize(480, 800));
      }
    } catch (err) {
      console.error("Error al cambiar tamaño de ventana en Tauri:", err);
    }
  }
}

async function toggleAvatarMinimizado() {
  const body = document.body;
  const mostrando = body.classList.toggle("avatar-visible");
  const btn = document.getElementById("btn-toggle-avatar");
  if (btn) {
    btn.classList.toggle("active", mostrando);
  }

  if (window.__TAURI__) {
    try {
      const { LogicalSize, getCurrent } = window.__TAURI__.window;
      const win = getCurrent();
      if (mostrando) {
        await win.setMinSize(new LogicalSize(380, 500));
        await win.setSize(new LogicalSize(480, 600));
      } else {
        await win.setMinSize(new LogicalSize(380, 80));
        await win.setSize(new LogicalSize(480, 80));
      }
    } catch (e) {
      console.error(e);
    }
  }
}
