// Every sound is synthesised at runtime with WebAudio — no audio files, so
// the game stays a zero-asset download and still has weight to it.

const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);

export class GameAudio {
  constructor(settings) {
    this.settings = settings;
    this.ctx = null;
    this.master = null;
    this.noise = null;
    this.listener = { x: 0, y: 0, z: 0, yaw: 0 };
    this.lastStep = 0;
    this.enabled = true;
    this._pending = 0;
  }

  /** Browsers only allow audio after a gesture; call this from one. */
  resume() {
    if (!this.ctx) this._create();
    if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume();
  }

  _create() {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) { this.enabled = false; return; }
    try {
      this.ctx = new AC();
    } catch { this.enabled = false; return; }
    this.master = this.ctx.createGain();
    this.master.gain.value = this.settings.masterVolume ?? 0.7;
    const comp = this.ctx.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.knee.value = 24;
    comp.ratio.value = 8;
    comp.attack.value = 0.002;
    comp.release.value = 0.18;
    this.master.connect(comp);
    comp.connect(this.ctx.destination);

    // one second of white noise, reused by everything percussive
    const len = this.ctx.sampleRate;
    const buf = this.ctx.createBuffer(1, len, this.ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = Math.random() * 2 - 1;
    this.noise = buf;
  }

  applySettings() {
    if (this.master) {
      this.master.gain.value = this.settings.masterVolume ?? 0.7;
    }
  }

  setListener(pos, yaw) {
    this.listener.x = pos[0];
    this.listener.y = pos[1];
    this.listener.z = pos[2];
    this.listener.yaw = yaw;
  }

  /** Distance gain + stereo pan for a world position. */
  _spatial(pos, maxDist = 260) {
    if (!pos) return { gain: 1, pan: 0 };
    const dx = pos[0] - this.listener.x;
    const dy = pos[1] - this.listener.y;
    const dz = pos[2] - this.listener.z;
    const dist = Math.hypot(dx, dy, dz);
    if (dist > maxDist) return null;
    const gain = clamp(1 - dist / maxDist, 0, 1) ** 1.8;
    const right = [Math.cos(this.listener.yaw), 0, -Math.sin(this.listener.yaw)];
    const pan = dist < 0.5 ? 0
      : clamp((dx * right[0] + dz * right[2]) / dist, -1, 1) * 0.85;
    return { gain, pan };
  }

  _chain(gainValue, pan) {
    const g = this.ctx.createGain();
    g.gain.value = gainValue * (this.settings.sfxVolume ?? 0.8);
    if (pan && this.ctx.createStereoPanner) {
      const p = this.ctx.createStereoPanner();
      p.pan.value = pan;
      g.connect(p);
      p.connect(this.master);
    } else {
      g.connect(this.master);
    }
    return g;
  }

  _ready() {
    if (!this.enabled) return false;
    if (!this.ctx) this._create();
    if (!this.ctx || this.ctx.state !== 'running') return false;
    // never let a burst of events stack into a wall of sound
    if (this._pending > 26) return false;
    this._pending++;
    setTimeout(() => { this._pending--; }, 120);
    return true;
  }

  _noiseBurst(dest, { duration = 0.12, type = 'lowpass', freq = 1800,
                      q = 1, curve = 4, gain = 1, delay = 0 } = {}) {
    const t = this.ctx.currentTime + delay;
    const src = this.ctx.createBufferSource();
    src.buffer = this.noise;
    src.playbackRate.value = 0.8 + Math.random() * 0.4;
    const filt = this.ctx.createBiquadFilter();
    filt.type = type;
    filt.frequency.setValueAtTime(freq, t);
    filt.Q.value = q;
    const env = this.ctx.createGain();
    env.gain.setValueAtTime(gain, t);
    env.gain.exponentialRampToValueAtTime(0.0008, t + duration);
    src.connect(filt); filt.connect(env); env.connect(dest);
    src.start(t, Math.random() * 0.5);
    src.stop(t + duration + 0.02);
    return filt;
  }

  _tone(dest, { freq = 440, to = null, duration = 0.14, type = 'sine',
                gain = 0.5, delay = 0 } = {}) {
    const t = this.ctx.currentTime + delay;
    const osc = this.ctx.createOscillator();
    osc.type = type;
    osc.frequency.setValueAtTime(freq, t);
    if (to) osc.frequency.exponentialRampToValueAtTime(Math.max(20, to),
                                                       t + duration);
    const env = this.ctx.createGain();
    env.gain.setValueAtTime(0.0001, t);
    env.gain.exponentialRampToValueAtTime(gain, t + 0.006);
    env.gain.exponentialRampToValueAtTime(0.0008, t + duration);
    osc.connect(env); env.connect(dest);
    osc.start(t);
    osc.stop(t + duration + 0.02);
  }

  // ------------------------------------------------------------- weapons
  shot(weaponModel, pos, own) {
    if (!this._ready()) return;
    const s = own ? { gain: 1, pan: 0 } : this._spatial(pos, 420);
    if (!s) return;
    const dest = this._chain(s.gain * (own ? 0.5 : 0.62), s.pan);
    const profile = {
      pistol:  { d: 0.11, f: 2600, body: 190, g: 0.9 },
      rifle:   { d: 0.13, f: 2200, body: 150, g: 1.0 },
      shotgun: { d: 0.26, f: 1500, body: 90,  g: 1.25 },
      sniper:  { d: 0.34, f: 1200, body: 70,  g: 1.35 },
      launcher: { d: 0.24, f: 900, body: 60,  g: 1.2 },
      zapper:  { d: 0.09, f: 4200, body: 520, g: 0.7 },
      mender:  { d: 0.10, f: 3000, body: 700, g: 0.4 },
      ball:    { d: 0.10, f: 1400, body: 320, g: 0.5 },
    }[weaponModel] || { d: 0.13, f: 2200, body: 150, g: 1 };
    this._noiseBurst(dest, { duration: profile.d, freq: profile.f,
                             type: 'bandpass', q: 0.8, gain: profile.g });
    this._tone(dest, { freq: profile.body, to: profile.body * 0.35,
                       duration: profile.d * 1.5, type: 'square',
                       gain: 0.28 * profile.g });
    if (!own) {
      // a little tail so distant fire reads as an echo
      this._noiseBurst(dest, { duration: 0.3, freq: 700, type: 'lowpass',
                               gain: 0.18, delay: 0.05 });
    }
  }

  impact(kind, pos) {
    if (!this._ready()) return;
    const s = this._spatial(pos, 160);
    if (!s) return;
    const dest = this._chain(s.gain * 0.5, s.pan);
    if (kind === 'flesh') {
      this._noiseBurst(dest, { duration: 0.08, freq: 700, type: 'lowpass',
                               gain: 0.9 });
      this._tone(dest, { freq: 150, to: 70, duration: 0.09, type: 'sine',
                         gain: 0.3 });
    } else {
      this._noiseBurst(dest, { duration: 0.07, freq: 3200, type: 'highpass',
                               gain: 0.6 });
    }
  }

  explosion(pos) {
    if (!this._ready()) return;
    const s = this._spatial(pos, 500);
    if (!s) return;
    const dest = this._chain(s.gain * 1.0, s.pan);
    this._noiseBurst(dest, { duration: 0.75, freq: 420, type: 'lowpass',
                             gain: 1.3 });
    this._tone(dest, { freq: 90, to: 26, duration: 0.7, type: 'sine',
                       gain: 0.85 });
    this._noiseBurst(dest, { duration: 0.16, freq: 2600, type: 'highpass',
                             gain: 0.5 });
  }

  hitmarker(kill) {
    if (!this._ready()) return;
    const dest = this._chain(0.45, 0);
    if (kill) {
      this._tone(dest, { freq: 880, duration: 0.06, type: 'square', gain: 0.5 });
      this._tone(dest, { freq: 1320, duration: 0.13, type: 'square',
                         gain: 0.45, delay: 0.055 });
    } else {
      this._tone(dest, { freq: 1650, to: 1250, duration: 0.05,
                         type: 'triangle', gain: 0.5 });
    }
  }

  hurt(amount) {
    if (!this._ready()) return;
    const dest = this._chain(clamp(0.25 + amount / 90, 0.25, 0.9), 0);
    this._noiseBurst(dest, { duration: 0.16, freq: 500, type: 'lowpass',
                             gain: 0.9 });
    this._tone(dest, { freq: 190, to: 90, duration: 0.2, type: 'sine',
                       gain: 0.4 });
  }

  // -------------------------------------------------------------- moving
  footstep(speed) {
    const now = performance.now();
    const gap = clamp(620 - speed * 16, 260, 620);
    if (now - this.lastStep < gap) return;
    this.lastStep = now;
    if (!this._ready()) return;
    const dest = this._chain(0.16, (Math.random() - 0.5) * 0.3);
    this._noiseBurst(dest, { duration: 0.07, freq: 900 + Math.random() * 400,
                             type: 'lowpass', gain: 0.7 });
  }

  jump() {
    if (!this._ready()) return;
    const dest = this._chain(0.2, 0);
    this._tone(dest, { freq: 320, to: 520, duration: 0.09, type: 'triangle',
                       gain: 0.4 });
  }

  land(force) {
    if (!this._ready()) return;
    const dest = this._chain(clamp(0.18 + force / 120, 0.18, 0.6), 0);
    this._noiseBurst(dest, { duration: 0.11, freq: 420, type: 'lowpass',
                             gain: 0.9 });
  }

  launchPad() {
    if (!this._ready()) return;
    const dest = this._chain(0.4, 0);
    this._tone(dest, { freq: 260, to: 1400, duration: 0.3, type: 'sawtooth',
                       gain: 0.35 });
  }

  // ------------------------------------------------------------- pickups
  pickup(kind) {
    if (!this._ready()) return;
    const dest = this._chain(0.4, 0);
    const notes = {
      health: [520, 780], armor: [420, 640], ammo: [660, 660],
      speed: [700, 1050], gravity: [560, 840], damage: [340, 510],
    }[kind] || [600, 900];
    this._tone(dest, { freq: notes[0], duration: 0.09, type: 'triangle',
                       gain: 0.4 });
    this._tone(dest, { freq: notes[1], duration: 0.16, type: 'triangle',
                       gain: 0.35, delay: 0.075 });
  }

  reload() {
    if (!this._ready()) return;
    const dest = this._chain(0.3, 0);
    this._noiseBurst(dest, { duration: 0.05, freq: 2400, type: 'bandpass',
                             q: 3, gain: 0.7 });
    this._noiseBurst(dest, { duration: 0.06, freq: 1600, type: 'bandpass',
                             q: 3, gain: 0.7, delay: 0.22 });
  }

  swap() {
    if (!this._ready()) return;
    const dest = this._chain(0.22, 0);
    this._noiseBurst(dest, { duration: 0.05, freq: 3000, type: 'bandpass',
                             q: 4, gain: 0.6 });
  }

  announce(kind) {
    if (!this._ready()) return;
    const dest = this._chain(0.45, 0);
    const chord = {
      victory: [523, 659, 784], defeat: [392, 330, 262],
      objective: [587, 784], wave: [330, 262, 196], round: [440, 587, 740],
      warn: [440, 415], streak: [659, 880], kill: [700],
    }[kind] || [520];
    chord.forEach((f, i) => this._tone(dest, {
      freq: f, duration: 0.26, type: 'triangle', gain: 0.3, delay: i * 0.09,
    }));
  }

  zombieGrowl(pos) {
    if (!this._ready()) return;
    const s = this._spatial(pos, 110);
    if (!s) return;
    const dest = this._chain(s.gain * 0.35, s.pan);
    this._tone(dest, { freq: 90 + Math.random() * 40, to: 55,
                       duration: 0.45, type: 'sawtooth', gain: 0.35 });
    this._noiseBurst(dest, { duration: 0.4, freq: 380, type: 'lowpass',
                             gain: 0.4 });
  }
}
