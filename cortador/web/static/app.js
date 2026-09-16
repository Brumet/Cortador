/* Logica del panel: formulario -> API -> visor 3D. */
import { Viewer } from '/static/viewer.js';

const $ = (id) => document.getElementById(id);
const estado = {
  trabajo: null,
  factor: 1,
  plan: null,
  resumen: null,
  fuente: 'original',   // que se esta viendo: original | piezas
};

let visor = null;
try {
  visor = new Viewer($('vista'));
} catch (err) {
  $('vacio').innerHTML = `<h1>WebGL no disponible</h1><p>${err.message}</p>
    <p class="tenue">Puedes seguir usando Cortador desde la terminal: <code>cortador cortar modelo.stl</code></p>`;
}

// ------------------------------------------------------------ utilidades
function leerConfig() {
  const divisiones = $('divisiones').value.trim();
  let div = null;
  if (divisiones) {
    const partes = divisiones.toLowerCase().replace(/\*/g, 'x').split('x');
    if (partes.length === 3) {
      div = partes.map((p) => (p.trim() === '' || p.trim() === '-' || p.trim() === 'auto'
        ? null : Math.max(1, parseInt(p, 10) || 1)));
    }
  }
  return {
    printer: {
      x: num('px', 220), y: num('py', 220), z: num('pz', 250),
      clearance: num('margen', 0),
    },
    mode: modoActual(),
    slab_thickness: num('espesor', 5),
    slab_axis: $('eje').value,
    slab_style: $('estilo-lamina').value,
    slab_fit: $('ajuste-lamina').value,
    split_slabs_to_fit: $('subdividir').checked,
    divisions: div,
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
    },
  };
}

function num(id, def) {
  const v = parseFloat($(id).value);
  return Number.isFinite(v) ? v : def;
}

function modoActual() {
  return $('modo').querySelector('.activo').dataset.valor;
}

function mostrarAvisos(lista, esError) {
  const caja = $('avisos');
  if (!lista || !lista.length) { caja.hidden = true; return; }
  caja.hidden = false;
  caja.className = 'aviso' + (esError ? ' error' : '');
  caja.innerHTML = `<b>${esError ? 'Error' : 'Avisos'}</b><ul>${
    lista.map((t) => `<li>${escapar(t)}</li>`).join('')}</ul>`;
}

function escapar(t) {
  return String(t).replace(/[<>&]/g, (c) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' }[c]));
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

// ------------------------------------------------------------ carga del modelo
async function cargarArchivo(file) {
  if (!file) return;
  $('nombre-archivo').textContent = 'cargando ' + file.name + '...';
  const datos = new FormData();
  datos.append('archivo', file);
  try {
    const res = await api('/api/modelo', { method: 'POST', body: datos });
    const info = await res.json();
    estado.trabajo = info.trabajo;
    estado.fuente = 'original';
    $('nombre-archivo').textContent = `${info.archivo} - ${info.modelo.triangles.toLocaleString('es')} triangulos`;
    $('btn-cortar').disabled = false;
    $('btn-descargar').hidden = true;
    $('btn-guia').hidden = true;
    $('vacio').hidden = true;
    mostrarAvisos(info.modelo.watertight ? [] : [
      'La malla no es estanca (tiene agujeros). Cortador intentara repararla, '
      + 'pero si el resultado sale raro conviene arreglarla antes.'], false);
    await verOriginal();
    actualizarPlan();
  } catch (err) {
    $('nombre-archivo').textContent = 'ningun modelo cargado';
    mostrarAvisos([err.message], true);
  }
}

async function verOriginal() {
  const res = await api(`/api/vista/${estado.trabajo}?fuente=original`);
  const buffer = await res.arrayBuffer();
  visor.setPayload(buffer);
  visor.frameAll();
  estado.fuente = 'original';
  pintarRejilla();
  $('r-piezas').textContent = '-';
  visor.render();
}

// ------------------------------------------------------------ plan
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
      mostrarAvisos(plan.warnings, false);
      pintarRejilla();
    } catch (err) {
      mostrarAvisos([err.message], true);
    }
  }, 180);
}

function pintarRejilla() {
  if (!visor || !estado.plan) return;
  const f = estado.fuente === 'original' ? (estado.factor || 1) : 1;
  const bordes = estado.plan.edges.map((eje) => eje.map((v) => v / f));
  visor.setGrid(bordes);
  visor.render();
}

// ------------------------------------------------------------ corte
async function cortar() {
  if (!estado.trabajo) return;
  $('btn-cortar').disabled = true;
  $('cargando').hidden = false;
  $('progreso').style.width = '0%';
  $('progreso-txt').textContent = 'Preparando...';
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
    $('btn-cortar').disabled = false;
  }
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
    const pct = Math.round(100 * info.hecho / Math.max(info.total, 1));
    $('progreso').style.width = pct + '%';
    $('progreso-txt').textContent = `${info.mensaje || 'Cortando'} ${info.hecho}/${info.total}`;
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
  $('cargando').hidden = true;
  $('btn-cortar').disabled = false;
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
  $('capa').max = resumen.capas;
  $('btn-descargar').hidden = false;
  $('btn-descargar').href = `/api/descargar/${estado.trabajo}`;
  $('btn-guia').hidden = false;
  $('btn-guia').href = `/api/guia/${estado.trabajo}`;
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
    const color = colorPieza(i);
    li.innerHTML = `<span class="color" style="background:${color}"></span>
      <span class="nombre">${escapar(p.nombre)}</span>
      ${p.avisos.length ? '<span class="marca-aviso" title="' + escapar(p.avisos.join('; ')) + '">!</span>' : ''}
      <span class="medidas">${p.medidas.map((v) => v.toFixed(0)).join('x')}</span>`;
    li.onclick = () => seleccionar(p.nombre);
    lista.appendChild(li);
  });
  $('contador').textContent = visibles ? `${visibles} pieza(s)` : '';
}

function colorPieza(i) {
  const h = (i * 0.61803398875) % 1;
  const s = 0.55 + 0.25 * ((i % 3) / 2);
  const v = Math.min(0.75 + 0.2 * (i % 2), 1);
  const f = (n) => {
    const k = (n + h * 6) % 6;
    const c = v - v * s * Math.max(Math.min(k, 4 - k, 1), 0);
    return Math.round(c * 255);
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
        + (vecinos ? ` - encaja con ${vecinos}` : '')].concat(p.avisos), false);
    }
  }
}

// ------------------------------------------------------------ eventos
$('archivo').addEventListener('change', (e) => cargarArchivo(e.target.files[0]));
$('btn-cortar').addEventListener('click', cortar);
$('btn-encuadrar').addEventListener('click', () => visor && visor.frameAll());
$('buscar').addEventListener('input', pintarLista);

$('modo').querySelectorAll('button').forEach((b) => {
  b.addEventListener('click', () => {
    $('modo').querySelectorAll('button').forEach((o) => o.classList.remove('activo'));
    b.classList.add('activo');
    $('opciones-laminas').hidden = b.dataset.valor !== 'slabs';
    actualizarPlan();
  });
});

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
  visor.render();
  pintarLista();
});
$('ver-rejilla').addEventListener('change', (e) => {
  if (!visor) return;
  visor.showGrid = e.target.checked;
  visor.render();
});

['px', 'py', 'pz', 'margen', 'espesor', 'eje', 'estilo-lamina', 'ajuste-lamina',
 'subdividir', 'kerf', 'divisiones', 'escala', 'tamano', 'tamano-eje', 'unidades',
 'motor', 'unir'].forEach((id) => {
  $(id).addEventListener('change', actualizarPlan);
  if ($(id).type === 'number' || $(id).type === 'text') {
    $(id).addEventListener('input', actualizarPlan);
  }
});

if (visor) {
  visor.onPick = (info) => {
    if (info) seleccionar(info.name);
    else { visor.selected = null; visor.render(); pintarLista(); }
  };
}

// atajos rapidos de maquina y espesor
const MAQUINAS = [
  ['Ender 3', 220, 220, 250], ['Bambu X1', 256, 256, 256],
  ['Prusa MK4', 250, 210, 220], ['Neptune 4 Max', 420, 420, 480],
  ['Modix 180X', 1800, 600, 600],
];
MAQUINAS.forEach(([nombre, x, y, z]) => {
  const b = document.createElement('button');
  b.textContent = nombre;
  b.onclick = () => { $('px').value = x; $('py').value = y; $('pz').value = z; actualizarPlan(); };
  $('presets').appendChild(b);
});
[3, 5, 10, 18, 25].forEach((mm) => {
  const b = document.createElement('button');
  b.textContent = mm + ' mm';
  b.onclick = () => { $('espesor').value = mm; actualizarPlan(); };
  $('espesores').appendChild(b);
});

// arrastrar y soltar
const lienzo = document.querySelector('.lienzo');
['dragenter', 'dragover'].forEach((ev) => lienzo.addEventListener(ev, (e) => {
  e.preventDefault(); lienzo.classList.add('arrastrando');
}));
['dragleave', 'drop'].forEach((ev) => lienzo.addEventListener(ev, (e) => {
  e.preventDefault(); lienzo.classList.remove('arrastrando');
}));
lienzo.addEventListener('drop', (e) => cargarArchivo(e.dataTransfer.files[0]));
