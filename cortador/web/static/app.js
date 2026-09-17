/* Cortador - by Brumet.  Logica del panel: formulario -> API -> visor 3D. */
import { Viewer } from '/static/viewer.js';

const $ = (id) => document.getElementById(id);
const estado = {
  trabajo: null,
  factor: 1,
  plan: null,
  resumen: null,
  fuente: 'original',   // que se esta viendo: original | piezas
  windows: false,
};

let visor = null;
try {
  visor = new Viewer($('vista'));
  aplicarTema();
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', aplicarTema);
} catch (err) {
  $('vacio').innerHTML = `<h1>WebGL no disponible</h1><p>${err.message}</p>
    <p class="tenue">Puedes seguir usando Cortador desde la terminal:
    <code>cortador cortar modelo.stl</code></p>`;
}

function aplicarTema() {
  if (!visor) return;
  const css = getComputedStyle(document.body).getPropertyValue('--lienzo').trim();
  const m = css.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const n = parseInt(m[1], 16);
    visor.background = [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
      .map((c) => Math.pow(c, 2.2));
  }
  const oscuro = window.matchMedia('(prefers-color-scheme: dark)').matches;
  visor.lineColor = oscuro ? [0.35, 0.62, 0.95, 1] : [0.0, 0.44, 0.89, 0.75];
  // la esfera de material: una para el tema oscuro y otra para el claro
  visor.setMatcap(oscuro ? '/static/matcap-oscuro.png' : '/static/matcap-claro.png');
  visor.render();
}

// ------------------------------------------------------------ utilidades
function num(id, def) {
  const v = parseFloat($(id).value);
  return Number.isFinite(v) ? v : def;
}

function modoActual() {
  return $('modo').querySelector('.activo').dataset.valor;
}

function formaCama() {
  const activo = $('forma-cama').querySelector('.activo');
  return activo ? activo.dataset.valor : 'rect';
}

/* Caja util de la maquina: en una cama redonda no cabe el diametro entero,
   sino el cuadrado que cabe dentro (diametro / raiz de 2). */
function cajaUtil() {
  const margen = num('margen', 5);
  if (formaCama() === 'round') {
    const lado = num('diametro', 300) / Math.SQRT2 - 2 * margen;
    return [lado, lado, num('pz-round', 410) - 2 * margen];
  }
  return [num('px', 220) - 2 * margen, num('py', 220) - 2 * margen,
          num('pz', 250) - 2 * margen];
}

function anchoLinea() {
  return Math.round(num('boquilla', 0.4) * 1.05 * 1000) / 1000;
}

function pintarUtilMaquina() {
  const [x, y, z] = cajaUtil().map((v) => Math.max(0, v));
  const redonda = formaCama() === 'round';
  const linea = anchoLinea();
  $('util-maquina').textContent =
    `Pieza mas grande que cabe: ${x.toFixed(0)} x ${y.toFixed(0)} x ${z.toFixed(0)} mm`
    + (redonda ? ' (el cuadrado que cabe en la cama redonda)' : '')
    + ` · linea de ${linea.toFixed(2)} mm con esa boquilla.`;
}

function leerConfig() {
  const divisiones = $('divisiones').value.trim();
  let div = null;
  if (divisiones) {
    const partes = divisiones.toLowerCase().replace(/\*/g, 'x').split('x');
    if (partes.length === 3) {
      div = partes.map((p) => (['', '-', 'auto'].includes(p.trim())
        ? null : Math.max(1, parseInt(p, 10) || 1)));
    }
  }
  const redonda = formaCama() === 'round';
  return {
    printer: redonda ? {
      x: num('diametro', 300), y: num('diametro', 300), z: num('pz-round', 410),
      clearance: num('margen', 5), shape: 'round', diameter: num('diametro', 300),
      nozzle: num('boquilla', 0.4), technology: $('tecnologia').value,
    } : {
      x: num('px', 220), y: num('py', 220), z: num('pz', 250),
      clearance: num('margen', 5), shape: 'rect',
      nozzle: num('boquilla', 0.4), technology: $('tecnologia').value,
    },
    rotation: [num('giro-x', 0), num('giro-y', 0), num('giro-z', 0)],
    auto_base: $('apoyar').checked,
    mode: modoActual(),
    slab_thickness: num('espesor', 5),
    slab_axis: $('eje').value,
    slab_style: $('estilo-lamina').value,
    slab_fit: $('ajuste-lamina').value,
    split_slabs_to_fit: $('subdividir').checked,
    divisions: div,
    hollow: $('hueco').checked,
    wall: num('pared', 3),
    solid_caps: $('tapas').checked,
    label_tab: $('lengueta').checked,
    min_piece: num('minima', 5),
    kerf: num('kerf', 0),
    scale: num('escala', 1),
    target_size: $('tamano').value ? num('tamano', 0) : null,
    target_axis: $('tamano-eje').value,
    units: $('unidades').value,
    engine: $('motor').value,
    weld: $('unir').checked,
    naming: 'grid',
    labels: {
      enabled: $('marcas').checked,
      style: $('marca-estilo').value,
      size: num('marca-tam', 8),
      depth: num('marca-prof', 0.8),
      stroke: num('marca-trazo', 1.2),
      placement: $('marca-caras').value,
      prefix: $('prefijo').value,
    },
    joinery: {
      mode: $('espigas').value,
      radius: num('espiga-radio', 3),
      depth: num('espiga-prof', 6),
      count: Math.round(num('espiga-num', 2)),
      auto: $('espiga-auto').checked,
    },
  };
}

function escapar(t) {
  return String(t).replace(/[<>&"]/g, (c) => (
    { '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;' }[c]));
}

function mostrarAvisos(lista, esError) {
  const caja = $('avisos');
  lista = (lista || []).filter(Boolean);
  if (!lista.length) { caja.hidden = true; return; }
  caja.hidden = false;
  caja.className = 'aviso' + (esError ? ' error' : '');
  caja.innerHTML = `<b>${esError ? 'Error' : 'Avisos'}</b><ul>${
    lista.map((t) => `<li>${escapar(t)}</li>`).join('')}</ul>`;
}

async function api(url, opciones) {
  const res = await fetch(url, opciones);
  if (!res.ok) {
    let detalle = res.statusText;
    try { detalle = (await res.json()).detail || detalle; } catch (e) { /* noop */ }
    throw new Error(detalle);
  }
  return res;
}

// ------------------------------------------------------------ progreso
const CONSEJOS = [
  'Cada pieza se marca con su nombre en una cara de corte.',
  'El vaciado deja el modelo hueco: mucho menos material y menos horas.',
  'Las laminas planas salen tambien en SVG y DXF para la laser.',
  'Puedes descargar una pieza suelta desde la lista del despiece.',
  'Con muchas laminas el corte tarda mas: sigue trabajando.',
  'La guia de armado te dice que pieza va con cual, capa por capa.',
];

const reloj = { inicio: 0, id: null, muestras: [] };

function relojArrancar(etapa) {
  reloj.inicio = Date.now();
  reloj.muestras = [];
  let consejo = 0;
  $('progreso-etapa').textContent = etapa || 'Preparando';
  $('progreso-consejo').textContent = CONSEJOS[0];
  $('progreso').style.width = '0%';
  $('progreso-txt').textContent = '';
  clearInterval(reloj.id);
  reloj.id = setInterval(() => {
    const seg = (Date.now() - reloj.inicio) / 1000;
    $('progreso-tiempo').textContent = formatoTiempo(seg) + restante();
    if (seg > 5 && Math.floor(seg / 6) !== consejo) {
      consejo = Math.floor(seg / 6);
      $('progreso-consejo').textContent = CONSEJOS[consejo % CONSEJOS.length];
    }
  }, 250);
}

function relojParar() {
  clearInterval(reloj.id);
  reloj.id = null;
}

function formatoTiempo(seg) {
  const m = Math.floor(seg / 60);
  const s = Math.floor(seg % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

function restante() {
  // estimacion con el ritmo de los ultimos avances
  const m = reloj.muestras;
  if (m.length < 3) return '';
  const [t0, p0] = m[0];
  const [t1, p1] = m[m.length - 1];
  if (p1 <= p0 || p1 >= 1) return '';
  const total = (t1 - t0) / (p1 - p0);
  const falta = total * (1 - p1);
  if (!Number.isFinite(falta) || falta < 2 || falta > 36000) return '';
  return `  ·  quedan ~${formatoTiempo(falta)}`;
}

function marcarAvance(hecho, total, etapa) {
  const pct = Math.max(0, Math.min(1, hecho / Math.max(total, 1)));
  $('progreso').style.width = (pct * 100).toFixed(1) + '%';
  $('progreso-etapa').textContent = etapa || 'Trabajando';
  $('progreso-txt').textContent = total > 1 ? `${hecho} / ${total}` : '';
  const ahora = (Date.now() - reloj.inicio) / 1000;
  if (pct > 0) reloj.muestras.push([ahora, pct]);
  if (reloj.muestras.length > 40) reloj.muestras.shift();
}

// ------------------------------------------------------------ carga del modelo
async function cargarArchivo(file) {
  if (!file) return;
  $('nombre-archivo').textContent = 'abriendo ' + file.name + '...';
  $('vacio').hidden = true;
  $('abriendo').hidden = false;
  $('abriendo-etapa').textContent = 'Leyendo ' + file.name;
  $('abriendo-txt').textContent =
    file.size > 20e6 ? 'Son ' + (file.size / 1e6).toFixed(0)
      + ' MB: puede tardar un minuto. No cierres la ventana.'
      : 'Revisando la malla y reparandola si hace falta...';
  const datos = new FormData();
  datos.append('archivo', file);
  try {
    const res = await api('/api/modelo', { method: 'POST', body: datos });
    const info = await res.json();
    estado.trabajo = info.trabajo;
    estado.fuente = 'original';
    estado.windows = !!info.windows;
    $('nombre-archivo').textContent =
      `${info.archivo} · ${info.modelo.triangles.toLocaleString('es')} triangulos`;
    $('btn-cortar').disabled = false;
    $('btn-descargar').hidden = true;
    $('btn-guia').hidden = true;
    $('btn-abrir').hidden = true;
    $('vacio').hidden = true;
    $('resumen').hidden = false;
    $('controles').hidden = false;
    $('pista-lista').hidden = false;
    $('lista').innerHTML = '';
    $('contador').textContent = '';
    pintarEstadoMalla(info);
    mostrarAvisos([]);
    await verOriginal();
    actualizarPlan();
  } catch (err) {
    $('nombre-archivo').textContent = 'ningun modelo cargado';
    $('vacio').hidden = !!estado.trabajo;
    mostrarAvisos([err.message], true);
  } finally {
    $('abriendo').hidden = true;
  }
}

function pintarEstadoMalla(info) {
  const rep = info.reparacion || {};
  const tarjeta = $('tarjeta-malla');
  const bloque = $('estado-malla');
  tarjeta.hidden = false;
  $('nota-reparar').hidden = true;
  $('btn-malla').hidden = !rep.cambiada;
  $('btn-malla').href = `/api/malla/${estado.trabajo}`;

  if (rep.ok) {
    bloque.classList.remove('mal');
    $('estado-titulo').textContent = rep.cambiada ? 'Reparada y lista' : 'Malla correcta';
    $('estado-texto').textContent = rep.resumen || '';
    $('btn-reparar').hidden = true;
  } else {
    bloque.classList.add('mal');
    $('estado-titulo').textContent = 'La malla tiene fallos';
    $('estado-texto').textContent = (rep.resumen || '')
      + ' ' + ((rep.problemas || []).join('; '));
    $('btn-reparar').hidden = false;
    $('btn-reparar').textContent = estado.windows
      ? 'Reparar con 3D Builder' : 'Como reparar la malla';
  }
}

async function repararEnWindows() {
  if (!estado.trabajo) return;
  $('btn-reparar').disabled = true;
  try {
    const info = await (await api(`/api/reparar/${estado.trabajo}`, { method: 'POST' })).json();
    const nota = $('nota-reparar');
    nota.hidden = false;
    nota.textContent = info.mensaje;
  } catch (err) {
    mostrarAvisos([err.message], true);
  }
  $('btn-reparar').disabled = false;
}

async function verOriginal() {
  const res = await api(`/api/vista/${estado.trabajo}?fuente=original`);
  visor.setPayload(await res.arrayBuffer());
  visor.frameAll();
  estado.fuente = 'original';
  pintarRejilla();
  $('r-piezas').textContent = '-';
  visor.render();
}

// ------------------------------------------------------------ plan en vivo
let temporizador = null;
function actualizarPlan() {
  if (!estado.trabajo) return;
  clearTimeout(temporizador);
  temporizador = setTimeout(async () => {
    try {
      const res = await api('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ trabajo: estado.trabajo, config: leerConfig() }),
      });
      const plan = await res.json();
      estado.plan = plan;
      estado.factor = plan.factor || 1;
      const [nx, ny, nz] = plan.counts;
      $('r-rejilla').textContent = `${nx}x${ny}x${nz}`;
      $('r-mayor').textContent = plan.piece_size.map((v) => v.toFixed(0)).join(' x ');
      $('r-tamano').textContent = plan.modelo.size.map((v) => v.toFixed(0)).join(' x ');
      if (estado.fuente === 'original') $('r-piezas').textContent = '~' + plan.total_cells;
      $('capa').max = Math.max(0, plan.layers);
      pintarPistaEscala(plan);
      mostrarAvisos(plan.warnings, false);
      pintarRejilla();
    } catch (err) {
      mostrarAvisos([err.message], true);
    }
  }, 180);
}

function pintarPistaEscala(plan) {
  const f = plan.factor || 1;
  const s = plan.modelo.size;
  const texto = Math.abs(f - 1) < 1e-6
    ? `Tamano original: ${s[0].toFixed(0)} x ${s[1].toFixed(0)} x ${s[2].toFixed(0)} mm.`
    : `Escala x${f.toFixed(3)} → ${s[0].toFixed(0)} x ${s[1].toFixed(0)} x ${s[2].toFixed(0)} mm `
      + `(${(s[2] / 1000).toFixed(2)} m de alto).`;
  $('pista-escala').textContent = texto;
}

function pintarRejilla() {
  if (!visor || !estado.plan) return;
  const f = estado.fuente === 'original' ? (estado.factor || 1) : 1;
  visor.setGrid(estado.plan.edges.map((eje) => eje.map((v) => v / f)));
  visor.render();
}

// ------------------------------------------------------------ corte
async function cortar() {
  if (!estado.trabajo) return;
  $('btn-cortar').disabled = true;
  $('btn-cortar').textContent = 'Cortando...';
  $('cargando').hidden = false;
  relojArrancar('Preparando el modelo');
  try {
    await api('/api/cortar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trabajo: estado.trabajo, config: leerConfig(),
                             formato: $('formato').value,
                             origen: $('origen').checked }),
    });
    await seguirProgreso();
  } catch (err) {
    mostrarAvisos([err.message], true);
    $('cargando').hidden = true;
  }
  relojParar();
  $('btn-cortar').disabled = false;
  $('btn-cortar').textContent = 'Cortar';
}

async function seguirProgreso() {
  for (;;) {
    await new Promise((r) => setTimeout(r, 350));
    let info;
    try {
      info = await (await api(`/api/progreso/${estado.trabajo}`)).json();
    } catch (err) {
      mostrarAvisos([err.message], true);
      break;
    }
    marcarAvance(info.hecho, info.total, info.mensaje);
    if (info.estado === 'listo') {
      estado.resumen = info.resumen;
      await verPiezas();
      break;
    }
    if (info.estado === 'error') {
      mostrarAvisos([info.error || 'El corte ha fallado'], true);
      break;
    }
  }
  relojParar();
  $('cargando').hidden = true;
}

async function verPiezas() {
  const res = await api(`/api/vista/${estado.trabajo}?fuente=piezas`);
  visor.setPayload(await res.arrayBuffer());
  estado.fuente = 'piezas';
  visor.frameAll();
  pintarRejilla();
  const resumen = estado.resumen;
  $('r-piezas').textContent = resumen.piezas;
  $('r-rejilla').textContent = resumen.rejilla.join('x');
  if (resumen.litros) {
    $('dato-material').hidden = false;
    const ahorro = resumen.litros_macizo
      ? Math.round(100 * (1 - resumen.litros / resumen.litros_macizo)) : 0;
    $('r-material').textContent = resumen.litros.toFixed(1) + ' L';
    $('dato-material').title = ahorro > 0
      ? `${ahorro} % menos que macizo (${resumen.litros_macizo.toFixed(1)} L)` : '';
    $('dato-material').querySelector('span').textContent =
      ahorro > 0 ? `material · ${ahorro}% menos` : 'material';
  }
  $('capa').max = resumen.capas;
  $('btn-descargar').hidden = false;
  $('btn-descargar').href = `/api/descargar/${estado.trabajo}`;
  $('btn-guia').hidden = false;
  $('btn-guia').href = `/api/guia/${estado.trabajo}`;
  $('btn-abrir').hidden = false;
  const avisos = resumen.avisos.slice();
  if (resumen.fuera_de_capacidad.length) {
    avisos.push('No caben en la maquina: ' + resumen.fuera_de_capacidad.join(', '));
  }
  mostrarAvisos(avisos, false);
  pintarLista();
}

// ------------------------------------------------------------ lista de piezas
function pintarLista() {
  const lista = $('lista');
  const filtro = $('buscar').value.trim().toUpperCase();
  const piezas = (estado.resumen ? estado.resumen.lista : []);
  const capa = parseInt($('capa').value, 10) || 0;
  lista.innerHTML = '';
  let visibles = 0;
  piezas.forEach((p, i) => {
    if (filtro && !p.nombre.toUpperCase().includes(filtro)) return;
    if (capa && p.capa !== capa) return;
    visibles++;
    const li = document.createElement('li');
    li.dataset.nombre = p.nombre;
    li.innerHTML = `<span class="color" style="background:${colorPieza(i)}"></span>
      <span class="nombre">${escapar(p.nombre)}</span>
      ${p.avisos.length ? `<span class="marca-aviso" title="${escapar(p.avisos.join('; '))}">!</span>` : ''}
      <span class="medidas">${p.medidas.map((v) => v.toFixed(0)).join('&times;')}</span>
      <a class="bajar" title="Descargar solo esta pieza en STL" download
         href="/api/pieza/${estado.trabajo}/${encodeURIComponent(p.nombre)}">&#8595;</a>`;
    li.onclick = (ev) => {
      if (ev.target.classList.contains('bajar')) { ev.stopPropagation(); return; }
      seleccionar(p.nombre);
    };
    lista.appendChild(li);
  });
  $('contador').textContent = visibles ? `${visibles}` : '';
  $('pista-lista').hidden = visibles > 0;
}

function colorPieza(i) {
  const h = (i * 0.61803398875) % 1;
  const s = 0.55 + 0.25 * ((i % 3) / 2);
  const v = Math.min(0.75 + 0.2 * (i % 2), 1);
  const f = (n) => {
    const k = (n + h * 6) % 6;
    return Math.round((v - v * s * Math.max(Math.min(k, 4 - k, 1), 0)) * 255);
  };
  return `rgb(${f(5)},${f(3)},${f(1)})`;
}

function seleccionar(nombre) {
  visor.selected = visor.selected === nombre ? null : nombre;
  visor.render();
  document.querySelectorAll('#lista li').forEach((li) => {
    li.classList.toggle('activa', li.dataset.nombre === visor.selected);
  });
  if (visor.selected && estado.resumen) {
    const p = estado.resumen.lista.find((x) => x.nombre === visor.selected);
    if (p) {
      const vecinos = Object.entries(p.vecinos || {}).map(([k, v]) => `${v} (${k})`).join(', ');
      mostrarAvisos([`${p.nombre}: ${p.medidas.join(' x ')} mm`
        + (p.volumen_cm3 ? `, ${p.volumen_cm3} cm3` : '')
        + (vecinos ? ` · encaja con ${vecinos}` : '')].concat(p.avisos), false);
    }
  }
}

// ------------------------------------------------------------ eventos
$('archivo').addEventListener('change', (e) => cargarArchivo(e.target.files[0]));
$('archivo2').addEventListener('change', (e) => cargarArchivo(e.target.files[0]));
$('btn-cortar').addEventListener('click', cortar);
$('btn-reparar').addEventListener('click', repararEnWindows);
$('btn-encuadrar').addEventListener('click', () => visor && visor.frameAll());
$('buscar').addEventListener('input', pintarLista);
$('btn-abrir').addEventListener('click', async () => {
  try {
    const info = await (await api(`/api/abrir/${estado.trabajo}`, { method: 'POST' })).json();
    if (!info.abierto) mostrarAvisos([info.mensaje], false);
  } catch (err) { mostrarAvisos([err.message], true); }
});

$('modo').querySelectorAll('button').forEach((b) => {
  b.addEventListener('click', () => {
    $('modo').querySelectorAll('button').forEach((o) => o.classList.remove('activo'));
    b.classList.add('activo');
    $('opciones-laminas').hidden = b.dataset.valor !== 'slabs';
    actualizarPlan();
  });
});
$('hueco').addEventListener('change', () => {
  $('opciones-hueco').style.opacity = $('hueco').checked ? '1' : '0.45';
  $('opciones-hueco').style.pointerEvents = $('hueco').checked ? '' : 'none';
  actualizarPlan();
});

// ayudante: espesor de pared a partir de los perimetros del laminador
function pintarPerimetros() {
  const n = Math.max(1, Math.round(num('perimetros', 4)));
  const linea = num('linea', 0.4);
  const total = n * linea;
  $('pista-perimetros').textContent =
    `${n} perimetros de ${linea} mm = ${total.toFixed(2)} mm de pared.`;
  return total;
}
$('btn-perimetros').addEventListener('click', () => {
  $('pared').value = pintarPerimetros().toFixed(2);
  actualizarPlan();
});
['perimetros', 'linea'].forEach((id) => {
  $(id).addEventListener('input', pintarPerimetros);
});
pintarPerimetros();
$('espigas').addEventListener('change', () => {
  $('opciones-espigas').hidden = $('espigas').value === 'none';
});
$('marcas').addEventListener('change', () => {
  $('opciones-marcas').hidden = !$('marcas').checked;
});
$('explosion').addEventListener('input', (e) => {
  if (!visor) return;
  visor.explode = parseFloat(e.target.value) / 100;
  visor.render();
});
$('capa').addEventListener('input', (e) => {
  if (!visor) return;
  const v = parseInt(e.target.value, 10) || 0;
  visor.layer = v;
  $('capa-txt').textContent = v ? 'L' + String(v).padStart(2, '0') : 'todas';
  visor.frameAll();
  pintarLista();
});
$('ver-rejilla').addEventListener('change', (e) => {
  if (!visor) return;
  visor.showGrid = e.target.checked;
  visor.render();
});

['px', 'py', 'pz', 'diametro', 'pz-round', 'margen', 'espesor', 'eje',
 'estilo-lamina', 'ajuste-lamina', 'subdividir', 'kerf', 'divisiones', 'escala',
 'tamano', 'tamano-eje', 'unidades', 'motor', 'unir', 'pared', 'tapas',
 'lengueta', 'minima', 'giro-x', 'giro-y', 'giro-z', 'apoyar'].forEach((id) => {
  $(id).addEventListener('change', actualizarPlan);
  if (['number', 'text'].includes($(id).type)) $(id).addEventListener('input', actualizarPlan);
});

if (visor) {
  visor.onPick = (info) => {
    if (info) seleccionar(info.name);
    else { visor.selected = null; visor.render(); pintarLista(); }
  };
}

// atajos: maquinas, alturas y espesores habituales
function chips(contenedor, items, accion) {
  items.forEach((item) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.textContent = item.texto;
    b.onclick = () => { accion(item); actualizarPlan(); };
    $(contenedor).appendChild(b);
  });
}

/* ------------------------------------------------------- maquina */
function ponerForma(valor) {
  $('forma-cama').querySelectorAll('button').forEach((b) => {
    b.classList.toggle('activo', b.dataset.valor === valor);
  });
  $('medidas-rect').hidden = valor === 'round';
  $('medidas-round').hidden = valor !== 'round';
  pintarUtilMaquina();
}

$('forma-cama').querySelectorAll('button').forEach((b) => {
  b.addEventListener('click', () => {
    ponerForma(b.dataset.valor);
    $('perfil').value = '';
    actualizarPlan();
  });
});

let PERFILES = [];

fetch('/api/perfiles').then((r) => r.json()).then((d) => {
  PERFILES = d.perfiles || [];
  const sel = $('perfil');
  PERFILES.forEach((p) => {
    const o = document.createElement('option');
    o.value = p.id;
    o.textContent = p.nombre;
    sel.appendChild(o);
  });
}).catch(() => { /* sin perfiles, se configura a mano */ });

$('perfil').addEventListener('change', () => {
  const p = PERFILES.find((x) => x.id === $('perfil').value);
  if (!p) { $('nota-perfil').textContent = 'Pon las medidas de tu maquina a mano.'; return; }
  const m = p.printer;
  if (m.shape === 'round') {
    ponerForma('round');
    $('diametro').value = m.diameter;
    $('pz-round').value = m.z;
  } else {
    ponerForma('rect');
    $('px').value = m.x; $('py').value = m.y; $('pz').value = m.z;
  }
  $('margen').value = m.clearance;
  $('boquilla').value = String(m.nozzle);
  $('tecnologia').value = m.technology === 'resina' ? 'resina' : 'fdm';
  $('pared').value = p.wall;
  $('kerf').value = p.kerf;
  $('minima').value = p.min_piece;
  $('linea').value = p.linea;
  $('perimetros').value = Math.max(1, Math.round(p.wall / p.linea));
  $('nota-perfil').textContent = p.nota || '';
  pintarUtilMaquina();
  actualizarPlan();
});

/* la boquilla manda sobre el espesor de la piel: la pared tiene que ser un
   multiplo exacto del ancho de linea o el laminador deja huecos */
$('boquilla').addEventListener('change', () => {
  const linea = anchoLinea();
  $('linea').value = linea;
  const perimetros = Math.max(1, Math.round(num('pared', 3) / linea));
  $('perimetros').value = perimetros;
  $('pared').value = (perimetros * linea).toFixed(2);
  $('perfil').value = '';
  pintarUtilMaquina();
  actualizarPlan();
});

$('tecnologia').addEventListener('change', () => {
  const resina = $('tecnologia').value === 'resina';
  // en resina no hay boquilla ni perimetros: manda la rigidez de la pieza
  $('boquilla').disabled = resina;
  if (resina) {
    $('pared').value = 2.1;
    $('kerf').value = 0.05;
    $('minima').value = 2;
  }
  actualizarPlan();
});

chips('giros', [
  { texto: '90 en X', eje: 'giro-x', v: 90 },
  { texto: '-90 en X', eje: 'giro-x', v: -90 },
  { texto: '90 en Y', eje: 'giro-y', v: 90 },
  { texto: '90 en Z', eje: 'giro-z', v: 90 },
  { texto: 'sin giro', eje: null, v: 0 },
], (i) => {
  if (!i.eje) {
    $('giro-x').value = 0; $('giro-y').value = 0; $('giro-z').value = 0;
    return;
  }
  const actual = num(i.eje, 0);
  $(i.eje).value = ((actual + i.v) % 360 + 360) % 360;
});

chips('alturas', [
  { texto: '30 cm', v: 300 }, { texto: '50 cm', v: 500 }, { texto: '1 m', v: 1000 },
  { texto: '1,5 m', v: 1500 }, { texto: '1,8 m', v: 1800 }, { texto: '2 m', v: 2000 },
  { texto: 'original', v: '' },
], (i) => { $('tamano').value = i.v; });

chips('paredes', [
  { texto: '1,5 mm', v: 1.5 }, { texto: '2 mm', v: 2 }, { texto: '3 mm', v: 3 },
  { texto: '5 mm', v: 5 }, { texto: '8 mm', v: 8 },
], (i) => { $('pared').value = i.v; });

chips('espesores', [
  { texto: '3 mm', v: 3 }, { texto: '5 mm', v: 5 }, { texto: '10 mm', v: 10 },
  { texto: '15 mm', v: 15 }, { texto: '18 mm', v: 18 }, { texto: '25 mm', v: 25 },
], (i) => { $('espesor').value = i.v; });

// arrastrar y soltar
const lienzo = document.querySelector('.lienzo');
['dragenter', 'dragover'].forEach((ev) => lienzo.addEventListener(ev, (e) => {
  e.preventDefault(); lienzo.classList.add('arrastrando');
}));
['dragleave', 'drop'].forEach((ev) => lienzo.addEventListener(ev, (e) => {
  e.preventDefault(); lienzo.classList.remove('arrastrando');
}));
lienzo.addEventListener('drop', (e) => cargarArchivo(e.dataTransfer.files[0]));

['px', 'py', 'pz', 'diametro', 'pz-round', 'margen'].forEach((id) => {
  $(id).addEventListener('input', pintarUtilMaquina);
});
pintarUtilMaquina();

fetch('/api/version').then((r) => r.json())
  .then((d) => { $('version').textContent = 'v' + d.version; })
  .catch(() => { /* sin version, da igual */ });

/* ------------------------------------------------------------- propina
   Solo aparece si el proyecto tiene canales configurados: si no hay
   ninguno, aqui no se ve nada y nadie tiene que cerrar ningun aviso. */
fetch('/api/apoyo').then((r) => r.json())
  .then((d) => {
    if (!d.hay) return;
    const boton = $('btn-apoyo');
    const lista = $('apoyo-lista');
    $('apoyo-mensaje').textContent = d.mensaje;
    lista.innerHTML = '';
    d.canales.forEach((canal) => {
      const li = document.createElement('li');
      const info = document.createElement('div');
      const titulo = document.createElement('b');
      titulo.textContent = canal.nombre;
      info.appendChild(titulo);
      const detalle = document.createElement('span');
      detalle.textContent = canal.tipo === 'copiar'
        ? canal.valor + (canal.nota ? ' · ' + canal.nota : '')
        : (canal.nota || canal.valor);
      info.appendChild(detalle);
      li.appendChild(info);

      if (canal.tipo === 'enlace') {
        const a = document.createElement('a');
        a.className = 'boton pequeno';
        a.href = canal.valor;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.textContent = 'Abrir';
        li.appendChild(a);
      } else {
        const b = document.createElement('button');
        b.className = 'boton pequeno';
        b.type = 'button';
        b.textContent = 'Copiar';
        b.addEventListener('click', () => {
          navigator.clipboard.writeText(canal.valor)
            .then(() => { b.textContent = 'Copiado'; })
            .catch(() => { b.textContent = canal.valor; });
        });
        li.appendChild(b);
      }
      lista.appendChild(li);
    });
    boton.hidden = false;
    boton.addEventListener('click', () => $('dlg-apoyo').showModal());
  })
  .catch(() => { /* sin propina, la app funciona igual */ });
