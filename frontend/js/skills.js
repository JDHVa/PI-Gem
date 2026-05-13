import { BACKEND } from './main.js';

async function cargar() {
  const cont = document.getElementById("skills-list");
  cont.innerHTML = `<div class="skills-empty">Cargando...</div>`;
  try {
    const r = await fetch(`${BACKEND}/skills`);
    const d = await r.json();
    const lista = d.skills || [];
    if (lista.length === 0) {
      cont.innerHTML = `<div class="skills-empty">
        Aún no tienes rutinas.<br/>
        Di: "guarda rutina mañana: abre code; abre spotify"
      </div>`;
      return;
    }
    cont.innerHTML = lista.map(s => `
      <div class="skill-item">
        <div>
          <div class="skill-name">${escapar(s.nombre)}</div>
          <div class="skill-meta">${s.pasos} paso${s.pasos === 1 ? "" : "s"} · ${escapar(s.descripcion || "")}</div>
        </div>
        <button class="skill-del" data-nombre="${escapar(s.nombre)}" title="Eliminar">🗑️</button>
      </div>
    `).join("");
    cont.querySelectorAll(".skill-del").forEach(btn => {
      btn.addEventListener("click", () => eliminar(btn.dataset.nombre));
    });
  } catch (_) {
    cont.innerHTML = `<div class="skills-empty">Error cargando rutinas.</div>`;
  }
}

async function eliminar(nombre) {
  try {
    await fetch(`${BACKEND}/skills/${encodeURIComponent(nombre)}`, { method: "DELETE" });
    cargar();
  } catch (_) {}
}

function abrir() {
  document.getElementById("modal-skills").classList.add("on");
  cargar();
}

function cerrar() {
  document.getElementById("modal-skills").classList.remove("on");
}

function escapar(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"})[c]);
}

export const Skills = { abrir, cerrar, cargar };
