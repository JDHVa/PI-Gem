let _autoOcultar = null;

function _cont() {
  return document.getElementById("at-pasos");
}

function _mostrar() {
  document.getElementById("agent-trace").classList.add("on");
  if (_autoOcultar) { clearTimeout(_autoOcultar); _autoOcultar = null; }
}

function _programarOcultar() {
  if (_autoOcultar) clearTimeout(_autoOcultar);
  _autoOcultar = setTimeout(() => {
    document.getElementById("agent-trace").classList.remove("on");
  }, 6000);
}

function agregarPaso(evento) {
  const c = _cont();
  if (!c) return;

  if (evento.tipo === "inicio") {
    c.innerHTML = "";
    _mostrar();
    const el = document.createElement("div");
    el.className = "at-paso";
    el.textContent = `▶ Tarea: ${(evento.tarea || "").slice(0, 60)}`;
    c.appendChild(el);
    return;
  }

  if (evento.tipo === "pensando") {
    // No agregamos por cada "pensando" — sería ruido
    return;
  }

  if (evento.tipo === "herramienta_llama") {
    _mostrar();
    const el = document.createElement("div");
    el.className = "at-paso";
    const argsResumen = JSON.stringify(evento.args || {}).slice(0, 80);
    el.textContent = `${evento.icono || "🔩"} [${evento.paso}] ${evento.nombre} ${argsResumen}`;
    c.appendChild(el);
    c.scrollTop = c.scrollHeight;
    return;
  }

  if (evento.tipo === "herramienta_ok") {
    const ultimo = c.lastElementChild;
    if (ultimo) ultimo.classList.add("ok");
    return;
  }

  if (evento.tipo === "herramienta_error") {
    const ultimo = c.lastElementChild;
    if (ultimo) {
      ultimo.classList.add("error");
      ultimo.textContent += `  ✗ ${(evento.error || "").slice(0, 50)}`;
    }
    return;
  }

  if (evento.tipo === "fin") {
    const el = document.createElement("div");
    el.className = "at-paso ok";
    el.textContent = `✓ Listo (${evento.pasos || 0} pasos)`;
    c.appendChild(el);
    _programarOcultar();
  }
}

export const Agent = { agregarPaso };
