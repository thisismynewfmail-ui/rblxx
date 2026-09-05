// Networking: authoritative snapshots in, predicted inputs out.
//
//  * the local player is simulated immediately and reconciled against the
//    server's `me` block (replaying any inputs it hasn't seen yet)
//  * everyone else is rendered ~2 snapshots in the past and interpolated,
//    which hides jitter without adding perceptible lag

import { makeState, moveCharacter } from './physics.js';

const INTERP_DELAY = 0.10;
const MAX_HISTORY = 128;

export class NetClient extends EventTarget {
  constructor(worldId, ticket) {
    super();
    this.worldId = worldId;
    this.ticket = ticket;
    this.ws = null;
    this.connected = false;
    this.seq = 0;
    this.pending = [];
    this.players = new Map();       // id -> {profile, buffer, model, ...}
    this.enemies = new Map();
    this.projectiles = new Map();
    this.me = null;
    this.myId = null;
    this.config = null;
    this.hud = {};
    this.serverTime = 0;
    this.clockOffset = 0;
    this.ping = 0;
    this.state = makeState();
    this.spectating = false;
    this.alive = false;
    this.health = 100;
    this.armor = 0;
    this.weapons = [];
    this.slot = 0;
    this.effects = {};
    this.score = { score: 0, kills: 0, deaths: 0, streak: 0, points: 0 };
    this.lastSnapshotAt = 0;
    this.reconciliations = 0;
    this.bytesIn = 0;
    this.closed = false;
  }

  connect() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${location.host}/ws/game/${this.worldId}`
      + `?ticket=${encodeURIComponent(this.ticket)}`;
    this.ws = new WebSocket(url);
    this.ws.onopen = () => {
      this.connected = true;
      this.emit('open');
      this._pingTimer = setInterval(() => this.sendPing(), 2000);
      this.sendPing();
    };
    this.ws.onmessage = (ev) => {
      this.bytesIn += ev.data.length || 0;
      let msg;
      try { msg = JSON.parse(ev.data); } catch { return; }
      if (msg.t === 'batch') { for (const m of msg.m) this._handle(m); }
      else this._handle(msg);
    };
    this.ws.onclose = (ev) => {
      this.connected = false;
      clearInterval(this._pingTimer);
      if (!this.closed) this.emit('close', { code: ev.code, reason: ev.reason });
    };
    this.ws.onerror = () => this.emit('error', {});
  }

  close() {
    this.closed = true;
    clearInterval(this._pingTimer);
    if (this.ws) try { this.ws.close(1000, 'leaving'); } catch { /* ignore */ }
  }

  emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }

  send(obj) {
    if (this.ws && this.ws.readyState === 1) {
      this.ws.send(JSON.stringify(obj));
    }
  }

  sendPing() {
    this._pingSent = performance.now();
    this.send({ t: 'ping', ts: this._pingSent, sent: Date.now() });
  }

  // ------------------------------------------------------------- messages
  _handle(msg) {
    switch (msg.t) {
      case 'welcome': return this._welcome(msg);
      case 'snap': return this._snapshot(msg);
      case 'pong': {
        if (msg.ts) {
          const rtt = (performance.now() - msg.ts) / 1000;
          this.ping = this.ping ? this.ping * 0.7 + rtt * 0.3 : rtt;
        }
        return;
      }
      case 'spawn': {
        this.state = makeState(msg.p[0], msg.p[1], msg.p[2],
          this.config ? this.config.playerRadius : 1.4,
          this.config ? this.config.playerHeight : 5);
        this.pending.length = 0;
        this.alive = true;
        this.spectating = false;
        if (msg.weapons) this.weapons = msg.weapons;
        this.emit('spawn', msg);
        return;
      }
      case 'join': {
        this.players.set(msg.player.id, this._newRemote(msg.player));
        this.emit('roster', {});
        this.emit('system', { text: `${msg.player.name} joined the game` });
        return;
      }
      case 'leave': {
        this.players.delete(msg.id);
        this.emit('roster', {});
        this.emit('system', { text: `${msg.name} left the game` });
        return;
      }
      case 'weapons': {
        this.weapons = msg.list;
        this.slot = msg.slot;
        this.emit('weapons', msg);
        return;
      }
      case 'part': {
        this.emit('part', msg);
        return;
      }
      case 'pickup': return this.emit('pickup', msg);
      default:
        this.emit(msg.t, msg);
    }
  }

  _newRemote(profile) {
    return {
      profile, id: profile.id, buffer: [], model: null,
      render: { x: 0, y: 0, z: 0, yaw: 0, pitch: 0, speed: 0,
                onGround: true, alive: true, firing: false, crouch: false },
      lastSeen: performance.now(),
    };
  }

  _welcome(msg) {
    this.config = msg;
    this.myId = msg.yourId;
    this.hud = msg.hud || {};
    this.weapons = msg.loadout || [];
    this.players.clear();
    for (const p of msg.players || []) {
      if (p.id === this.myId) { this.me = p; continue; }
      this.players.set(p.id, this._newRemote(p));
    }
    this.me = this.me || msg.you;
    this.state = makeState(0, 0, 0, msg.playerRadius, msg.playerHeight);
    this.emit('welcome', msg);
  }

  _snapshot(msg) {
    const now = performance.now() / 1000;
    this.lastSnapshotAt = now;
    this.serverTime = msg.s;
    this.hud = msg.hud || this.hud;
    if (msg.lava !== undefined) this.lavaY = msg.lava;

    // --- remote players ---
    const seen = new Set();
    for (const p of msg.pl || []) {
      if (p.i === this.myId) continue;
      seen.add(p.i);
      let remote = this.players.get(p.i);
      if (!remote) {
        remote = this._newRemote({ id: p.i, name: `Player ${p.i}`,
                                   team: 'neutral', avatar: {} });
        this.players.set(p.i, remote);
        this.emit('roster', {});
      }
      remote.buffer.push({ t: now, p: p.p, y: p.y, pitch: p.t, alive: p.a,
                           firing: p.f, onGround: p.g, crouch: p.c,
                           sprint: p.sp, weapon: p.w, hp: p.h, flag: p.fl,
                           emote: p.em, downed: p.dn, zip: p.zp, shield: p.sh });
      if (remote.buffer.length > 24) remote.buffer.shift();
      remote.lastSeen = now;
      remote.hp = p.h;
      remote.weapon = p.w;
    }

    // --- enemies ---
    if (msg.en) {
      const alive = new Set();
      for (const e of msg.en) {
        alive.add(e.i);
        let en = this.enemies.get(e.i);
        if (!en) { en = { id: e.i, buffer: [], kind: e.k }; this.enemies.set(e.i, en); }
        en.kind = e.k;
        en.health = e.h;
        en.buffer.push({ t: now, p: e.p, y: e.y, anim: e.a });
        if (en.buffer.length > 16) en.buffer.shift();
      }
      for (const id of [...this.enemies.keys()]) {
        if (!alive.has(id)) this.enemies.delete(id);
      }
    } else if (this.enemies.size) {
      this.enemies.clear();
    }

    // --- projectiles ---
    this.projectiles.clear();
    for (const pr of msg.pr || []) this.projectiles.set(pr.id, pr);

    // --- authoritative self ---
    const me = msg.me;
    if (me) {
      this.health = me.hp;
      this.armor = me.ar;
      this.alive = me.a;
      this.spectating = me.sp;
      this.respawnIn = me.rs;
      this.effects = me.ef || {};
      this.slot = me.sl;
      this.reloadLeft = me.rl;
      this.downed = me.dn;
      this.reviverName = me.rvn;
      this.carryingFlag = me.fl;
      this.score = { score: me.sc, kills: me.ki, deaths: me.de,
                     streak: me.st, points: me.pt };
      if (this.weapons[this.slot]) {
        this.weapons[this.slot].ammo = me.am;
        this.weapons[this.slot].reserve = me.rv;
      }
      this._reconcile(me);
    }
    this.emit('snapshot', msg);
  }

  _reconcile(me) {
    if (this.freeze) return;
    if (!this.world || !this.alive) {
      if (me.p) {
        this.state.x = me.p[0]; this.state.y = me.p[1]; this.state.z = me.p[2];
      }
      return;
    }
    const ack = me.seq | 0;
    this.pending = this.pending.filter((p) => p.seq > ack);
    const err = Math.hypot(this.state.x - me.p[0], this.state.y - me.p[1],
                           this.state.z - me.p[2]);
    if (err < 0.05 && this.pending.length === 0) return;

    // Snap to the server state and replay everything it hasn't acked.
    const st = this.state;
    st.x = me.p[0]; st.y = me.p[1]; st.z = me.p[2];
    st.vx = me.v[0]; st.vy = me.v[1]; st.vz = me.v[2];
    st.onGround = me.g;
    for (const cmd of this.pending) {
      moveCharacter(st, this.world.collision, cmd.wx, cmd.wz, cmd.dt, cmd.opts);
    }
    if (err > 0.4) this.reconciliations++;
    if (err > 40) {
      // A teleport (spawn, zipline, launch): kill the prediction buffer.
      this.pending.length = 0;
    }
  }

  // ------------------------------------------------------------- outgoing
  sendInput(cmd) {
    this.seq++;
    const packet = {
      t: 'in', seq: this.seq,
      mv: [+cmd.moveX.toFixed(3), +cmd.moveZ.toFixed(3)],
      y: +cmd.yaw.toFixed(4), p: +cmd.pitch.toFixed(4), b: cmd.buttons,
    };
    this.send(packet);
    return this.seq;
  }

  recordPrediction(seq, wx, wz, dt, opts) {
    this.pending.push({ seq, wx, wz, dt, opts });
    if (this.pending.length > MAX_HISTORY) this.pending.shift();
  }

  fire(dir) { this.send({ t: 'fire', d: dir }); }
  reload() { this.send({ t: 'reload' }); }
  switchWeapon(slot) { this.send({ t: 'switch', slot }); }
  chat(text, channel = 'all') { this.send({ t: 'chat', text, channel }); }
  use(target) { this.send({ t: 'use', target }); }
  requestRespawn() { this.send({ t: 'respawn' }); }
  vote(choice) { this.send({ t: 'vote', choice }); }
  emote(id) { this.send({ t: 'emote', id }); }
  requestScoreboard() { this.send({ t: 'scoreboard' }); }
  setLoadout(name) { this.send({ t: 'loadout', name }); }

  // ------------------------------------------------------------- sampling
  /** Interpolate every remote entity to the render clock. */
  interpolate() {
    const renderTime = performance.now() / 1000 - INTERP_DELAY;
    for (const remote of this.players.values()) {
      const buf = remote.buffer;
      if (!buf.length) continue;
      let a = buf[0], b = buf[buf.length - 1];
      if (renderTime <= buf[0].t) { a = b = buf[0]; }
      else if (renderTime >= buf[buf.length - 1].t) { a = b = buf[buf.length - 1]; }
      else {
        for (let i = 0; i < buf.length - 1; i++) {
          if (buf[i].t <= renderTime && buf[i + 1].t >= renderTime) {
            a = buf[i]; b = buf[i + 1];
            break;
          }
        }
      }
      const span = b.t - a.t;
      const f = span > 1e-5 ? (renderTime - a.t) / span : 0;
      const r = remote.render;
      const px = a.p[0] + (b.p[0] - a.p[0]) * f;
      const py = a.p[1] + (b.p[1] - a.p[1]) * f;
      const pz = a.p[2] + (b.p[2] - a.p[2]) * f;
      r.speed = span > 1e-5
        ? Math.hypot(b.p[0] - a.p[0], b.p[2] - a.p[2]) / span : 0;
      r.x = px; r.y = py; r.z = pz;
      r.yaw = lerpAngle(a.y, b.y, f);
      r.pitch = a.pitch + (b.pitch - a.pitch) * f;
      r.alive = b.alive;
      r.firing = b.firing;
      r.onGround = b.onGround;
      r.crouch = b.crouch;
      r.weapon = b.weapon;
      r.hp = b.hp;
      r.flag = b.flag;
      r.emote = b.emote;
      r.downed = b.downed;
      r.zip = b.zip;
      r.shield = b.shield;
    }
    for (const en of this.enemies.values()) {
      const buf = en.buffer;
      if (!buf.length) continue;
      let a = buf[0], b = buf[buf.length - 1];
      if (renderTime > buf[0].t && renderTime < buf[buf.length - 1].t) {
        for (let i = 0; i < buf.length - 1; i++) {
          if (buf[i].t <= renderTime && buf[i + 1].t >= renderTime) {
            a = buf[i]; b = buf[i + 1]; break;
          }
        }
      } else if (renderTime >= buf[buf.length - 1].t) { a = b = buf[buf.length - 1]; }
      else { a = b = buf[0]; }
      const span = b.t - a.t;
      const f = span > 1e-5 ? (renderTime - a.t) / span : 0;
      en.x = a.p[0] + (b.p[0] - a.p[0]) * f;
      en.y = a.p[1] + (b.p[1] - a.p[1]) * f;
      en.z = a.p[2] + (b.p[2] - a.p[2]) * f;
      en.yaw = lerpAngle(a.y, b.y, f);
      en.anim = b.anim;
      en.speed = span > 1e-5
        ? Math.hypot(b.p[0] - a.p[0], b.p[2] - a.p[2]) / span : 0;
    }
  }
}

function lerpAngle(a, b, t) {
  const TAU = Math.PI * 2;
  let d = ((b - a + Math.PI) % TAU + TAU) % TAU - Math.PI;
  return a + d * t;
}
