// Jarvis Orbe 2D — Canvas con partículas, sin WebGL
// Mucho más ligero que la versión 3D

const COLORES_EMOCION = {
  alegre:    { core: "#00e5ff", glow: "#00b8d4", particle: "#80f0ff" },
  neutro:    { core: "#00c8ff", glow: "#0091ea", particle: "#64d8ff" },
  pensativo: { core: "#7c4dff", glow: "#6200ea", particle: "#b388ff" },
  triste:    { core: "#3d5afe", glow: "#1a237e", particle: "#8c9eff" },
  enojado:   { core: "#ff1744", glow: "#d50000", particle: "#ff8a80" },
  confundido:{ core: "#ffab00", glow: "#ff8f00", particle: "#ffe57f" },
  ansioso:   { core: "#ff6d00", glow: "#e65100", particle: "#ffab40" },
  dormido:   { core: "#1a237e", glow: "#0d1642", particle: "#3949ab" },
  hablando:  { core: "#00e5ff", glow: "#00b8d4", particle: "#80f0ff" },
};

const NUM_PARTICULAS = 80;
const NUM_ANILLOS = 3;

let _canvas, _ctx;
let _activo = false;
let _animFrame = null;
let _tiempo = 0;

let _colorActual = {
  core:     _hexToRgb(COLORES_EMOCION.neutro.core),
  glow:     _hexToRgb(COLORES_EMOCION.neutro.glow),
  particle: _hexToRgb(COLORES_EMOCION.neutro.particle)
};
let _colorTarget = {
  core:     _hexToRgb(COLORES_EMOCION.neutro.core),
  glow:     _hexToRgb(COLORES_EMOCION.neutro.glow),
  particle: _hexToRgb(COLORES_EMOCION.neutro.particle)
};
let _amplitudActual = 0;
let _amplitudTarget = 0;
let _vadActivo = false;

let _particulas = [];
let _anillos = [];

function _hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return { r, g, b };
}

function _lerpColores(t) {
  for (const key of ["core", "glow", "particle"]) {
    _colorActual[key].r += (_colorTarget[key].r - _colorActual[key].r) * t;
    _colorActual[key].g += (_colorTarget[key].g - _colorActual[key].g) * t;
    _colorActual[key].b += (_colorTarget[key].b - _colorActual[key].b) * t;
  }
}

function _colorStr(c, alpha) {
  const r = Math.round(c.r);
  const g = Math.round(c.g);
  const b = Math.round(c.b);
  if (alpha !== undefined) {
    return `rgba(${r},${g},${b},${alpha})`;
  }
  return `rgb(${r},${g},${b})`;
}

function _initParticulas() {
  _particulas = [];
  for (let i = 0; i < NUM_PARTICULAS; i++) {
    const angulo = Math.random() * Math.PI * 2;
    const dist   = 0.55 + Math.random() * 0.45;
    _particulas.push({
      angulo,
      dist,
      vel:     0.2 + Math.random() * 0.5,
      size:    1 + Math.random() * 2.5,
      offset:  Math.random() * Math.PI * 2,
      opBase:  0.2 + Math.random() * 0.5,
    });
  }

  _anillos = [];
  for (let i = 0; i < NUM_ANILLOS; i++) {
    _anillos.push({
      radio:    0.35 + i * 0.12,
      rotacion: Math.random() * Math.PI * 2,
      vel:      0.3 + Math.random() * 0.4,
      grosor:   0.5 + Math.random(),
      opBase:   0.1 + Math.random() * 0.15,
    });
  }
}

function init(contenedor) {
  _canvas = document.createElement("canvas");
  _canvas.id = "jarvis2d";
  _canvas.width = 600;
  _canvas.height = 600;
  _canvas.style.width  = "100%";
  _canvas.style.height = "100%";
  _canvas.style.maxWidth  = "460px";
  _canvas.style.maxHeight = "460px";
  _canvas.style.display = "none";
  contenedor.appendChild(_canvas);
  _ctx = _canvas.getContext("2d");
  _initParticulas();
  console.log("Jarvis 2D inicializado");
}

function _dibujar() {
  const w = _canvas.width, h = _canvas.height;
  const cx = w / 2, cy = h / 2;
  // Usamos un radio base estático de 70 (en lugar de dinámico por pantalla) para un canvas de 600x600
  const radio = 70;

  _ctx.clearRect(0, 0, w, h);

  const pulso = Math.sin(_tiempo * 1.5) * 0.06 + 1.0;
  const radioActual = radio * pulso + radio * _amplitudActual * 0.25;

  // Glow exterior (frenado a un tamaño que no se desborde del canvas 600x600)
  const glowSize = radioActual * (1.8 + _amplitudActual * 0.8);
  const gradGlow = _ctx.createRadialGradient(cx, cy, radioActual * 0.3, cx, cy, glowSize);
  gradGlow.addColorStop(0, _colorStr(_colorActual.glow, 0.25));
  gradGlow.addColorStop(0.4, _colorStr(_colorActual.glow, 0.08));
  gradGlow.addColorStop(1, _colorStr(_colorActual.glow, 0.0));
  _ctx.fillStyle = gradGlow;
  _ctx.fillRect(0, 0, w, h);

  // Anillos orbitales (ajustado para mantenerse dentro del canvas de 600)
  for (const anillo of _anillos) {
    const r = radioActual * (anillo.radio / 0.35) * (1.1 + _amplitudActual * 0.3);
    anillo.rotacion += anillo.vel * 0.016 * (1 + _amplitudActual * 3);
    const op = anillo.opBase + _amplitudActual * 0.3;

    _ctx.save();
    _ctx.translate(cx, cy);
    _ctx.rotate(anillo.rotacion);
    _ctx.strokeStyle = _colorStr(_colorActual.particle);
    _ctx.globalAlpha = op;
    _ctx.lineWidth = anillo.grosor;
    _ctx.setLineDash([3 + _amplitudActual * 10, 8 + Math.sin(_tiempo * 2 + anillo.rotacion) * 5]);
    _ctx.beginPath();
    _ctx.ellipse(0, 0, r, r * 0.4, 0, 0, Math.PI * 2);
    _ctx.stroke();
    _ctx.setLineDash([]);
    _ctx.globalAlpha = 1;
    _ctx.restore();
  }

  // Partículas (ajustado radio de dispersión máxima a p.dist * 1.3)
  for (const p of _particulas) {
    p.angulo += p.vel * 0.016 * (1 + _amplitudActual * 4);
    const dist = radioActual * (p.dist * 1.3 + _amplitudActual * 0.4);
    const wobble = Math.sin(_tiempo * 2 + p.offset) * radioActual * 0.08;
    const px = cx + Math.cos(p.angulo) * (dist + wobble);
    const py = cy + Math.sin(p.angulo) * (dist + wobble) * 0.6;
    const op = p.opBase + _amplitudActual * 0.4 + Math.sin(_tiempo * 3 + p.offset) * 0.1;
    const sz = p.size * (1 + _amplitudActual * 1.5);

    _ctx.globalAlpha = Math.max(0, Math.min(1, op));
    _ctx.fillStyle = _colorStr(_colorActual.particle);
    _ctx.beginPath();
    _ctx.arc(px, py, sz, 0, Math.PI * 2);
    _ctx.fill();
  }
  _ctx.globalAlpha = 1;

  // Esfera core
  const gradCore = _ctx.createRadialGradient(
    cx - radioActual * 0.15, cy - radioActual * 0.15, 0,
    cx, cy, radioActual
  );
  gradCore.addColorStop(0, "#ffffff");
  gradCore.addColorStop(0.15, _colorStr(_colorActual.core));
  gradCore.addColorStop(0.6, _colorStr(_colorActual.glow));
  gradCore.addColorStop(1, _colorStr(_colorActual.glow, 0.0));

  _ctx.fillStyle = gradCore;
  _ctx.beginPath();
  _ctx.arc(cx, cy, radioActual, 0, Math.PI * 2);
  _ctx.fill();

  // Borde brillante
  const gradBorde = _ctx.createRadialGradient(cx, cy, radioActual * 0.85, cx, cy, radioActual * 1.1);
  gradBorde.addColorStop(0, "transparent");
  gradBorde.addColorStop(0.5, _colorStr(_colorActual.core, 0.37));
  gradBorde.addColorStop(1, "transparent");
  _ctx.strokeStyle = gradBorde;
  _ctx.lineWidth = 2 + _amplitudActual * 3;
  _ctx.beginPath();
  _ctx.arc(cx, cy, radioActual, 0, Math.PI * 2);
  _ctx.stroke();

  // Reflejo especular
  _ctx.globalAlpha = 0.4 - _amplitudActual * 0.1;
  const gradSpec = _ctx.createRadialGradient(
    cx - radioActual * 0.25, cy - radioActual * 0.3, 0,
    cx - radioActual * 0.15, cy - radioActual * 0.2, radioActual * 0.5,
  );
  gradSpec.addColorStop(0, "#ffffff");
  gradSpec.addColorStop(1, "transparent");
  _ctx.fillStyle = gradSpec;
  _ctx.beginPath();
  _ctx.arc(cx, cy, radioActual, 0, Math.PI * 2);
  _ctx.fill();
  _ctx.globalAlpha = 1;

  // Noise interno (distorsión cuando habla)
  if (_amplitudActual > 0.05) {
    const noiseCount = Math.floor(_amplitudActual * 12);
    for (let i = 0; i < noiseCount; i++) {
      const na = Math.random() * Math.PI * 2;
      const nr = Math.random() * radioActual * 0.8;
      const ns = 1 + Math.random() * 3 * _amplitudActual;
      _ctx.globalAlpha = _amplitudActual * 0.3;
      _ctx.fillStyle = "#ffffff";
      _ctx.beginPath();
      _ctx.arc(cx + Math.cos(na) * nr, cy + Math.sin(na) * nr, ns, 0, Math.PI * 2);
      _ctx.fill();
    }
    _ctx.globalAlpha = 1;
  }
}

function _loop() {
  if (!_activo) return;
  _animFrame = requestAnimationFrame(_loop);
  _tiempo += 0.016;

  _amplitudActual += (_amplitudTarget - _amplitudActual) * 0.15;
  _lerpColores(0.05);
  _dibujar();
}

function activar() {
  if (!_canvas) return;
  _canvas.style.display = "";
  _activo = true;
  _tiempo = 0;
  _loop();
}

function desactivar() {
  _activo = false;
  if (_animFrame) { cancelAnimationFrame(_animFrame); _animFrame = null; }
  if (_canvas) _canvas.style.display = "none";
}

function cambiarEmocion(emocion) {
  const c = COLORES_EMOCION[emocion] || COLORES_EMOCION.neutro;
  _colorTarget.core = _hexToRgb(c.core);
  _colorTarget.glow = _hexToRgb(c.glow);
  _colorTarget.particle = _hexToRgb(c.particle);
}

function setAmplitud(rms) {
  _amplitudTarget = Math.min(1, Math.max(0, rms * 8));
}

function iniciarHabla() {
  _amplitudTarget = 0.3;
}

function detenerHabla() {
  _amplitudTarget = 0;
}

function setVAD(activo) {
  _vadActivo = activo;
  if (activo) _amplitudTarget = Math.max(_amplitudTarget, 0.1);
}

function estaActivo() {
  return _activo;
}

export const Jarvis = {
  init, activar, desactivar,
  cambiarEmocion, setAmplitud,
  iniciarHabla, detenerHabla,
  setVAD, estaActivo,
};