/*
 * Visor 3D minimo en WebGL, sin librerias externas.
 * Dibuja las piezas con color propio, permite orbitar, separar el despiece
 * (vista explosionada), filtrar por capa y seleccionar piezas con el raton.
 */

// ---------------------------------------------------------------- matematicas
function mat4() { return new Float32Array(16); }

function identity(out) {
  out.set([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
  return out;
}

function perspective(out, fovy, aspect, near, far) {
  const f = 1.0 / Math.tan(fovy / 2), nf = 1 / (near - far);
  out.set([f / aspect, 0, 0, 0, 0, f, 0, 0, 0, 0, (far + near) * nf, -1,
           0, 0, 2 * far * near * nf, 0]);
  return out;
}

function lookAt(out, eye, center, up) {
  let z0 = eye[0] - center[0], z1 = eye[1] - center[1], z2 = eye[2] - center[2];
  let len = Math.hypot(z0, z1, z2) || 1;
  z0 /= len; z1 /= len; z2 /= len;
  let x0 = up[1] * z2 - up[2] * z1, x1 = up[2] * z0 - up[0] * z2, x2 = up[0] * z1 - up[1] * z0;
  len = Math.hypot(x0, x1, x2);
  if (!len) { x0 = 1; x1 = 0; x2 = 0; } else { x0 /= len; x1 /= len; x2 /= len; }
  const y0 = z1 * x2 - z2 * x1, y1 = z2 * x0 - z0 * x2, y2 = z0 * x1 - z1 * x0;
  out.set([x0, y0, z0, 0, x1, y1, z1, 0, x2, y2, z2, 0,
           -(x0 * eye[0] + x1 * eye[1] + x2 * eye[2]),
           -(y0 * eye[0] + y1 * eye[1] + y2 * eye[2]),
           -(z0 * eye[0] + z1 * eye[1] + z2 * eye[2]), 1]);
  return out;
}

function multiply(out, a, b) {
  for (let i = 0; i < 4; i++) {
    const b0 = b[i * 4], b1 = b[i * 4 + 1], b2 = b[i * 4 + 2], b3 = b[i * 4 + 3];
    out[i * 4] = b0 * a[0] + b1 * a[4] + b2 * a[8] + b3 * a[12];
    out[i * 4 + 1] = b0 * a[1] + b1 * a[5] + b2 * a[9] + b3 * a[13];
    out[i * 4 + 2] = b0 * a[2] + b1 * a[6] + b2 * a[10] + b3 * a[14];
    out[i * 4 + 3] = b0 * a[3] + b1 * a[7] + b2 * a[11] + b3 * a[15];
  }
  return out;
}

// ---------------------------------------------------------------- shaders
const VERT = `
attribute vec3 aPos;
attribute vec3 aNormal;
uniform mat4 uMVP;
uniform vec3 uOffset;
varying vec3 vNormal;
varying float vDepth;
void main() {
  vNormal = aNormal;
  vec4 p = uMVP * vec4(aPos + uOffset, 1.0);
  vDepth = p.z / p.w;
  gl_Position = p;
}`;

const FRAG = `
precision mediump float;
uniform vec3 uColor;
uniform float uGhost;
uniform mat3 uNormalView;   // rotacion de la camara, para el matcap
uniform sampler2D uMatcap;
uniform float uMatcapMix;   // 0 = luces calculadas, 1 = matcap
varying vec3 vNormal;
void main() {
  vec3 n = normalize(vNormal);

  // luces de toda la vida, que es lo que se ve si no hay textura
  vec3 key = normalize(vec3(0.45, -0.7, 0.85));
  vec3 fill = normalize(vec3(-0.6, 0.3, 0.2));
  float d = max(dot(n, key), 0.0) * 0.72 + max(dot(n, fill), 0.0) * 0.22;
  float sky = 0.28 + 0.22 * (n.z * 0.5 + 0.5);
  vec3 col = uColor * (d + sky);

  if (uMatcapMix > 0.001) {
    // matcap: la normal en coordenadas de camara elige el punto de la esfera
    vec3 nv = normalize(uNormalView * n);
    vec2 uv = nv.xy * 0.5 + 0.5;
    vec3 m = texture2D(uMatcap, uv).rgb;
    float lum = dot(m, vec3(0.299, 0.587, 0.114));
    vec3 conMatcap = uColor * (0.46 + 1.25 * lum) + m * 0.28;
    col = mix(col, conMatcap, uMatcapMix);
  }

  col = pow(col, vec3(0.85));
  gl_FragColor = vec4(col, uGhost);
}`;

const LINE_VERT = `
attribute vec3 aPos;
uniform mat4 uMVP;
void main() { gl_Position = uMVP * vec4(aPos, 1.0); }`;

const LINE_FRAG = `
precision mediump float;
uniform vec4 uColor;
void main() { gl_FragColor = uColor; }`;

const PICK_FRAG = `
precision mediump float;
uniform vec3 uColor;
void main() { gl_FragColor = vec4(uColor, 1.0); }`;

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) || 'shader');
  }
  return shader;
}

function program(gl, vs, fs) {
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl, gl.VERTEX_SHADER, vs));
  gl.attachShader(p, compile(gl, gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(p) || 'program');
  }
  return p;
}

// ---------------------------------------------------------------- visor
export class Viewer {
  constructor(canvas) {
    this.canvas = canvas;
    const opts = { antialias: true, alpha: false, preserveDrawingBuffer: false };
    this.gl = canvas.getContext('webgl', opts) || canvas.getContext('experimental-webgl', opts);
    if (!this.gl) throw new Error('Este navegador no soporta WebGL');
    const gl = this.gl;
    this.prog = program(gl, VERT, FRAG);
    this.lineProg = program(gl, LINE_VERT, LINE_FRAG);
    this.pickProg = program(gl, VERT, PICK_FRAG);
    this.pieces = [];
    this.lines = null;
    this.explode = 0;
    this.layer = 0;          // 0 = todas
    this.selected = null;
    this.showGrid = true;
    this.center = [0, 0, 0];
    this.radius = 100;
    this.theta = -Math.PI / 4;
    this.phi = Math.PI / 2.6;
    this.distance = 400;
    this.pan = [0, 0, 0];
    this.background = [0.055, 0.063, 0.078];
    this.lineColor = [0.45, 0.85, 1.0, 1.0];
    this.matcapMix = 0;
    this.matcap = this._texturaLisa();
    this._setupInput();
    this._resize();
    this.render();
  }

  // ---- material ---------------------------------------------------
  _texturaLisa() {
    // un pixel gris: lo que se usa mientras no haya matcap cargado
    const gl = this.gl;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, 1, 1, 0, gl.RGB, gl.UNSIGNED_BYTE,
                  new Uint8Array([160, 160, 160]));
    return tex;
  }

  /* Carga la esfera de material (matcap). Si no llega, no pasa nada: se
     siguen usando las luces calculadas de siempre. */
  setMatcap(url) {
    const gl = this.gl;
    const img = new Image();
    img.onload = () => {
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
      this.matcap = tex;
      this.matcapMix = 1;
      this.render();
    };
    img.onerror = () => { /* sin matcap, el visor funciona igual */ };
    img.src = url;
  }

  // ---- datos ------------------------------------------------------
  setPayload(buffer) {
    const gl = this.gl;
    this.clear();
    const view = new DataView(buffer);
    const headerLength = view.getUint32(0, true);
    const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 4, headerLength)));
    const floats = new Float32Array(buffer, 4 + headerLength);
    this.bounds = header.bounds;
    const bmin = header.bounds[0], bmax = header.bounds[1];
    this.center = [(bmin[0] + bmax[0]) / 2, (bmin[1] + bmax[1]) / 2, (bmin[2] + bmax[2]) / 2];
    this.radius = Math.max(
      Math.hypot(bmax[0] - bmin[0], bmax[1] - bmin[1], bmax[2] - bmin[2]) / 2, 1);

    header.pieces.forEach((info, i) => {
      const start = info.offset * 3;
      const count = info.count * 3;
      const positions = floats.subarray(start, start + count);
      const normals = flatNormals(positions);
      const posBuf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
      gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
      const normBuf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, normBuf);
      gl.bufferData(gl.ARRAY_BUFFER, normals, gl.STATIC_DRAW);
      const dir = [info.center[0] - this.center[0], info.center[1] - this.center[1],
                   info.center[2] - this.center[2]];
      this.pieces.push({
        info, posBuf, normBuf, vertices: info.count,
        color: info.color.map((c) => c / 255),
        dir, id: i + 1,
      });
    });
    return header;
  }

  setGrid(edges) {
    const gl = this.gl;
    if (this.lines) { gl.deleteBuffer(this.lines.buffer); this.lines = null; }
    if (!edges || !this.bounds) return;
    const [lo, hi] = this.bounds;
    const pts = [];
    const seg = (a, b) => { pts.push(a[0], a[1], a[2], b[0], b[1], b[2]); };
    for (let axis = 0; axis < 3; axis++) {
      const u = (axis + 1) % 3, v = (axis + 2) % 3;
      const total = Math.max((edges[axis] || []).length - 2, 0);
      // con cientos de laminas la rejilla tapa el modelo: dibujamos una de cada N
      const paso = Math.max(1, Math.ceil(total / 40));
      (edges[axis] || []).forEach((value, i, arr) => {
        if (i === 0 || i === arr.length - 1) return;   // los extremos son el contorno
        if ((i - 1) % paso !== 0) return;
        const corners = [[lo[u], lo[v]], [hi[u], lo[v]], [hi[u], hi[v]], [lo[u], hi[v]]];
        for (let c = 0; c < 4; c++) {
          const a = [0, 0, 0], b = [0, 0, 0];
          a[axis] = value; b[axis] = value;
          a[u] = corners[c][0]; a[v] = corners[c][1];
          b[u] = corners[(c + 1) % 4][0]; b[v] = corners[(c + 1) % 4][1];
          seg(a, b);
        }
      });
    }
    // caja envolvente
    const corners = [[lo[0], lo[1], lo[2]], [hi[0], lo[1], lo[2]], [hi[0], hi[1], lo[2]],
                     [lo[0], hi[1], lo[2]], [lo[0], lo[1], hi[2]], [hi[0], lo[1], hi[2]],
                     [hi[0], hi[1], hi[2]], [lo[0], hi[1], hi[2]]];
    [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4],
     [0, 4], [1, 5], [2, 6], [3, 7]].forEach(([a, b]) => seg(corners[a], corners[b]));
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(pts), gl.STATIC_DRAW);
    this.lines = { buffer, count: pts.length / 3 };
  }

  clear() {
    const gl = this.gl;
    this.pieces.forEach((p) => { gl.deleteBuffer(p.posBuf); gl.deleteBuffer(p.normBuf); });
    this.pieces = [];
    this.selected = null;
  }

  // ---- camara -----------------------------------------------------
  frameAll() {
    this.pan = [0, 0, 0];
    this._centerOn(this.pieces.filter((p) => this._visible(p)));
    this.distance = this._fitDistance();
    this.render();
  }

  _centerOn(piezas) {
    // encuadra solo lo que esta a la vista (util al aislar una capa)
    const cajas = piezas.map((p) => p.info.bounds).filter(Boolean);
    if (!cajas.length) return;
    const lo = [Infinity, Infinity, Infinity];
    const hi = [-Infinity, -Infinity, -Infinity];
    for (const [a, b] of cajas) {
      for (let i = 0; i < 3; i++) {
        lo[i] = Math.min(lo[i], a[i]);
        hi[i] = Math.max(hi[i], b[i]);
      }
    }
    this.center = [0, 1, 2].map((i) => (lo[i] + hi[i]) / 2);
    this.radius = Math.max(
      Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2, 1);
  }

  _fitDistance() {
    // distancia a la que la esfera envolvente entra entera, tambien cuando la
    // ventana es mas ancha que alta y cuando el despiece esta separado
    const fov = Math.PI / 4;
    const aspect = Math.max(this.canvas.width / Math.max(this.canvas.height, 1), 0.2);
    const vertical = this.radius / Math.sin(fov / 2);
    const horizontal = this.radius / Math.sin(Math.atan(Math.tan(fov / 2) * aspect));
    return Math.max(vertical, horizontal) * 1.25 * (1 + this.explode * 0.45);
  }

  _eye() {
    const sp = Math.sin(this.phi), cp = Math.cos(this.phi);
    const target = [this.center[0] + this.pan[0], this.center[1] + this.pan[1],
                    this.center[2] + this.pan[2]];
    return {
      target,
      eye: [target[0] + this.distance * sp * Math.cos(this.theta),
            target[1] + this.distance * sp * Math.sin(this.theta),
            target[2] + this.distance * cp],
    };
  }

  // ---- interaccion ------------------------------------------------
  _setupInput() {
    const c = this.canvas;
    let dragging = null, lastX = 0, lastY = 0, moved = 0;
    const down = (e) => {
      dragging = (e.button === 2 || e.shiftKey) ? 'pan' : 'orbit';
      lastX = e.clientX; lastY = e.clientY; moved = 0;
      c.setPointerCapture?.(e.pointerId);
    };
    const move = (e) => {
      if (!dragging) return;
      const dx = e.clientX - lastX, dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      moved += Math.abs(dx) + Math.abs(dy);
      if (dragging === 'orbit') {
        this.theta -= dx * 0.008;
        this.phi = Math.min(Math.PI - 0.02, Math.max(0.02, this.phi - dy * 0.008));
      } else {
        const k = this.distance * 0.0016;
        const right = [-Math.sin(this.theta), Math.cos(this.theta), 0];
        const upv = [-Math.cos(this.theta) * Math.cos(this.phi),
                     -Math.sin(this.theta) * Math.cos(this.phi), Math.sin(this.phi)];
        for (let i = 0; i < 3; i++) this.pan[i] += (-right[i] * dx + upv[i] * dy) * k;
      }
      this.render();
    };
    const up = (e) => {
      if (dragging && moved < 4 && this.onPick) {
        const hit = this.pick(e.offsetX, e.offsetY);
        this.onPick(hit);
      }
      dragging = null;
    };
    c.addEventListener('pointerdown', down);
    c.addEventListener('pointermove', move);
    c.addEventListener('pointerup', up);
    c.addEventListener('pointerleave', () => { dragging = null; });
    c.addEventListener('contextmenu', (e) => e.preventDefault());
    c.addEventListener('wheel', (e) => {
      e.preventDefault();
      this.distance *= Math.exp(Math.sign(e.deltaY) * 0.12);
      this.distance = Math.max(this.radius * 0.15, Math.min(this.radius * 40, this.distance));
      this.render();
    }, { passive: false });

    let pinch = 0;
    c.addEventListener('touchmove', (e) => {
      if (e.touches.length !== 2) return;
      e.preventDefault();
      const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX,
                           e.touches[0].clientY - e.touches[1].clientY);
      if (pinch) {
        this.distance *= pinch / d;
        this.distance = Math.max(this.radius * 0.15, Math.min(this.radius * 40, this.distance));
        this.render();
      }
      pinch = d;
    }, { passive: false });
    c.addEventListener('touchend', () => { pinch = 0; });
    window.addEventListener('resize', () => { this._resize(); this.render(); });
  }

  _resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.floor(this.canvas.clientWidth * dpr));
    const h = Math.max(1, Math.floor(this.canvas.clientHeight * dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w; this.canvas.height = h;
    }
  }

  _visible(piece) {
    if (this.layer && piece.info.layer !== this.layer) return false;
    return true;
  }

  _offset(piece) {
    const f = this.explode;
    if (!f) return [0, 0, 0];
    return [piece.dir[0] * f, piece.dir[1] * f, piece.dir[2] * f];
  }

  // ---- dibujado ---------------------------------------------------
  render() {
    const gl = this.gl;
    this._resize();
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(this.background[0], this.background[1], this.background[2], 1);
    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.CULL_FACE);
    gl.cullFace(gl.BACK);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    const { eye, target } = this._eye();
    const proj = perspective(mat4(), Math.PI / 4,
                             this.canvas.width / this.canvas.height,
                             Math.max(this.radius * 0.01, 0.1), this.radius * 60);
    const view = lookAt(mat4(), eye, target, [0, 0, 1]);
    const mvp = multiply(mat4(), proj, view);

    gl.useProgram(this.prog);
    const uMVP = gl.getUniformLocation(this.prog, 'uMVP');
    const uColor = gl.getUniformLocation(this.prog, 'uColor');
    const uOffset = gl.getUniformLocation(this.prog, 'uOffset');
    const uGhost = gl.getUniformLocation(this.prog, 'uGhost');
    const aPos = gl.getAttribLocation(this.prog, 'aPos');
    const aNormal = gl.getAttribLocation(this.prog, 'aNormal');
    gl.uniformMatrix4fv(uMVP, false, mvp);

    // el matcap necesita la normal vista desde la camara: basta la parte de
    // rotacion de la matriz de vista, porque el modelo no se rota
    const rot = new Float32Array([view[0], view[1], view[2],
                                  view[4], view[5], view[6],
                                  view[8], view[9], view[10]]);
    gl.uniformMatrix3fv(gl.getUniformLocation(this.prog, 'uNormalView'), false, rot);
    gl.uniform1f(gl.getUniformLocation(this.prog, 'uMatcapMix'), this.matcapMix);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.matcap);
    gl.uniform1i(gl.getUniformLocation(this.prog, 'uMatcap'), 0);

    gl.enableVertexAttribArray(aPos);
    gl.enableVertexAttribArray(aNormal);

    for (const piece of this.pieces) {
      if (!this._visible(piece)) continue;
      let color = piece.color;
      if (this.selected && piece.info.name === this.selected) color = [1, 1, 1];
      gl.uniform3fv(uColor, color);
      gl.uniform3fv(uOffset, this._offset(piece));
      gl.uniform1f(uGhost, 1.0);
      gl.bindBuffer(gl.ARRAY_BUFFER, piece.posBuf);
      gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, piece.normBuf);
      gl.vertexAttribPointer(aNormal, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, piece.vertices * 3);
    }

    if (this.lines && this.showGrid) {
      gl.useProgram(this.lineProg);
      gl.uniformMatrix4fv(gl.getUniformLocation(this.lineProg, 'uMVP'), false, mvp);
      gl.uniform4fv(gl.getUniformLocation(this.lineProg, 'uColor'),
                    new Float32Array(this.lineColor));
      const la = gl.getAttribLocation(this.lineProg, 'aPos');
      gl.enableVertexAttribArray(la);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.lines.buffer);
      gl.vertexAttribPointer(la, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.LINES, 0, this.lines.count);
    }
  }

  // ---- seleccion con el raton -------------------------------------
  pick(x, y) {
    const gl = this.gl;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const px = Math.floor(x * dpr), py = Math.floor(this.canvas.height - y * dpr);
    if (!this._pickFbo || this._pickSize[0] !== this.canvas.width
        || this._pickSize[1] !== this.canvas.height) {
      this._createPickTarget();
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, this._pickFbo);
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0, 0, 0, 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
    gl.enable(gl.DEPTH_TEST);

    const { eye, target } = this._eye();
    const proj = perspective(mat4(), Math.PI / 4,
                             this.canvas.width / this.canvas.height,
                             Math.max(this.radius * 0.01, 0.1), this.radius * 60);
    const mvp = multiply(mat4(), proj, lookAt(mat4(), eye, target, [0, 0, 1]));
    gl.useProgram(this.pickProg);
    gl.uniformMatrix4fv(gl.getUniformLocation(this.pickProg, 'uMVP'), false, mvp);
    const uColor = gl.getUniformLocation(this.pickProg, 'uColor');
    const uOffset = gl.getUniformLocation(this.pickProg, 'uOffset');
    const aPos = gl.getAttribLocation(this.pickProg, 'aPos');
    const aNormal = gl.getAttribLocation(this.pickProg, 'aNormal');
    gl.enableVertexAttribArray(aPos);
    gl.enableVertexAttribArray(aNormal);
    for (const piece of this.pieces) {
      if (!this._visible(piece)) continue;
      const id = piece.id;
      gl.uniform3f(uColor, ((id >> 16) & 255) / 255, ((id >> 8) & 255) / 255, (id & 255) / 255);
      gl.uniform3fv(uOffset, this._offset(piece));
      gl.bindBuffer(gl.ARRAY_BUFFER, piece.posBuf);
      gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, piece.normBuf);
      gl.vertexAttribPointer(aNormal, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, piece.vertices * 3);
    }
    const data = new Uint8Array(4);
    gl.readPixels(px, py, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, data);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    this.render();
    const id = (data[0] << 16) | (data[1] << 8) | data[2];
    const hit = this.pieces.find((p) => p.id === id);
    return hit ? hit.info : null;
  }

  _createPickTarget() {
    const gl = this.gl;
    if (this._pickFbo) {
      gl.deleteFramebuffer(this._pickFbo);
      gl.deleteTexture(this._pickTex);
      gl.deleteRenderbuffer(this._pickDepth);
    }
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, this.canvas.width, this.canvas.height, 0,
                  gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    const depth = gl.createRenderbuffer();
    gl.bindRenderbuffer(gl.RENDERBUFFER, depth);
    gl.renderbufferStorage(gl.RENDERBUFFER, gl.DEPTH_COMPONENT16,
                           this.canvas.width, this.canvas.height);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    gl.framebufferRenderbuffer(gl.FRAMEBUFFER, gl.DEPTH_ATTACHMENT, gl.RENDERBUFFER, depth);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    this._pickFbo = fbo;
    this._pickTex = tex;
    this._pickDepth = depth;
    this._pickSize = [this.canvas.width, this.canvas.height];
  }
}

function flatNormals(positions) {
  const out = new Float32Array(positions.length);
  for (let i = 0; i < positions.length; i += 9) {
    const ax = positions[i], ay = positions[i + 1], az = positions[i + 2];
    const bx = positions[i + 3], by = positions[i + 4], bz = positions[i + 5];
    const cx = positions[i + 6], cy = positions[i + 7], cz = positions[i + 8];
    const e1x = bx - ax, e1y = by - ay, e1z = bz - az;
    const e2x = cx - ax, e2y = cy - ay, e2z = cz - az;
    let nx = e1y * e2z - e1z * e2y;
    let ny = e1z * e2x - e1x * e2z;
    let nz = e1x * e2y - e1y * e2x;
    const len = Math.hypot(nx, ny, nz) || 1;
    nx /= len; ny /= len; nz /= len;
    for (let k = 0; k < 3; k++) {
      out[i + k * 3] = nx; out[i + k * 3 + 1] = ny; out[i + k * 3 + 2] = nz;
    }
  }
  return out;
}
