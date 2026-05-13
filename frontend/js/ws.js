import { WS_URL } from './main.js';
import { Avatar }  from './avatar.js';
import { Chat }    from './chat.js';
import { Confirm } from './confirm.js';
import { Agent }   from './agent.js';

let _ws = null;

function setBadge(cls, txt) {
  document.getElementById("badge").className = cls;
  document.getElementById("btxt").textContent = txt;
}

function conectar() {
  _ws = new WebSocket(WS_URL);

  _ws.onmessage = ({ data }) => {
    let d; try { d = JSON.parse(data); } catch { return; }

    if (d.tipo === "expresion") {
      Avatar.cambiarEmocion(d.emocion);
    }
    else if (d.tipo === "lipsync") {
      Avatar.actualizarAmplitudHabla(d.amplitud || 0);
      if (d.terminado) {
        Avatar.detenerHabla();
        window.GEM.state.ttsActivo = false;
        setBadge("idle", "En espera");
      } else if ((d.amplitud || 0) > 0.01 && !window.GEM.state.ttsActivo) {
        Avatar.iniciarHabla();
        window.GEM.state.ttsActivo = true;
        setBadge("gem-habla", "Respondiendo");
      }
    }
    else if (d.tipo === "vad") {
      document.getElementById("vad").classList.toggle("on", d.hablando);
      setBadge(
        d.hablando ? "escuchando" : (window.GEM.state.ttsActivo ? "gem-habla" : "idle"),
        d.hablando ? "Te escucho" : (window.GEM.state.ttsActivo ? "Respondiendo" : "En espera")
      );
    }
    else if (d.tipo === "procesando") {
      if (d.activo) setBadge("procesando", "Pensando...");
      else if (!window.GEM.state.ttsActivo) setBadge("idle", "En espera");
    }
    else if (d.tipo === "respuesta") {
      document.getElementById("msg").textContent = d.texto || "";
    }
    else if (d.tipo === "trigger_proactivo") {
      console.log("trigger proactivo:", d.subtipo, d.mensaje);
    }
    else if (d.tipo === "confirmar") {
      Confirm.abrir(d.id, d.accion, d.args);
    }
    else if (d.tipo === "agente") {
      Agent.agregarPaso(d);
    }
  };

  _ws.onclose = () => setTimeout(conectar, 2000);
  _ws.onerror = () => _ws.close();
}

function enviar(obj) {
  if (_ws && _ws.readyState === WebSocket.OPEN) {
    _ws.send(JSON.stringify(obj));
    return true;
  }
  return false;
}

export const WS = { conectar, enviar, setBadge };