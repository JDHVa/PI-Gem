// Entry point GEM. Namespace global window.GEM.
import { WS }      from './ws.js';
import { Avatar }  from './avatar.js';
import { Chat }    from './chat.js';
import { Status }  from './status.js';
import { Skills }  from './skills.js';
import { Confirm } from './confirm.js';
import { Agent }   from './agent.js';
import { App }     from './app.js';
import { Camara }  from './camara.js';

export const BACKEND = "http://127.0.0.1:8770";
export const WS_URL  = "ws://localhost:8770/ws";

window.GEM = {
  backend: BACKEND,
  state:   { lastEstado: {}, proactivoActivo: false, ttsActivo: false, microfonoMuteado: false },
  ws:      WS,
  avatar:  Avatar,
  chat:    Chat,
  status:  Status,
  skills:  Skills,
  confirm: Confirm,
  agent:   Agent,
  app:     App,
  camara:  Camara,
};

// Avatar inicial
Avatar.init();
Avatar.mostrarFrame("alegre", 0);

// WS
WS.conectar();

// Estado: poll cada 2s
Status.iniciar();

// Input: Enter envía
document.getElementById("ti").addEventListener("keydown", e => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); Chat.enviar(); }
});

// Click fuera del panel cierra
document.addEventListener("click", ev => {
  const p = document.getElementById("panel");
  const d = document.getElementById("dots");
  if (Status.panelOpen && !p.contains(ev.target) && !d.contains(ev.target)) {
    Status.cerrarPanel();
  }
});

// Click en dots abre panel
document.getElementById("dots").addEventListener("click", () => Status.togglePanel());
