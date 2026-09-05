// A real WebGL turntable preview of a character, used on the profile page
// and in the avatar editor.

import { Renderer } from '../engine/renderer.js';
import { AvatarModel } from '../engine/avatar.js';

const live = new Set();

export class AvatarPreview {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.opts = opts;
    this.yaw = opts.yaw != null ? opts.yaw : 0.5;
    this.pitch = opts.pitch != null ? opts.pitch : 0.13;
    this.dist = opts.dist || 12.5;
    this.targetYaw = this.yaw;
    this.spin = opts.spin !== false;
    this.dragging = false;
    this.last = performance.now();
    this.ok = false;
    this.raf = 0;
    this.pose = opts.pose || 'idle';
    try {
      this.renderer = new Renderer(canvas, { antialias: true, maxDpr: 2 });
      this.ok = true;
    } catch (e) {
      canvas.parentElement?.classList.add('preview-failed');
      console.warn('avatar preview unavailable:', e.message);
      return;
    }
    this.renderer.setSky(opts.sky || 'studio');
    this.renderer.setLighting({
      ambient: 0.82, sun: [0.42, 0.86, 0.5], fog: opts.fog || '#cfe0ee',
      fogNear: 60, fogFar: 220,
    });
    this.model = new AvatarModel(opts.bundle || {});
    this._buildStage();
    this._bind();
    live.add(this);
    this.start();
  }

  _buildStage() {
    const r = this.renderer;
    r.clearStatic();
    if (this.opts.stage !== false) {
      r.add('static', 'cylinder', 'tile', 0, -0.35, 0, 9, 0.7, 9, '#dfe6ee', {});
      r.add('static', 'cylinder', 'tile', 0, -0.7, 0, 11, 0.6, 11, '#c4d0dc', {});
      for (let i = 0; i < 8; i++) {
        const a = (i / 8) * Math.PI * 2;
        r.add('static', 'box', 'smooth', Math.cos(a) * 4.9, 0.1,
              Math.sin(a) * 4.9, 0.55, 0.22, 0.55, '#9fb0c0',
              { ry: -a });
      }
    }
    r.uploadStatic();
  }

  setBundle(bundle) {
    if (!this.ok) return;
    this.model.set(bundle || {});
  }

  setPose(pose) { this.pose = pose; }

  _bind() {
    const c = this.canvas;
    let lastX = 0, lastY = 0;
    const down = (e) => {
      this.dragging = true;
      this.spin = false;
      lastX = (e.touches ? e.touches[0] : e).clientX;
      lastY = (e.touches ? e.touches[0] : e).clientY;
      c.setPointerCapture?.(e.pointerId);
    };
    const move = (e) => {
      if (!this.dragging) return;
      const x = (e.touches ? e.touches[0] : e).clientX;
      const y = (e.touches ? e.touches[0] : e).clientY;
      this.yaw -= (x - lastX) * 0.011;
      this.pitch = Math.max(-0.55, Math.min(0.75,
        this.pitch + (y - lastY) * 0.006));
      lastX = x; lastY = y;
      e.preventDefault();
    };
    const up = () => { this.dragging = false; };
    c.addEventListener('pointerdown', down);
    c.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    c.addEventListener('wheel', (e) => {
      this.dist = Math.max(7, Math.min(24, this.dist + Math.sign(e.deltaY) * 1.1));
      e.preventDefault();
    }, { passive: false });
    c.addEventListener('dblclick', () => { this.spin = !this.spin; });
    this._cleanup = () => {
      c.removeEventListener('pointerdown', down);
      c.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }

  start() {
    if (!this.ok || this.raf) return;
    const loop = () => {
      this.raf = requestAnimationFrame(loop);
      const now = performance.now();
      const dt = Math.min(0.1, (now - this.last) / 1000);
      this.last = now;
      this.frame(dt);
    };
    this.raf = requestAnimationFrame(loop);
  }

  stop() {
    cancelAnimationFrame(this.raf);
    this.raf = 0;
  }

  frame(dt) {
    const r = this.renderer;
    if (!r || !this.canvas.isConnected) { this.dispose(); return; }
    if (this.spin && !this.dragging) this.yaw += dt * 0.42;
    r.beginDynamic();
    const pose = this.pose;
    this.model.update(dt, {
      speed: pose === 'walk' ? 12 : 0,
      onGround: true,
      holding: pose === 'hold',
      crouch: false,
      pitch: 0,
    });
    this.model.draw(r, { x: 0, y: 0, z: 0, yaw: Math.PI + 0.07, pitch: 0 });
    // soft contact shadow
    r.add('dynamic', 'cylinder', 'smooth', 0, 0.06, 0, 3.6, 0.05, 3.6,
          '#0d1219', { alpha: 0.18 });
    const cp = Math.cos(this.pitch);
    const eye = [
      Math.sin(this.yaw) * cp * this.dist,
      2.5 + Math.sin(this.pitch) * this.dist,
      Math.cos(this.yaw) * cp * this.dist,
    ];
    const camYaw = Math.atan2(-eye[0], -eye[2]) + Math.PI;
    const flat = Math.hypot(eye[0], eye[2]);
    const camPitch = Math.atan2(2.5 - eye[1], flat);
    r.setCamera(eye, camYaw, camPitch, 0, 34);
    r.render(dt);
  }

  dispose() {
    this.stop();
    live.delete(this);
    this._cleanup?.();
    if (this.renderer) {
      this.renderer.dispose();
      const gl = this.renderer.gl;
      const ext = gl.getExtension('WEBGL_lose_context');
      if (ext) ext.loseContext();
      this.renderer = null;
    }
  }
}

export function disposeAllPreviews() {
  for (const p of [...live]) p.dispose();
}
