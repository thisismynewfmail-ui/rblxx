// WebGL context bootstrap + a thin instanced-drawing layer.
// Targets WebGL2, transparently falls back to WebGL1 + ANGLE_instanced_arrays.

export function createContext(canvas, opts = {}) {
  const attrs = {
    alpha: false, antialias: opts.antialias !== false, depth: true,
    stencil: false, powerPreference: 'high-performance',
    preserveDrawingBuffer: false, desynchronized: true,
  };
  let gl = canvas.getContext('webgl2', attrs);
  let isGL2 = !!gl;
  let angle = null;
  if (!gl) {
    gl = canvas.getContext('webgl', attrs) || canvas.getContext('experimental-webgl', attrs);
    if (!gl) return null;
    angle = gl.getExtension('ANGLE_instanced_arrays');
    if (!angle) return null;
  }
  const api = {
    gl, isGL2, canvas,
    vertexAttribDivisor: isGL2
      ? (i, d) => gl.vertexAttribDivisor(i, d)
      : (i, d) => angle.vertexAttribDivisorANGLE(i, d),
    drawElementsInstanced: isGL2
      ? (m, c, t, o, n) => gl.drawElementsInstanced(m, c, t, o, n)
      : (m, c, t, o, n) => angle.drawElementsInstancedANGLE(m, c, t, o, n),
    maxAnisotropy: 1,
    aniso: null,
  };
  const af = gl.getExtension('EXT_texture_filter_anisotropic')
    || gl.getExtension('WEBKIT_EXT_texture_filter_anisotropic');
  if (af) {
    api.aniso = af;
    api.maxAnisotropy = Math.min(8, gl.getParameter(af.MAX_TEXTURE_MAX_ANISOTROPY_EXT));
  }
  return api;
}

export function compile(ctx, vsSource, fsSource, attribOrder = []) {
  const { gl, isGL2 } = ctx;
  const prelude = isGL2 ? '#version 300 es\n' : '';
  const vs = shader(gl, gl.VERTEX_SHADER, prelude + translate(vsSource, isGL2, true));
  const fs = shader(gl, gl.FRAGMENT_SHADER, prelude + translate(fsSource, isGL2, false));
  const prog = gl.createProgram();
  gl.attachShader(prog, vs);
  gl.attachShader(prog, fs);
  attribOrder.forEach((name, i) => gl.bindAttribLocation(prog, i, name));
  gl.linkProgram(prog);
  if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
    throw new Error('shader link failed: ' + gl.getProgramInfoLog(prog));
  }
  gl.deleteShader(vs);
  gl.deleteShader(fs);
  const uniforms = {};
  const n = gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) {
    const info = gl.getActiveUniform(prog, i);
    const name = info.name.replace(/\[0\]$/, '');
    uniforms[name] = gl.getUniformLocation(prog, name);
  }
  return { program: prog, uniforms };
}

function shader(gl, type, source) {
  const s = gl.createShader(type);
  gl.shaderSource(s, source);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(s);
    console.error(source.split('\n').map((l, i) => `${i + 1}: ${l}`).join('\n'));
    throw new Error('shader compile failed: ' + log);
  }
  return s;
}

// Shaders are authored in GLSL ES 1.00 style; upgrade them for WebGL2.
function translate(src, isGL2, isVertex) {
  if (!isGL2) return src;
  let out = src
    .replace(/\battribute\b/g, 'in')
    .replace(/\btexture2D\b/g, 'texture');
  if (isVertex) {
    out = out.replace(/\bvarying\b/g, 'out');
  } else {
    out = out.replace(/\bvarying\b/g, 'in')
      .replace(/\bgl_FragColor\b/g, 'fragColor');
    out = out.replace(/precision ([a-z]+) float;/,
      'precision $1 float;\nout vec4 fragColor;');
    if (!/out vec4 fragColor;/.test(out)) out = 'out vec4 fragColor;\n' + out;
  }
  return out;
}

export function buffer(ctx, target, data, usage) {
  const { gl } = ctx;
  const buf = gl.createBuffer();
  gl.bindBuffer(target, buf);
  gl.bufferData(target, data, usage || gl.STATIC_DRAW);
  return buf;
}

export function texture2D(ctx, source, opts = {}) {
  const { gl } = ctx;
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, opts.flipY !== false);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
  const repeat = opts.repeat !== false ? gl.REPEAT : gl.CLAMP_TO_EDGE;
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, repeat);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, repeat);
  if (opts.mipmap !== false) {
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  } else {
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  }
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER,
    opts.nearest ? gl.NEAREST : gl.LINEAR);
  if (ctx.aniso && opts.mipmap !== false) {
    gl.texParameterf(gl.TEXTURE_2D, ctx.aniso.TEXTURE_MAX_ANISOTROPY_EXT,
      ctx.maxAnisotropy);
  }
  gl.bindTexture(gl.TEXTURE_2D, null);
  return tex;
}

/** A reusable, growable instance attribute buffer. */
export class InstanceBuffer {
  constructor(ctx, floatsPerInstance, initialCapacity = 256) {
    this.ctx = ctx;
    this.stride = floatsPerInstance;
    this.capacity = initialCapacity;
    this.data = new Float32Array(this.capacity * this.stride);
    this.count = 0;
    this.buffer = ctx.gl.createBuffer();
    this.dirty = true;
    this.bytes = 0;
  }
  reset() { this.count = 0; }
  reserve(n) {
    if (n <= this.capacity) return;
    let cap = this.capacity;
    while (cap < n) cap *= 2;
    const next = new Float32Array(cap * this.stride);
    next.set(this.data.subarray(0, this.count * this.stride));
    this.data = next;
    this.capacity = cap;
  }
  /** Returns the float offset for a new instance. */
  alloc() {
    if (this.count + 1 > this.capacity) this.reserve(this.count + 1);
    const off = this.count * this.stride;
    this.count++;
    this.dirty = true;
    return off;
  }
  upload() {
    const { gl } = this.ctx;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buffer);
    const used = this.count * this.stride;
    if (this.bytes < used * 4) {
      gl.bufferData(gl.ARRAY_BUFFER, this.data, gl.DYNAMIC_DRAW);
      this.bytes = this.data.length * 4;
    } else {
      gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.data.subarray(0, used));
    }
    this.dirty = false;
  }
  dispose() { this.ctx.gl.deleteBuffer(this.buffer); }
}
