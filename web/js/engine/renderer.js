// Instanced, batched forward renderer. One draw call per (shape, texture)
// pair, so a 500-part world costs a couple of dozen draws per frame.

import { m4, v3, hexToRgb, clamp } from './math.js';
import * as glh from './gl.js';
import { getMesh } from './geometry.js';
import { buildSurfaceTextures, skyTexture, SKY_PRESETS } from './textures.js';

const FLOATS = 24;                 // 16 matrix + 4 colour + 4 params

const VS = `
precision highp float;
attribute vec3 aPos;
attribute vec3 aNormal;
attribute vec4 aM0;
attribute vec4 aM1;
attribute vec4 aM2;
attribute vec4 aM3;
attribute vec4 aColor;
attribute vec4 aParams;   // x: tile multiplier, y: glow, z: uvMode, w: spin

uniform mat4 uViewProj;
uniform float uTile;
uniform float uTime;

varying vec3 vNormal;
varying vec3 vWorld;
varying vec4 vColor;
varying vec2 vUV;
varying float vTop;
varying float vGlow;

void main() {
  vec4 m0 = aM0, m1 = aM1, m2 = aM2;
  if (aParams.w > 0.0) {
    float a = uTime * aParams.w;
    float c = cos(a), s = sin(a);
    vec4 nm0 = m0 * c - m2 * s;
    vec4 nm2 = m0 * s + m2 * c;
    m0 = nm0; m2 = nm2;
  }
  mat4 model = mat4(m0, m1, m2, aM3);
  vec3 size = vec3(length(m0.xyz), length(m1.xyz), length(m2.xyz));
  vec4 world = model * vec4(aPos, 1.0);
  vWorld = world.xyz;
  vNormal = normalize(mat3(model) * aNormal);
  vColor = aColor;
  vGlow = aParams.y;

  vec3 an = abs(aNormal);
  vTop = step(0.5, an.y);
  vec2 uv;
  if (aParams.z > 0.5) {
    uv = vec2(aPos.x + 0.5, 0.5 - aPos.y);
    if (an.y > 0.5) uv = vec2(aPos.x + 0.5, aPos.z + 0.5);
    else if (an.x > 0.5) uv = vec2(0.5 - aPos.z * sign(aNormal.x), 0.5 - aPos.y);
    if (aParams.z > 1.5) uv.x = 1.0 - uv.x;
  } else {
    if (an.y > an.x && an.y > an.z) uv = vec2(aPos.x * size.x, aPos.z * size.z);
    else if (an.x > an.z) uv = vec2(aPos.z * size.z, aPos.y * size.y);
    else uv = vec2(aPos.x * size.x, aPos.y * size.y);
    uv /= max(0.001, uTile * aParams.x);
  }
  vUV = uv;
  gl_Position = uViewProj * world;
}`;

const FS = `
precision highp float;
varying vec3 vNormal;
varying vec3 vWorld;
varying vec4 vColor;
varying vec2 vUV;
varying float vTop;
varying float vGlow;

uniform sampler2D uTexTop;
uniform sampler2D uTexSide;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform vec3 uAmbientLo;
uniform vec3 uAmbientHi;
uniform vec3 uFogColor;
uniform vec2 uFogRange;
uniform vec3 uCamPos;
uniform float uAlphaScale;

void main() {
  vec4 texTop = texture2D(uTexTop, vUV);
  vec4 texSide = texture2D(uTexSide, vUV);
  vec4 tex = mix(texSide, texTop, vTop);

  vec3 n = normalize(vNormal);
  float ndl = max(dot(n, uSunDir), 0.0);
  float hemi = 0.5 + 0.5 * n.y;
  vec3 ambient = mix(uAmbientLo, uAmbientHi, hemi);
  // A touch of directional bias keeps flat faces readable (classic look).
  float facing = 0.86 + 0.14 * abs(dot(n, vec3(0.35, 0.0, 0.94)));
  vec3 lit = (ambient + uSunColor * ndl) * facing;

  vec3 base = vColor.rgb * tex.rgb;
  vec3 color = base * lit;
  color = mix(color, vColor.rgb * 1.05 + 0.12, clamp(vGlow, 0.0, 1.0));

  float dist = length(vWorld - uCamPos);
  float fog = clamp((dist - uFogRange.x) / max(1.0, uFogRange.y - uFogRange.x),
                    0.0, 1.0);
  fog *= (1.0 - clamp(vGlow, 0.0, 1.0) * 0.7);
  color = mix(color, uFogColor, fog);

  float alpha = vColor.a * tex.a * uAlphaScale;
  if (alpha < 0.02) discard;
  gl_FragColor = vec4(color, alpha);
}`;

const SKY_VS = `
precision highp float;
attribute vec3 aPos;
uniform mat4 uViewProj;
uniform vec3 uCamPos;
uniform float uScale;
varying vec3 vDir;
void main() {
  vDir = aPos;
  vec4 p = uViewProj * vec4(aPos * uScale + uCamPos, 1.0);
  gl_Position = p.xyww;
}`;

const SKY_FS = `
precision highp float;
varying vec3 vDir;
uniform sampler2D uSky;
uniform vec3 uFogColor;
void main() {
  vec3 d = normalize(vDir);
  float u = atan(d.x, -d.z) / 6.2831853 + 0.5;
  float v = 0.5 - asin(clamp(d.y, -1.0, 1.0)) / 3.14159265;
  vec3 c = texture2D(uSky, vec2(u, v)).rgb;
  float horizon = smoothstep(0.02, -0.16, d.y);
  c = mix(c, uFogColor, horizon * 0.75);
  gl_FragColor = vec4(c, 1.0);
}`;

const ATTRIBS = ['aPos', 'aNormal', 'aM0', 'aM1', 'aM2', 'aM3', 'aColor',
                 'aParams'];

class Batch {
  constructor(ctx, mesh, tex, opts = {}) {
    this.ctx = ctx;
    this.mesh = mesh;
    this.tex = tex;
    this.transparent = !!opts.transparent;
    this.instances = new glh.InstanceBuffer(ctx, FLOATS, opts.capacity || 64);
    const { gl } = ctx;
    this.vbo = glh.buffer(ctx, gl.ARRAY_BUFFER, interleave(mesh));
    this.ibo = glh.buffer(ctx, gl.ELEMENT_ARRAY_BUFFER, mesh.indices);
    this.indexType = mesh.indices instanceof Uint32Array
      ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT;
    this.vao = null;
  }
  dispose() {
    const { gl } = this.ctx;
    gl.deleteBuffer(this.vbo);
    gl.deleteBuffer(this.ibo);
    this.instances.dispose();
    if (this.vao && this.ctx.isGL2) gl.deleteVertexArray(this.vao);
  }
}

function interleave(mesh) {
  const n = mesh.positions.length / 3;
  const out = new Float32Array(n * 6);
  for (let i = 0; i < n; i++) {
    out[i * 6] = mesh.positions[i * 3];
    out[i * 6 + 1] = mesh.positions[i * 3 + 1];
    out[i * 6 + 2] = mesh.positions[i * 3 + 2];
    out[i * 6 + 3] = mesh.normals[i * 3];
    out[i * 6 + 4] = mesh.normals[i * 3 + 1];
    out[i * 6 + 5] = mesh.normals[i * 3 + 2];
  }
  return out;
}

export class Renderer {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.ctx = glh.createContext(canvas, opts);
    if (!this.ctx) throw new Error('WebGL is not available in this browser.');
    const { gl } = this.ctx;
    this.gl = gl;
    this.shader = glh.compile(this.ctx, VS, FS, ATTRIBS);
    this.skyShader = glh.compile(this.ctx, SKY_VS, SKY_FS, ['aPos']);
    this.textures = buildSurfaceTextures(this.ctx, glh);
    this.extraTextures = new Map();

    this.staticBatches = new Map();
    this.dynamicBatches = new Map();
    this.batchOrder = [];
    this.skyTex = null;
    this.skyMesh = getMesh('sphere');
    this.skyVbo = glh.buffer(this.ctx, gl.ARRAY_BUFFER,
                             interleave(this.skyMesh));
    this.skyIbo = glh.buffer(this.ctx, gl.ELEMENT_ARRAY_BUFFER,
                             this.skyMesh.indices);

    this.view = m4.create();
    this.proj = m4.create();
    this.viewProj = m4.create();
    this.camPos = v3.create(0, 10, 0);
    this.sunDir = v3.create(0.4, 0.85, 0.35);
    this.sunColor = [0.62, 0.60, 0.55];
    this.ambientLo = [0.30, 0.32, 0.38];
    this.ambientHi = [0.52, 0.54, 0.58];
    this.fogColor = [0.80, 0.88, 0.95];
    this.fogRange = [300, 1000];
    this.time = 0;
    this.fov = 72;
    this.near = 0.12;
    this.far = 4000;
    this.dpr = Math.min(window.devicePixelRatio || 1, opts.maxDpr || 2);
    this.stats = { draws: 0, instances: 0, batches: 0 };
    this.hiddenTags = new Set();

    gl.enable(gl.DEPTH_TEST);
    gl.enable(gl.CULL_FACE);
    gl.cullFace(gl.BACK);
    gl.depthFunc(gl.LEQUAL);
    this.resize();
  }

  // ---------------------------------------------------------------- setup
  setSky(name) {
    const preset = SKY_PRESETS[name] || SKY_PRESETS.classic;
    if (this.skyTex) this.gl.deleteTexture(this.skyTex);
    this.skyTex = skyTexture(this.ctx, glh, name);
    this.skyName = name;
    const [r, g, b] = hexToRgb(preset.horizon);
    this.fogColor = [r, g, b];
    v3.normalize(this.sunDir, v3.create(...preset.sunPos));
    return preset;
  }

  setLighting({ ambient = 0.55, sun, fog, fogNear, fogFar }) {
    const a = clamp(ambient, 0.05, 1.2);
    this.ambientLo = [a * 0.62, a * 0.65, a * 0.78];
    this.ambientHi = [a * 0.95, a * 0.98, a * 1.0];
    this.sunColor = [0.72 - a * 0.18, 0.70 - a * 0.18, 0.64 - a * 0.16]
      .map((v) => Math.max(0.06, v));
    if (sun) v3.normalize(this.sunDir, v3.create(sun[0], sun[1], sun[2]));
    if (fog) this.fogColor = hexToRgb(fog);
    if (fogNear != null) this.fogRange[0] = fogNear;
    if (fogFar != null) this.fogRange[1] = fogFar;
  }

  registerTexture(key, tex, opts = {}) {
    this.extraTextures.set(key, {
      name: key, top: tex, side: tex,
      tile: opts.tile || 1, transparent: !!opts.transparent,
    });
    return key;
  }

  lookupTexture(name) {
    return this.textures[name] || this.extraTextures.get(name)
      || this.textures.smooth;
  }

  resize() {
    const w = Math.max(1, Math.floor(this.canvas.clientWidth * this.dpr));
    const h = Math.max(1, Math.floor(this.canvas.clientHeight * this.dpr));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w;
      this.canvas.height = h;
    }
    this.aspect = w / Math.max(1, h);
  }

  // ---------------------------------------------------------------- batches
  _batch(map, shape, texName, transparent) {
    const key = `${shape}|${texName}|${transparent ? 1 : 0}`;
    let b = map.get(key);
    if (!b) {
      const tex = this.lookupTexture(texName);
      b = new Batch(this.ctx, getMesh(shape), tex,
                    { transparent: transparent || tex.transparent });
      map.set(key, b);
    }
    return b;
  }

  clearStatic() {
    for (const b of this.staticBatches.values()) b.dispose();
    this.staticBatches.clear();
  }

  beginDynamic() {
    for (const b of this.dynamicBatches.values()) b.instances.reset();
  }

  /** Adds one instance. `into` is 'static' or 'dynamic'. */
  add(into, shape, texName, px, py, pz, sx, sy, sz, color,
      { rx = 0, ry = 0, rz = 0, alpha = 1, glow = 0, tile = 1, uvMode = 0,
        spin = 0 } = {}) {
    const transparent = alpha < 0.999;
    const map = into === 'static' ? this.staticBatches : this.dynamicBatches;
    const batch = this._batch(map, shape, texName, transparent);
    const buf = batch.instances;
    const off = buf.alloc();
    const d = buf.data;
    m4.compose(d, off, px, py, pz, rx, ry, rz, sx, sy, sz);
    const c = typeof color === 'string' ? hexToRgb(color) : color;
    d[off + 16] = c[0]; d[off + 17] = c[1]; d[off + 18] = c[2];
    d[off + 19] = alpha;
    d[off + 20] = tile; d[off + 21] = glow; d[off + 22] = uvMode;
    d[off + 23] = spin;
    return batch;
  }

  uploadStatic() {
    for (const b of this.staticBatches.values()) b.instances.upload();
  }

  // ---------------------------------------------------------------- camera
  setCamera(pos, yaw, pitch, roll = 0, fov = this.fov) {
    v3.copy(this.camPos, pos);
    const cp = Math.cos(pitch);
    const fwd = [-Math.sin(yaw) * cp, Math.sin(pitch), -Math.cos(yaw) * cp];
    const target = [pos[0] + fwd[0], pos[1] + fwd[1], pos[2] + fwd[2]];
    let up = [0, 1, 0];
    if (roll) {
      const right = [Math.cos(yaw), 0, -Math.sin(yaw)];
      const cr = Math.cos(roll), sr = Math.sin(roll);
      up = [right[0] * sr, cr, right[2] * sr];
    }
    m4.lookAt(this.view, pos, target, up);
    m4.perspective(this.proj, fov * Math.PI / 180, this.aspect, this.near,
                   this.far);
    m4.multiply(this.viewProj, this.proj, this.view);
    this.forward = fwd;
  }

  projectToScreen(x, y, z, out) {
    const m = this.viewProj;
    const cx = m[0] * x + m[4] * y + m[8] * z + m[12];
    const cy = m[1] * x + m[5] * y + m[9] * z + m[13];
    const cw = m[3] * x + m[7] * y + m[11] * z + m[15];
    if (cw <= 0.001) { out.visible = false; return out; }
    out.visible = true;
    out.x = (cx / cw * 0.5 + 0.5) * this.canvas.clientWidth;
    out.y = (0.5 - cy / cw * 0.5) * this.canvas.clientHeight;
    out.depth = cw;
    return out;
  }

  // ---------------------------------------------------------------- draw
  render(dt) {
    const { gl } = this;
    this.time += dt;
    this.resize();
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(this.fogColor[0], this.fogColor[1], this.fogColor[2], 1);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    this.stats.draws = 0;
    this.stats.instances = 0;

    this._drawSky();

    const prog = this.shader;
    gl.useProgram(prog.program);
    gl.uniformMatrix4fv(prog.uniforms.uViewProj, false, this.viewProj);
    gl.uniform3fv(prog.uniforms.uSunDir, this.sunDir);
    gl.uniform3fv(prog.uniforms.uSunColor, this.sunColor);
    gl.uniform3fv(prog.uniforms.uAmbientLo, this.ambientLo);
    gl.uniform3fv(prog.uniforms.uAmbientHi, this.ambientHi);
    gl.uniform3fv(prog.uniforms.uFogColor, this.fogColor);
    gl.uniform2fv(prog.uniforms.uFogRange, this.fogRange);
    gl.uniform3fv(prog.uniforms.uCamPos, this.camPos);
    gl.uniform1f(prog.uniforms.uTime, this.time);
    gl.uniform1f(prog.uniforms.uAlphaScale, 1.0);
    gl.uniform1i(prog.uniforms.uTexTop, 0);
    gl.uniform1i(prog.uniforms.uTexSide, 1);

    for (const b of this.dynamicBatches.values()) {
      if (b.instances.count) b.instances.upload();
    }

    gl.disable(gl.BLEND);
    gl.depthMask(true);
    this._drawBatches(this.staticBatches, false);
    this._drawBatches(this.dynamicBatches, false);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    gl.depthMask(false);
    this._drawBatches(this.staticBatches, true);
    this._drawBatches(this.dynamicBatches, true);
    gl.depthMask(true);
    gl.disable(gl.BLEND);

    this.stats.batches = this.staticBatches.size + this.dynamicBatches.size;
  }

  _drawBatches(map, transparent) {
    const { gl, ctx } = this;
    const prog = this.shader;
    for (const b of map.values()) {
      if (b.transparent !== transparent) continue;
      if (!b.instances.count) continue;
      gl.bindBuffer(gl.ARRAY_BUFFER, b.vbo);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 24, 12);
      ctx.vertexAttribDivisor(0, 0);
      ctx.vertexAttribDivisor(1, 0);

      gl.bindBuffer(gl.ARRAY_BUFFER, b.instances.buffer);
      for (let i = 0; i < 6; i++) {
        const loc = 2 + i;
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, 4, gl.FLOAT, false, FLOATS * 4, i * 16);
        ctx.vertexAttribDivisor(loc, 1);
      }
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, b.ibo);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, b.tex.top);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, b.tex.side);
      gl.uniform1f(prog.uniforms.uTile, b.tex.tile);
      ctx.drawElementsInstanced(gl.TRIANGLES, b.mesh.count, b.indexType, 0,
                                b.instances.count);
      this.stats.draws++;
      this.stats.instances += b.instances.count;
    }
  }

  _drawSky() {
    if (!this.skyTex) return;
    const { gl } = this;
    const prog = this.skyShader;
    gl.useProgram(prog.program);
    gl.depthMask(false);
    gl.disable(gl.CULL_FACE);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.skyVbo);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 24, 0);
    for (let i = 1; i < 8; i++) gl.disableVertexAttribArray(i);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.skyIbo);
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.skyTex);
    gl.uniform1i(prog.uniforms.uSky, 0);
    gl.uniformMatrix4fv(prog.uniforms.uViewProj, false, this.viewProj);
    gl.uniform3fv(prog.uniforms.uCamPos, this.camPos);
    gl.uniform3fv(prog.uniforms.uFogColor, this.fogColor);
    gl.uniform1f(prog.uniforms.uScale, this.far * 0.5);
    const type = this.skyMesh.indices instanceof Uint32Array
      ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT;
    gl.drawElements(gl.TRIANGLES, this.skyMesh.count, type, 0);
    gl.enable(gl.CULL_FACE);
    gl.depthMask(true);
  }

  dispose() {
    for (const b of this.staticBatches.values()) b.dispose();
    for (const b of this.dynamicBatches.values()) b.dispose();
    this.staticBatches.clear();
    this.dynamicBatches.clear();
  }
}
