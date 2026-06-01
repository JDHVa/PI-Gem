import { BACKEND } from './main.js';

const MODELOS_DISPONIBLES = [
  { id: 'gemini-2.5-flash',           nombre: 'Gemini 2.5 Flash',       tipo: 'gemini' },
  { id: 'gemini-3.5-flash',           nombre: 'Gemini 3.5 Flash',       tipo: 'gemini' },
  { id: 'gemini-3.1-pro',             nombre: 'Gemini 3.1 Pro',         tipo: 'gemini' },
  { id: 'claude-opus-4-7',            nombre: 'Claude Opus 4.7',        tipo: 'claude' },
  { id: 'claude-sonnet-4-6',          nombre: 'Claude Sonnet 4.6',      tipo: 'claude' },
  { id: 'claude-3-5-sonnet-v2@20241022', nombre: 'Claude 3.5 Sonnet v2', tipo: 'claude' },
];

let _modeloActual = '';

async function cargarModelo() {
  try {
    const r = await fetch(`${BACKEND}/modelo`);
    const d = await r.json();
    _modeloActual = d.modelo || '';
  } catch (_) {
    _modeloActual = '?';
  }
}

function _renderLista() {
  const cont = document.getElementById('modelo-lista');
  const actual = document.getElementById('modelo-actual');
  actual.textContent = _modeloActual || '—';

  cont.innerHTML = '';
  for (const m of MODELOS_DISPONIBLES) {
    const el = document.createElement('div');
    el.className = 'modelo-item' + (m.id === _modeloActual ? ' active' : '');
    el.innerHTML = `
      <span class="modelo-nombre">${m.nombre}</span>
      <span class="modelo-tag ${m.tipo}">${m.tipo}</span>
    `;
    el.onclick = () => cambiarModelo(m.id);
    cont.appendChild(el);
  }
}

async function cambiarModelo(id) {
  try {
    const r = await fetch(`${BACKEND}/modelo`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ modelo: id }),
    });
    const d = await r.json();
    _modeloActual = d.modelo;
    _renderLista();
    document.getElementById('msg').textContent = `Modelo cambiado a: ${_modeloActual}`;
  } catch (e) {
    document.getElementById('msg').textContent = 'Error al cambiar modelo.';
  }
}

async function abrir() {
  await cargarModelo();
  _renderLista();
  document.getElementById('modal-modelo').classList.add('on');
}

function cerrar() {
  document.getElementById('modal-modelo').classList.remove('on');
}

export const Modelo = { abrir, cerrar, cargarModelo };
