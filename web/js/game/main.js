// Game View bootstrap and main loop.

import { Renderer } from '../engine/renderer.js';
import { AvatarModel } from '../engine/avatar.js';
import { clamp, damp, lerpAngle } from '../engine/math.js';
import { GameWorld } from './world.js';
import { NetClient } from './net.js';
import { InputManager } from './input.js';
import { Hud } from './hud.js';
import { Chat } from './chat.js';
import { PauseMenu } from './menu.js';
import { Effects, WEAPON_SKINS } from './effects.js';
import { modelFor } from './weaponmodels.js';
import { moveCharacter } from './physics.js';

const $ = (id) => document.getElementById(id);
const TICK = 1 / 30;

const TIPS = [
  'Double-click a name in chat to open that player\'s profile in a new tab.',
  'Press P at any time to switch between first and third person.',
  'Rocket splash launches you — aim at your feet and jump.',
  'Hold Tab for the live scoreboard.',
  'Speed Coils stack with sprint. Gravity Coils make you jump 40% higher.',
  'Falling more than 34 studs hurts. Look before you leap.',
  'Esc opens the pause menu; every key can be rebound in Controls.',
  'Team chat is bound to U — the enemy will not see it.',
];

class Game {
  constructor() {
    this.canvas = $('game');
    this.worldId = decodeURIComponent(
      location.pathname.replace(/^\/play\/?/, '').replace(/\/$/, ''));
    this.thirdPerson = false;
    this.camDist = 14;
    this.camDistTarget = 14;
    this.recoil = 0;
    this.recoilYaw = 0;
    this.bob = 0;
    this.fps = 0;
    this.acc = 0;
    this.lastFrame = performance.now();
    this.avatars = new Map();
    this.scoreRows = [];
    this.holdScoreboard = false;
    this.spectateTarget = null;
    this.selfUserId = null;
    this.running = false;
    this.lastFireAt = 0;
    this.camShake = [0, 0];
    this.viewYaw = 0;
    this.viewPitch = 0;
  }

  // ------------------------------------------------------------- startup
  async start() {
    this.setLoad(5, 'Checking your session…');
    let boot;
    try {
      boot = await (await fetch('/api/bootstrap', { credentials: 'same-origin' })).json();
    } catch {
      return this.fatal('Cannot reach the RBLXX server.');
    }
    if (!boot.user) {
      location.href = `/#/login?next=${encodeURIComponent('/play/' + this.worldId)}`;
      return;
    }
    this.selfUserId = boot.user.id;
    this.selfName = boot.user.username;
    const worldMeta = (boot.worlds || []).find((w) => w.id === this.worldId);
    if (worldMeta) {
      $('load-name').textContent = worldMeta.name;
      $('load-tag').textContent = worldMeta.tagline;
      document.title = `${worldMeta.name} — RBLXX`;
    }
    $('load-tip').textContent = TIPS[(Math.random() * TIPS.length) | 0];

    this.setLoad(15, 'Requesting a server slot…');
    let ticket;
    try {
      const res = await fetch(`/api/worlds/${this.worldId}/join`, {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json',
                   'X-CSRF-Token': boot.csrf || '' },
        body: '{}',
      });
      const data = await res.json();
      if (!data.ok) return this.fatal(data.error || 'The server refused the join.');
      ticket = data.ticket;
    } catch {
      return this.fatal('Could not reach the game server.');
    }

    this.setLoad(28, 'Downloading the world…');
    let level;
    try {
      level = await (await fetch(`/api/worlds/${this.worldId}/level`)).json();
    } catch {
      return this.fatal('Could not download the level.');
    }

    this.setLoad(45, 'Building geometry…');
    try {
      this.renderer = new Renderer(this.canvas, { maxDpr: 2 });
    } catch (e) {
      return this.fatal(e.message || 'WebGL is unavailable.');
    }
    await frame();
    this.renderer.setSky(level.sky || 'classic');
    this.renderer.setLighting({
      ambient: level.ambient, sun: level.sun, fog: level.fog,
      fogNear: level.fogNear, fogFar: level.fogFar,
    });
    this.world = new GameWorld(this.renderer, level);

    this.setLoad(68, 'Connecting to the match…');
    this.input = new InputManager(this.canvas);
    this.hud = new Hud(null, this.input.settings);
    this.effects = new Effects(this.renderer);
    this.net = new NetClient(this.worldId, ticket);
    this.net.world = this.world;
    this.hud.net = this.net;
    this.chat = new Chat(this.net, this.input);
    this.chat.fade = this.input.settings.chatFade;
    this.chat.onBubble = (id, text) => this.hud.bubble(id, text);
    this.menu = new PauseMenu(this);
    this.applySettings();
    this.wireInput();
    this.wireNet();
    this.net.connect();

    window.addEventListener('resize', () => this.renderer.resize());
    window.addEventListener('beforeunload', () => this.net.close());
  }

  setLoad(pct, step) {
    $('load-bar').style.width = pct + '%';
    if (step) $('load-step').textContent = step;
  }

  fatal(message) {
    $('load-step').innerHTML =
      `<span style="color:#ff8072">${message}</span><br>
       <a href="/#/games" style="color:#7cff9e">Back to the world browser</a>`;
    $('load-bar').style.background = '#c0392b';
  }

  // --------------------------------------------------------------- input
  wireInput() {
    const input = this.input;

    input.addEventListener('requestlock', () => {
      if (!this.menu.open && !this.chat.open) input.requestLock();
    });
    this.canvas.addEventListener('click', () => {
      if (!this.menu.open && !this.chat.open) input.requestLock();
    });

    input.addEventListener('lockchange', (e) => {
      document.body.classList.toggle('unlocked', !e.detail.locked);
      if (!e.detail.locked && this.running && !this.chat.open && !this.menu.open) {
        this.menu.show();
      }
    });

    input.addEventListener('escape', () => {
      if (this.chat.open) { this.chat.close(); return; }
      this.menu.toggle();
    });

    input.addEventListener('action', (e) => {
      const { action, pressed } = e.detail;
      if (!pressed) {
        if (action === 'scoreboard') {
          this.holdScoreboard = false;
          this.hud.toggleScoreboard(false);
        }
        return;
      }
      switch (action) {
        case 'chat': this.chat.openChat('all'); break;
        case 'teamChat': this.chat.openChat('team'); break;
        case 'scoreboard':
          this.holdScoreboard = true;
          this.net.requestScoreboard();
          this.hud.toggleScoreboard(true, this.scoreRows, this.net);
          break;
        case 'toggleCamera':
          this.thirdPerson = !this.thirdPerson;
          this.chat.addSystem(this.thirdPerson
            ? 'Camera: third person' : 'Camera: first person');
          break;
        case 'reload': this.net.reload(); break;
        case 'slot1': this.selectSlot(0); break;
        case 'slot2': this.selectSlot(1); break;
        case 'slot3': this.selectSlot(2); break;
        case 'slot4': this.selectSlot(3); break;
        case 'interact': this.tryInteract(); break;
        case 'emote': this.net.emote('wave'); break;
        case 'vote': this.toggleVotePanel(); break;
        case 'zoomIn': this.camDistTarget = clamp(this.camDistTarget - 2, 6, 30); break;
        case 'zoomOut': this.camDistTarget = clamp(this.camDistTarget + 2, 6, 30); break;
        case 'jump':
          if (!this.net.alive && this.net.respawnIn <= 0.05) this.net.requestRespawn();
          break;
        case 'sprint':
          if (input.settings.toggleSprint) input.sprintToggle = !input.sprintToggle;
          break;
        case 'crouch':
          if (input.settings.toggleCrouch) input.crouchToggle = !input.crouchToggle;
          break;
      }
    });

    input.addEventListener('wheel', (e) => {
      if (this.thirdPerson && input.isDown('crouch')) {
        this.camDistTarget = clamp(this.camDistTarget + e.detail.delta * 2, 6, 30);
        return;
      }
      const n = this.net.weapons.length;
      if (!n) return;
      this.selectSlot((this.net.slot + (e.detail.delta > 0 ? 1 : n - 1)) % n);
    });

    input.addEventListener('mouse', (e) => {
      if (e.detail.button !== 0 || !e.detail.pressed) return;
      this.fireOnce();
    });
  }

  selectSlot(i) {
    if (i < 0 || i >= this.net.weapons.length || i === this.net.slot) return;
    this.net.switchWeapon(i);
    this.net.slot = i;
  }

  tryInteract() {
    const target = this.currentInteract;
    if (target) this.net.use(target.id === 'zipline' ? null : target.id);
    else this.net.use(null);
  }

  toggleVotePanel() {
    const el = $('votepanel');
    const on = !el.classList.contains('show');
    el.classList.toggle('show', on);
    if (!on) return;
    fetch('/api/worlds').then((r) => r.json()).then((data) => {
      el.innerHTML = `<h4>Vote for the next world</h4>` +
        (data.worlds || []).map((w) => `<div class="vote-opt" data-w="${w.id}">
          <span>${w.name}</span><span class="cnt" data-c="${w.id}">
          ${(this.voteTally && this.voteTally[w.id]) || 0}</span></div>`).join('') +
        `<div style="opacity:.6;font-size:.85em;margin-top:6px">Press V to close</div>`;
      el.querySelectorAll('.vote-opt').forEach((opt) => {
        opt.addEventListener('click', () => {
          this.net.vote(opt.dataset.w);
          el.querySelectorAll('.vote-opt').forEach((o) =>
            o.classList.toggle('chosen', o === opt));
        });
      });
    });
  }

  applySettings() {
    const s = this.input.settings;
    this.renderer.fov = s.fov;
    this.renderer.dpr = { low: 0.7, medium: 1, high: Math.min(1.5, devicePixelRatio || 1),
      ultra: Math.min(2, devicePixelRatio || 1) }[s.quality] || 1;
    this.renderer.resize();
    this.hud.setHudScale(s.hudScale);
    this.hud.setCrosshair(s.crosshairColor, s.crosshairStyle);
    this.chat.fade = s.chatFade;
    $('perf').classList.toggle('show', !!s.showFps);
  }

  // ----------------------------------------------------------------- net
  wireNet() {
    const net = this.net;

    net.addEventListener('welcome', (e) => {
      const msg = e.detail;
      this.setLoad(92, 'Spawning…');
      this.hud.updateMode(msg.hud, net);
      for (const p of msg.players || []) this.ensureAvatar(p);
      if (msg.you) this.ensureAvatar(msg.you);
      (msg.chatLog || []).forEach((m) => this.chat.addMessage(m));
      (msg.killFeed || []).forEach((k) => this.hud.addKill(k, this.selfName));
      for (const tag of msg.inactiveTags || []) this.world.setTagVisible(tag, false);
      for (const p of msg.pickups || []) this.world.setPickupActive(p.id, p.on);
      this.chat.addSystem(`Welcome to ${msg.world.name} — ${msg.world.mode}. `
        + `Press Y to chat, Esc for the menu.`);
      setTimeout(() => {
        $('loading').classList.add('gone');
        setTimeout(() => { $('loading').style.display = 'none'; }, 500);
        this.running = true;
        this.input.requestLock();
      }, 250);
      this.setLoad(100, 'Ready');
      if (!this._loopStarted) { this._loopStarted = true; this.loop(); }
    });

    net.addEventListener('spawn', () => {
      this.viewYaw = net.state ? this.input.yaw : 0;
      this.input.yaw = this.spawnYaw ?? this.input.yaw;
      this.hud.setLastKiller(null);
    });

    net.addEventListener('roster', () => {
      for (const p of net.players.values()) this.ensureAvatar(p.profile);
      this.hud.renderScoreboard(this.scoreRows, net);
    });

    net.addEventListener('chat', (e) => this.chat.addMessage(e.detail));
    net.addEventListener('sys', (e) => this.chat.addSystem(e.detail.text));
    net.addEventListener('system', (e) => this.chat.addSystem(e.detail.text));

    net.addEventListener('kill', (e) => {
      const k = e.detail;
      this.hud.addKill(k, this.selfName);
      if (k.victim === this.selfName) {
        this.hud.setLastKiller(k.killer, k.weapon);
        this.effects.addShake(0.5);
      }
      if (k.killer === this.selfName) this.hud.hitMarker(true);
    });

    net.addEventListener('hit', (e) => {
      this.hud.hitMarker(false);
    });

    net.addEventListener('dmg', (e) => {
      const d = e.detail;
      this.hud.flashDamage();
      if (this.input.settings.shake) this.effects.addShake(Math.min(0.5, d.a / 90));
      if (d.from) {
        this.hud.damageDirection(d.from,
          [net.state.x, net.state.y, net.state.z], this.input.yaw);
      }
    });

    net.addEventListener('shot', (e) => {
      const remote = net.players.get(e.detail.i);
      if (remote) remote.muzzleUntil = performance.now() + 60;
    });

    net.addEventListener('fx', (e) => this.handleFx(e.detail));

    net.addEventListener('event', (e) => {
      const ev = e.detail;
      if (ev.t === 'announce') this.hud.announce(ev.text, ev.kind, ev.ttl);
      else if (ev.t === 'downed') this.chat.addSystem(`${ev.who} is down!`);
      else if (ev.t === 'revived') this.chat.addSystem(`${ev.by} revived ${ev.who}`);
      else if (ev.t === 'bledout') this.chat.addSystem(`${ev.who} bled out.`);
      else if (ev.t === 'wave') this.hud.announce(
        ev.boss ? `BOSS WAVE ${ev.wave}` : `WAVE ${ev.wave}`, 'wave', 3.5);
      else if (ev.t === 'bridge') this.world.setTagVisible('causeway', ev.extended);
      else if (ev.t === 'capture') this.effects.addShake(0.3);
    });

    net.addEventListener('part', (e) => {
      this.world.setTagVisible(e.detail.tag, e.detail.on);
    });
    net.addEventListener('pickup', (e) => {
      this.world.setPickupActive(e.detail.id, e.detail.on);
      if (!e.detail.on) {
        const p = this.world.pickups.get(e.detail.id);
        if (p) this.effects.spark(p.def.p[0], p.def.p[1], p.def.p[2],
          [0, 1, 0], '#ffffff', 8, 12);
      }
    });
    net.addEventListener('got', (e) => {
      const d = e.detail;
      this.hud.announce(d.label, 'objective', 1.6);
    });
    net.addEventListener('interact', (e) => {
      const d = e.detail;
      if (d.t === 'denied') this.hud.announce(d.reason, 'warn', 1.8);
      else if (d.t === 'weapon') this.hud.announce(`Purchased ${d.weapon}`, 'objective', 2);
      else if (d.t === 'ammo') this.hud.announce('Ammo refilled', 'objective', 1.5);
      else if (d.t === 'box') this.hud.announce(`The box grants… ${d.weapon}!`, 'victory', 3);
      else if (d.t === 'door') this.hud.announce('Blast door opened', 'objective', 2);
    });
    net.addEventListener('scores', (e) => {
      this.scoreRows = e.detail.rows;
      this.hud.renderScoreboard(this.scoreRows, net);
    });
    net.addEventListener('votes', (e) => {
      this.voteTally = e.detail.tally;
      for (const [w, c] of Object.entries(e.detail.tally)) {
        const el = document.querySelector(`[data-c="${w}"]`);
        if (el) el.textContent = c;
      }
    });
    net.addEventListener('roundend', (e) => {
      this.scoreRows = e.detail.scoreboard || [];
      this.showRoundEnd(e.detail);
    });
    net.addEventListener('enemy', (e) => {
      const d = e.detail;
      if (d.a === 'die' && d.p) {
        this.effects.debris(d.p[0], d.p[1] + 2, d.p[2], '#5c7a44', 12, 14, 0.5);
        this.effects.blood(d.p[0], d.p[1] + 2.5, d.p[2], '#6d8f4a');
      }
    });
    net.addEventListener('close', (e) => {
      this.running = false;
      this.chat.addSystem('Disconnected from the server.');
      $('loading').style.display = 'grid';
      $('loading').classList.remove('gone');
      this.fatal('Connection to the game server was lost.');
    });
    net.addEventListener('full', () => this.fatal('That server is full.'));
  }

  handleFx(fx) {
    const s = this.input.settings;
    if (fx.k === 'tracer') {
      const def = this.net.config?.weapons?.[fx.w];
      const color = def ? def.tracer : '#ffe27a';
      const isMine = fx.o === this.net.myId;
      const start = isMine && !this.thirdPerson
        ? this.muzzleWorld || fx.p : fx.p;
      this.effects.tracer(start, fx.d, fx.l, color,
        fx.w === 'railer' ? 0.16 : 0.09, fx.w === 'railer' ? 0.12 : 0.05);
      const hx = fx.p[0] + fx.d[0] * fx.l;
      const hy = fx.p[1] + fx.d[1] * fx.l;
      const hz = fx.p[2] + fx.d[2] * fx.l;
      if (fx.h === 'wall') this.effects.spark(hx, hy, hz, fx.n, '#ffd98a', 5, 16);
      else if (fx.h === 'flesh') this.effects.blood(hx, hy, hz);
    } else if (fx.k === 'launch') {
      this.effects.muzzle(fx.p[0], fx.p[1], fx.p[2], fx.d, '#ff8a4c', 1.4);
    } else if (fx.k === 'boom') {
      this.effects.explosion(fx.p[0], fx.p[1], fx.p[2], fx.r || 18);
    } else if (fx.k === 'impact') {
      this.effects.spark(fx.p[0], fx.p[1], fx.p[2], [0, 1, 0], '#ffd98a', 10, 18);
    } else if (fx.k === 'bounce') {
      this.effects.spark(fx.p[0], fx.p[1], fx.p[2], [0, 1, 0], '#ff6b5e', 4, 8);
    } else if (fx.k === 'pad' || fx.k === 'launch_pad') {
      const p = fx.i === this.net.myId
        ? [this.net.state.x, this.net.state.y, this.net.state.z] : null;
      if (p) this.effects.spark(p[0], p[1], p[2], [0, 1, 0], '#8ff0ff', 14, 20);
    } else if (fx.k === 'melee') {
      const t = fx.target === this.net.myId;
      if (t && s.shake) this.effects.addShake(0.35);
    }
  }

  ensureAvatar(profile) {
    if (!profile) return null;
    let model = this.avatars.get(profile.id);
    if (!model) {
      model = new AvatarModel(profile.avatar || {});
      this.avatars.set(profile.id, model);
    }
    return model;
  }

  showRoundEnd(detail) {
    const el = $('round-end');
    const rows = (detail.scoreboard || []).slice(0, 8);
    el.innerHTML = `<div class="pause-card" style="width:min(620px,92vw)">
      <div class="pause-head"><h2>${detail.winner
        ? esc(String(detail.winner).toUpperCase()) + ' WINS' : 'ROUND OVER'}</h2></div>
      <div class="pause-body">
        <table style="width:100%;border-collapse:collapse">
          <tr style="opacity:.6;font-size:.8em;text-transform:uppercase">
            <th style="text-align:left">Player</th><th>Score</th><th>K</th><th>D</th></tr>
          ${rows.map((r) => `<tr><td>${esc(r.name)}</td>
            <td style="text-align:center">${r.score}</td>
            <td style="text-align:center">${r.kills}</td>
            <td style="text-align:center">${r.deaths}</td></tr>`).join('')}
        </table>
        <div style="margin-top:12px;opacity:.6">Press V to vote for the next world.</div>
      </div></div>`;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 9000);
  }

  quit() {
    this.net.close();
    location.href = `/#/profile/${this.selfUserId || ''}`;
  }

  // ---------------------------------------------------------------- loop
  loop() {
    requestAnimationFrame(() => this.loop());
    const now = performance.now();
    let dt = (now - this.lastFrame) / 1000;
    this.lastFrame = now;
    if (dt > 0.25) dt = 0.25;
    this.fps = this.fps * 0.92 + (1 / Math.max(0.0005, dt)) * 0.08;

    if (!this.running) { this.renderer.beginDynamic(); this.renderer.render(dt); return; }

    this.acc += dt;
    let steps = 0;
    while (this.acc >= TICK && steps < 5) {
      this.acc -= TICK;
      this.tick(TICK);
      steps++;
    }
    if (steps >= 5) this.acc = 0;

    this.net.interpolate();
    this.effects.update(dt);
    this.render(dt);
  }

  tick(dt) {
    const net = this.net;
    const input = this.input;
    const cmd = input.sample();
    input.adsActive = cmd.ads;

    let buttons = 0;
    if (cmd.jump) buttons |= 1;
    if (cmd.sprint) buttons |= 2;
    if (cmd.crouch) buttons |= 4;
    if (cmd.fire) buttons |= 8;
    if (cmd.ads) buttons |= 16;
    if (cmd.use) buttons |= 32;

    const seq = net.sendInput({ ...cmd, buttons });

    if (net.alive && net.downed == null && !net.spectating) {
      const cfg = net.config || {};
      const w = net.weapons[net.slot];
      const def = w ? cfg.weapons?.[w.id] : null;
      let speed = cfg.walkSpeed || 16;
      if (cmd.sprint && cmd.moveZ < -0.1) speed = cfg.sprintSpeed || 24;
      if (cmd.crouch) speed *= 0.48;
      if (net.effects.speed) speed *= 1.55;
      if (net.carryingFlag) speed *= 0.86;
      if (cmd.ads && def) speed *= def.zoom > 2 ? 0.55 : 0.78;
      if (def) speed *= def.move_scale;
      let jump = cfg.jumpPower || 32;
      if (net.effects.gravity) jump *= 1.42;

      // forward = (-sin yaw, -cos yaw); moveZ is -1 when moving forward.
      const sy = Math.sin(cmd.yaw), cy = Math.cos(cmd.yaw);
      const wishX = cmd.moveZ * sy + cmd.moveX * cy;
      const wishZ = cmd.moveZ * cy - cmd.moveX * sy;
      const opts = { wantJump: cmd.jump, speed, jumpPower: jump,
                     gravity: cfg.gravity || 68 };
      moveCharacter(net.state, this.world.collision, wishX, wishZ, dt, opts);
      net.recordPrediction(seq, wishX, wishZ, dt, opts);
    }

    // auto fire
    const w = net.weapons[net.slot];
    const def = w ? net.config?.weapons?.[w.id] : null;
    if (cmd.fire && def && def.auto) this.fireOnce();

    // interaction prompt
    if (net.alive) {
      this.currentInteract = this.world.findInteractable(
        net.state.x, net.state.y, net.state.z, net.hud);
      this.hud.interactPrompt(this.currentInteract,
        keyShort(input.binds.interact));
    } else {
      this.hud.interactPrompt(null);
    }
  }

  fireOnce() {
    const net = this.net;
    if (!net.alive || net.downed != null || this.menu.open || this.chat.open) return;
    if (!this.input.locked) return;
    const w = net.weapons[net.slot];
    const def = w ? net.config?.weapons?.[w.id] : null;
    if (!def) return;
    const now = performance.now() / 1000;
    if (now - this.lastFireAt < def.shotInterval * 0.94) return;
    if (w.ammo <= 0) { net.reload(); return; }
    this.lastFireAt = now;

    const dir = this.aimDirection();
    net.fire([+dir[0].toFixed(4), +dir[1].toFixed(4), +dir[2].toFixed(4)]);

    // local feedback (server is still the authority on the actual hit)
    const kick = def.recoil * (this.input.adsActive ? 0.62 : 1);
    this.recoil += kick * 0.016;
    this.recoilYaw += (Math.random() - 0.5) * kick * 0.008;
    if (this.input.settings.shake) this.effects.addShake(kick * 0.06);
    const m = this.muzzleWorld || [net.state.x, net.state.y + 4, net.state.z];
    this.effects.muzzle(m[0], m[1], m[2], dir, def.tracer, def.model === 'launcher' ? 1.6 : 1);
  }

  aimDirection() {
    const yaw = this.input.yaw, pitch = this.input.pitch;
    const cp = Math.cos(pitch);
    return [-Math.sin(yaw) * cp, Math.sin(pitch), -Math.cos(yaw) * cp];
  }

  // -------------------------------------------------------------- render
  render(dt) {
    const net = this.net;
    const r = this.renderer;
    const s = this.input.settings;
    r.beginDynamic();

    this.recoil = damp(this.recoil, 0, 9, dt);
    this.recoilYaw = damp(this.recoilYaw, 0, 8, dt);

    const speed = Math.hypot(net.state.vx, net.state.vz);
    if (s.viewBob && net.state.onGround) {
      this.bob += dt * (2.6 + speed * 0.42);
    }
    const bobAmt = s.viewBob ? Math.min(1, speed / 16) : 0;

    const eyeY = net.state.y + (net.config?.playerHeight || 5) - 0.85
      + (this.input.isDown('crouch') ? -1.1 : 0);
    const yaw = this.input.yaw + this.recoilYaw;
    const pitch = clamp(this.input.pitch + this.recoil, -1.54, 1.54);

    let camPos;
    let camYaw = yaw, camPitch = pitch;
    const followTarget = (!net.alive && this.spectateTarget)
      ? this.spectateTarget : null;
    const baseX = followTarget ? followTarget.x : net.state.x;
    const baseZ = followTarget ? followTarget.z : net.state.z;
    const baseY = followTarget ? followTarget.y + 4.2 : eyeY;

    if (this.freeCam) {
      camPos = [net.state.x, net.state.y, net.state.z];
    } else if (this.thirdPerson || !net.alive) {
      this.camDist = damp(this.camDist, this.camDistTarget, 8, dt);
      const cp = Math.cos(camPitch);
      const back = [Math.sin(camYaw) * cp, -Math.sin(camPitch), Math.cos(camYaw) * cp];
      let dist = this.camDist;
      const hit = this.world.collision.raycast(baseX, baseY + 1.2, baseZ,
        back[0], back[1], back[2], dist + 1.2);
      if (hit) dist = Math.max(2.2, hit.t - 1.0);
      camPos = [baseX + back[0] * dist, baseY + 1.2 + back[1] * dist,
                baseZ + back[2] * dist];
    } else {
      const bobX = Math.sin(this.bob) * 0.09 * bobAmt;
      const bobY = Math.abs(Math.cos(this.bob)) * 0.07 * bobAmt;
      const right = [Math.cos(camYaw), 0, -Math.sin(camYaw)];
      camPos = [baseX + right[0] * bobX, baseY + bobY, baseZ + right[2] * bobX];
    }

    const shake = s.shake ? this.effects.shakeVec : [0, 0];
    const def = net.weapons[net.slot]
      ? net.config?.weapons?.[net.weapons[net.slot].id] : null;
    const zoom = this.input.adsActive && def ? def.zoom : 1;
    const fov = s.fov / (this.thirdPerson ? 1 : zoom);
    r.setCamera(camPos, camYaw + shake[0], camPitch + shake[1], 0, fov);

    // ---- world ----
    if (net.lavaY !== undefined && net.hud?.kind === 'lavarise') {
      this.world.lavaY = net.lavaY;
    }
    this.world.drawDynamic(dt, net.hud);

    // ---- characters ----
    this.drawSelf(dt, camPos, camYaw, camPitch);
    this.drawRemotes(dt);
    this.drawEnemies(dt);
    this.drawProjectiles();

    if (!this.thirdPerson && net.alive && net.downed == null && !this.freeCam) {
      this.drawViewModel(camPos, camYaw, camPitch, dt, bobAmt);
    } else {
      this.muzzleWorld = null;
    }

    this.effects.draw();
    r.render(dt);

    // ---- HUD ----
    this.hud.updateVitals(net);
    this.hud.updateMode(net.hud, net);
    this.hud.updateNameplates(r, net, camPos);
    this.hud.updateRespawn(net);
    this.hud.updateRevive(net);
    this.hud.crosshairSpread(speed > 6 || !net.state.onGround);
    if (this.holdScoreboard && performance.now() - (this._sbAt || 0) > 900) {
      this._sbAt = performance.now();
      net.requestScoreboard();
    }
    if (s.showFps) {
      $('perf').textContent =
        `fps ${this.fps.toFixed(0)}  ping ${(net.ping * 1000).toFixed(0)}ms\n`
        + `draws ${r.stats.draws}  inst ${r.stats.instances}\n`
        + `pos ${net.state.x.toFixed(1)} ${net.state.y.toFixed(1)} ${net.state.z.toFixed(1)}\n`
        + `corrections ${net.reconciliations}  players ${net.players.size + 1}`;
    }
  }

  drawSelf(dt, camPos, camYaw, camPitch) {
    const net = this.net;
    if (this.freeCam) return;
    if (!net.alive && !net.downed) return;
    const model = this.ensureAvatar(net.me);
    if (!model) return;
    const speed = Math.hypot(net.state.vx, net.state.vz);
    model.update(dt, {
      speed, onGround: net.state.onGround, holding: true,
      crouch: this.input.isDown('crouch'), pitch: this.input.pitch,
      dead: net.downed != null,
    });
    const firstPerson = !this.thirdPerson && net.alive;
    if (!firstPerson) {
      model.draw(this.renderer, {
        x: net.state.x, y: net.state.y, z: net.state.z,
        yaw: this.input.yaw, pitch: this.input.pitch,
      });
      this.drawHeldWeapon(model, net.state.x, net.state.y, net.state.z,
        this.input.yaw, this.input.pitch, net.weapons[net.slot]?.id,
        net.me?.skin);
    }
    this.drawShadow(net.state.x, net.state.y, net.state.z);
  }

  drawRemotes(dt) {
    const net = this.net;
    for (const remote of net.players.values()) {
      const r = remote.render;
      if (!r.alive && r.downed == null) continue;
      const model = this.ensureAvatar(remote.profile);
      model.update(dt, {
        speed: r.speed, onGround: r.onGround, holding: !!r.weapon,
        crouch: r.crouch, pitch: r.pitch, dead: r.downed != null,
      });
      model.draw(this.renderer, {
        x: r.x, y: r.y, z: r.z, yaw: r.yaw, pitch: r.pitch,
        glow: r.shield ? 0.25 : 0,
      });
      if (r.weapon) {
        this.drawHeldWeapon(model, r.x, r.y, r.z, r.yaw, r.pitch, r.weapon,
                            remote.profile.skin);
      }
      if (remote.muzzleUntil && performance.now() < remote.muzzleUntil) {
        const cp = Math.cos(r.pitch);
        const dir = [-Math.sin(r.yaw) * cp, Math.sin(r.pitch), -Math.cos(r.yaw) * cp];
        this.effects.muzzle(r.x + dir[0] * 2, r.y + 4.2 + dir[1] * 2,
                            r.z + dir[2] * 2, dir, '#ffe27a', 0.9);
        remote.muzzleUntil = 0;
      }
      this.drawShadow(r.x, r.y, r.z);
    }
  }

  drawEnemies(dt) {
    const r = this.renderer;
    for (const en of this.net.enemies.values()) {
      if (en.x === undefined) continue;
      const boss = en.kind === 'brute';
      const s = boss ? 1.32 : 1;
      const swing = Math.sin((en.anim || 0)) * 0.7;
      const skin = boss ? '#5a7a3a' : '#79994f';
      const cloth = boss ? '#3a2a20' : '#4b5b39';
      const cy = Math.cos(en.yaw), sy = Math.sin(en.yaw);
      const put = (lx, ly, lz, w, h, d, color, rx = 0) => {
        r.add('dynamic', 'box', 'studs',
          en.x + lx * cy + lz * sy, en.y + ly, en.z - lx * sy + lz * cy,
          w, h, d, color, { ry: en.yaw, rx });
      };
      put(-0.5 * s, 0.95 * s, 0, 0.95 * s, 1.9 * s, 0.95 * s, cloth, swing);
      put(0.5 * s, 0.95 * s, 0, 0.95 * s, 1.9 * s, 0.95 * s, cloth, -swing);
      put(0, 2.85 * s, 0, 1.95 * s, 1.9 * s, 0.95 * s, cloth);
      put(-1.45 * s, 2.7 * s, -0.7 * s, 0.95 * s, 1.9 * s, 0.95 * s, skin, -1.25);
      put(1.45 * s, 2.7 * s, -0.7 * s, 0.95 * s, 1.9 * s, 0.95 * s, skin, -1.25);
      put(0, 4.35 * s, 0, 1.25 * s, 1.1 * s, 1.25 * s, skin);
      // eyes
      r.add('dynamic', 'box', 'neon',
        en.x - 0.28 * cy - 0.63 * sy * s, en.y + 4.45 * s, en.z + 0.28 * sy - 0.63 * cy * s,
        0.18, 0.16, 0.06, boss ? '#ff4040' : '#ffe14f',
        { ry: en.yaw, glow: 1 });
      r.add('dynamic', 'box', 'neon',
        en.x + 0.28 * cy - 0.63 * sy * s, en.y + 4.45 * s, en.z - 0.28 * sy - 0.63 * cy * s,
        0.18, 0.16, 0.06, boss ? '#ff4040' : '#ffe14f',
        { ry: en.yaw, glow: 1 });
      if (boss) {
        r.add('dynamic', 'sphere', 'neon', en.x, en.y + 6.6, en.z, 1.2, 1.2, 1.2,
          '#ff4040', { glow: 1, alpha: 0.55 });
      }
      this.drawShadow(en.x, en.y, en.z, boss ? 4.2 : 3.2);
    }
  }

  drawProjectiles() {
    const r = this.renderer;
    for (const p of this.net.projectiles.values()) {
      const def = this.net.config?.weapons?.[p.w];
      const color = def ? def.tracer : '#ff8a4c';
      if (p.w === 'rocket') {
        const yaw = Math.atan2(-p.v[0], -p.v[2]);
        const pitch = Math.asin(clamp(p.v[1] / (Math.hypot(...p.v) || 1), -1, 1));
        r.add('dynamic', 'cylinder', 'metal', p.p[0], p.p[1], p.p[2],
          0.55, 2.4, 0.55, '#c8ced6', { ry: yaw, rx: -pitch + Math.PI / 2 });
        r.add('dynamic', 'cone', 'metal', p.p[0], p.p[1], p.p[2],
          0.7, 1.0, 0.7, '#c0392b', { ry: yaw, rx: -pitch + Math.PI / 2 });
        r.add('dynamic', 'sphere', 'neon', p.p[0] - p.v[0] * 0.012,
          p.p[1] - p.v[1] * 0.012, p.p[2] - p.v[2] * 0.012,
          1.3, 1.3, 1.3, '#ff8a4c', { glow: 1, alpha: 0.7 });
      } else {
        r.add('dynamic', 'sphere', 'neon', p.p[0], p.p[1], p.p[2],
          1.1, 1.1, 1.1, color, { glow: 0.9 });
      }
    }
  }

  drawShadow(x, y, z, size = 3.4) {
    const hit = this.world.collision.raycast(x, y + 0.6, z, 0, -1, 0, 40);
    if (!hit) return;
    const gy = y + 0.6 - hit.t;
    const fade = 1 - Math.min(1, hit.t / 40);
    this.renderer.add('dynamic', 'cylinder', 'smooth', x, gy + 0.06, z,
      size * (0.6 + fade * 0.6), 0.05, size * (0.6 + fade * 0.6),
      '#0a0d12', { alpha: 0.30 * fade });
  }

  drawHeldWeapon(model, x, y, z, yaw, pitch, weaponId, skinName) {
    if (!weaponId || !model) return;
    const spec = modelFor(weaponId, this.net.config?.weapons);
    const skin = WEAPON_SKINS[skinName] || WEAPON_SKINS.default;
    const hand = model.handOffset(pitch);
    const scale = 1.15;
    // Slide the grip a little further along the arm so the weapon reads as
    // held rather than floating at the wrist.
    const reach = 0.45;
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const lx = hand.x;
    const ly = hand.y + sp * reach;
    const lz = hand.z - cp * reach;
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const wx = x + lx * cy + lz * sy;
    const wy = y + ly;
    const wz = z - lx * sy + lz * cy;
    this.drawWeaponParts(spec, skin, wx, wy, wz, yaw, pitch, scale);
  }

  drawWeaponParts(spec, skin, ox, oy, oz, yaw, pitch, scale, handColor) {
    const r = this.renderer;
    const cy = Math.cos(yaw), sy = Math.sin(yaw);
    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const place = (lx, ly, lz) => {
      // rotate around X (pitch) then Y (yaw)
      const py = ly * cp - lz * sp;
      const pz = ly * sp + lz * cp;
      return [ox + lx * cy + pz * sy, oy + py, oz - lx * sy + pz * cy];
    };
    const parts = handColor
      ? spec.parts.concat(handParts(spec, handColor)) : spec.parts;
    for (const part of parts) {
      const [lx, ly, lz] = part.pos;
      const [w, h, d] = part.size;
      const [wx, wy, wz] = place(lx * scale, ly * scale, lz * scale);
      r.add('dynamic', part.shape, part.glow ? 'neon' : 'metal',
        wx, wy, wz, w * scale, h * scale, d * scale,
        part.tint === 'hand' ? handColor : (skin[part.tint] || skin.body), {
          ry: yaw + ((part.ry || 0) * Math.PI / 180),
          rx: pitch + ((part.rx || 0) * Math.PI / 180),
          rz: (part.rz || 0) * Math.PI / 180,
          glow: part.glow || skin.glow, alpha: part.alpha != null ? part.alpha : 1,
        });
    }
    const [mx, my, mz] = spec.muzzle;
    return place(mx * scale, my * scale, mz * scale);
  }

  drawViewModel(camPos, yaw, pitch, dt, bobAmt) {
    const net = this.net;
    const w = net.weapons[net.slot];
    if (!w) { this.muzzleWorld = null; return; }
    const spec = modelFor(w.id, net.config?.weapons);
    const skin = WEAPON_SKINS[net.me?.skin] || WEAPON_SKINS.default;
    const ads = this.input.adsActive;
    this.adsBlend = damp(this.adsBlend || 0, ads ? 1 : 0, 14, dt);
    const a = this.adsBlend;

    // The view model lives in world space a fixed distance in front of the
    // camera, so these numbers are tuned against the projected size: at
    // distance d the screen spans 2*d*tan(fov/2) studs.
    const VM = {
      scale: 0.46,
      dist: 1.36,
      right: 0.36,
      down: -0.30,
      adsRight: 0.0,
      adsDown: -0.185,
      adsDist: 1.18,
    };

    const cp = Math.cos(pitch), sp = Math.sin(pitch);
    const fwd = [-Math.sin(yaw) * cp, sp, -Math.cos(yaw) * cp];
    const right = [Math.cos(yaw), 0, -Math.sin(yaw)];
    const up = [Math.sin(yaw) * sp, cp, Math.cos(yaw) * sp];

    const sway = Math.sin(this.bob) * 0.035 * bobAmt * (1 - a);
    const swayY = Math.abs(Math.cos(this.bob)) * 0.026 * bobAmt * (1 - a);
    const rx = VM.right + (VM.adsRight - VM.right) * a + sway;
    const ry = VM.down + (VM.adsDown - VM.down) * a + swayY
      - this.recoil * 0.30;
    const rz = VM.dist + (VM.adsDist - VM.dist) * a - this.recoil * 0.22;

    const ox = camPos[0] + right[0] * rx + up[0] * ry + fwd[0] * rz;
    const oy = camPos[1] + right[1] * rx + up[1] * ry + fwd[1] * rz;
    const oz = camPos[2] + right[2] * rx + up[2] * ry + fwd[2] * rz;
    const model = this.ensureAvatar(net.me);
    const handColor = model ? model.colorOf('rightArm') : '#f3d64e';
    this.muzzleWorld = this.drawWeaponParts(spec, skin, ox, oy, oz, yaw,
                                            pitch, VM.scale, handColor);
  }

}

/** A fist on the grip plus a forearm running back out of frame. */
function handParts(spec, color) {
  const g = spec.grip || [0, -0.26, 0];
  return [
    { shape: 'box', pos: [g[0], g[1] - 0.10, g[2] + 0.02],
      size: [0.44, 0.46, 0.48], tint: 'hand' },
    { shape: 'box', pos: [g[0] + 0.17, g[1] - 0.30, g[2] + 0.52],
      size: [0.42, 0.42, 0.98], tint: 'hand', rx: -12, ry: -6 },
  ];
}

function keyShort(code) {
  return String(code || 'E').replace(/^Key/, '').replace(/^Digit/, '')
    .replace('Space', 'Space').slice(0, 6);
}

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

const frame = () => new Promise((r) => requestAnimationFrame(r));

const game = new Game();
window.__rblxx = game;
game.start().catch((e) => {
  console.error(e);
  game.fatal(e.message || 'Something went wrong starting the game.');
});
