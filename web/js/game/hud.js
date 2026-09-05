// Everything drawn in DOM on top of the canvas: vitals, mode HUD, name
// plates, kill feed, announcements, scoreboard, respawn screen.

const $ = (id) => document.getElementById(id);

const WEAPON_SYMBOL = {
  blaster: '⬥', rifle: '➤', scatter: '✦', railer: '─▸',
  rocket: '➶', superball: '●', zapper: '⚡', mender: '✚',
  fall: '↓', void: '⬇', lava: '♨', zombie: '☠',
  turret: '⚙', explosion: '✹',
};
const TEAM_CLASS = ['red', 'blue', 'sun', 'moon', 'survivor', 'neutral'];

export class Hud {
  constructor(net, settings) {
    this.net = net;
    this.settings = settings;
    this.plateEls = new Map();
    this.markerEls = new Map();
    this.killfeed = [];
    this.announcements = [];
    this.bubbles = new Map();
    this.lastHp = 100;
    this.scoreboardOpen = false;
    this._proj = { x: 0, y: 0, visible: false, depth: 0 };
    this.setHudScale(settings.hudScale);
    this.setCrosshair(settings.crosshairColor, settings.crosshairStyle);
  }

  setHudScale(scale) {
    $('overlay').style.setProperty('--hud-scale', scale || 1);
  }

  setCrosshair(color, style) {
    const xh = $('crosshair');
    xh.style.setProperty('--xh', color || '#7cff9e');
    xh.classList.toggle('hidden-xh', style === 'none');
    xh.querySelector('.dot').style.display = style === 'cross' ? 'none' : 'block';
    xh.querySelectorAll('.arm').forEach((a) => {
      a.style.display = style === 'dot' ? 'none' : 'block';
    });
  }

  // ------------------------------------------------------------- vitals
  updateVitals(net) {
    const hp = Math.max(0, Math.round(net.health));
    const num = $('hp-num');
    num.textContent = hp;
    num.classList.toggle('warn', hp <= 55 && hp > 25);
    num.classList.toggle('crit', hp <= 25);
    $('hp-label').textContent = `${hp} / 100`;
    const bar = $('hp-bar');
    bar.style.width = `${Math.max(0, Math.min(100, hp))}%`;
    bar.parentElement.classList.toggle('low', hp <= 55 && hp > 25);
    bar.parentElement.classList.toggle('crit', hp <= 25);
    $('lowhp').style.display = hp > 0 && hp <= 25 ? 'block' : 'none';

    const armorWrap = $('armor-wrap');
    if (net.armor > 0.5) {
      armorWrap.style.display = 'block';
      $('armor-bar').style.width = `${Math.min(100, net.armor / 60 * 100)}%`;
    } else armorWrap.style.display = 'none';

    const w = net.weapons[net.slot];
    if (w) {
      const def = net.config?.weapons?.[w.id];
      $('weapon-name').textContent = def ? def.name : w.id;
      const mag = $('ammo-mag');
      mag.textContent = w.ammo;
      mag.classList.toggle('low', w.ammo > 0 && w.ammo <= Math.max(1, (def?.mag || 10) * 0.3));
      mag.classList.toggle('empty', w.ammo === 0);
      $('ammo-reserve').textContent = w.reserve < 0 ? '/ ∞' : `/ ${w.reserve}`;
    }
    const rl = net.reloadLeft || 0;
    const rw = $('reload-wrap');
    if (rl > 0.02 && w) {
      const def = net.config?.weapons?.[w.id];
      const total = def ? def.reload_time : 2;
      rw.style.display = 'block';
      $('reload-bar').style.width = `${Math.max(0, (1 - rl / total)) * 100}%`;
    } else rw.style.display = 'none';

    this.updateWeaponWheel(net);
    this.updateEffects(net);

    if (hp < this.lastHp - 0.5 && hp > 0) this.flashDamage();
    this.lastHp = hp;
  }

  updateWeaponWheel(net) {
    const wheel = $('weapon-wheel');
    const sig = net.weapons.map((w) => w.id).join(',') + '|' + net.slot;
    if (this._wheelSig === sig) return;
    this._wheelSig = sig;
    wheel.innerHTML = '';
    net.weapons.forEach((w, i) => {
      const def = net.config?.weapons?.[w.id];
      const el = document.createElement('div');
      el.className = 'wslot' + (i === net.slot ? ' active' : '');
      el.innerHTML = `<span>${def ? def.name : w.id}</span>
        <span class="k">${i + 1}</span>`;
      wheel.appendChild(el);
    });
  }

  updateEffects(net) {
    const strip = $('effects-strip');
    const eff = net.effects || {};
    const keys = Object.keys(eff);
    const sig = keys.map((k) => `${k}:${Math.ceil(eff[k])}`).join(',');
    if (this._effSig === sig) return;
    this._effSig = sig;
    strip.innerHTML = '';
    const META = {
      speed: ['Speed Coil', '#38d0ff'], gravity: ['Gravity Coil', '#b58cff'],
      damage: ['Damage Boost', '#ff7a2a'],
    };
    for (const k of keys) {
      const [label, color] = META[k] || [k, '#ffffff'];
      const el = document.createElement('div');
      el.className = 'eff';
      el.style.borderLeftColor = color;
      el.style.color = color;
      el.innerHTML = `${label} <span style="opacity:.75">${Math.ceil(eff[k])}s</span>`;
      strip.appendChild(el);
    }
  }

  flashDamage() {
    const v = $('vignette');
    v.classList.add('hurt');
    setTimeout(() => v.classList.remove('hurt'), 90);
  }

  damageDirection(worldPos, camPos, camYaw) {
    const dx = worldPos[0] - camPos[0];
    const dz = worldPos[2] - camPos[2];
    const angle = Math.atan2(dx, -dz);
    const rel = angle - camYaw;
    const el = document.createElement('div');
    el.className = 'dmg-dir';
    el.style.transform = `rotate(${-rel}rad)`;
    el.innerHTML = '<i></i>';
    $('damage-dirs').appendChild(el);
    setTimeout(() => el.remove(), 1150);
  }

  hitMarker(kill) {
    if (!this.settings.hitMarkers) return;
    const hm = $('hitmarker');
    hm.classList.remove('show');
    hm.classList.toggle('kill', !!kill);
    void hm.offsetWidth;
    hm.classList.add('show');
  }

  crosshairSpread(on) {
    $('crosshair').classList.toggle('spread', on);
  }

  // -------------------------------------------------------------- feed
  addKill(entry, myName) {
    const el = document.createElement('div');
    const involved = entry.killer === myName || entry.victim === myName;
    el.className = 'kf' + (involved ? ' you-involved' : '')
      + (!entry.killer ? ' self-kill' : '');
    const sym = WEAPON_SYMBOL[entry.weapon] || '✖';
    const kt = TEAM_CLASS.includes(entry.killerTeam) ? entry.killerTeam : 'neutral';
    const vt = TEAM_CLASS.includes(entry.victimTeam) ? entry.victimTeam : 'neutral';
    const killerHtml = entry.killer
      ? `<span class="who ${kt}${entry.killer === myName ? ' me' : ''}">${esc(entry.killer)}</span>`
      : '<span class="who neutral">—</span>';
    el.innerHTML = `${killerHtml}
      ${entry.headshot ? '<span class="hs">⚑</span>' : ''}
      <span class="wsym">${sym}</span>
      <span class="who ${vt}${entry.victim === myName ? ' me' : ''}">${esc(entry.victim)}</span>`;
    const feed = $('killfeed');
    feed.appendChild(el);
    this.killfeed.push(el);
    const max = this.settings.killFeedSize || 6;
    while (this.killfeed.length > max) {
      const old = this.killfeed.shift();
      old.classList.add('fading');
      setTimeout(() => old.remove(), 500);
    }
    setTimeout(() => {
      if (!el.isConnected) return;
      el.classList.add('fading');
      setTimeout(() => el.remove(), 500);
      const i = this.killfeed.indexOf(el);
      if (i >= 0) this.killfeed.splice(i, 1);
    }, 8500);
  }

  announce(text, kind = 'info', ttl = 4) {
    const el = document.createElement('div');
    el.className = `announce ${kind}`;
    el.textContent = text;
    $('announcements').appendChild(el);
    setTimeout(() => {
      el.classList.add('fading');
      setTimeout(() => el.remove(), 500);
    }, ttl * 1000);
    const box = $('announcements');
    while (box.children.length > 4) box.firstChild.remove();
  }

  // ----------------------------------------------------------- mode HUD
  updateMode(hud, net) {
    const root = $('mode-hud');
    if (!hud || !hud.kind) { root.innerHTML = ''; return; }
    const sig = JSON.stringify([hud.kind, hud.teams, hud.phase, hud.wave,
      hud.enemiesLeft, hud.owner, hud.round, hud.alive,
      hud.flags && Object.entries(hud.flags).map(([k, v]) => [k, v.state, v.carrier]),
      hud.bridge && hud.bridge.owner]);
    const clockOnly = sig === this._modeSig;
    if (!clockOnly) { this._modeSig = sig; root.innerHTML = this._modeHtml(hud, net); }
    this._updateClocks(hud);
  }

  _modeHtml(hud, net) {
    const time = (s) => {
      s = Math.max(0, s | 0);
      return `${(s / 60) | 0}:${String(s % 60).padStart(2, '0')}`;
    };
    if (hud.kind === 'tdm' || hud.kind === 'ctf' || hud.kind === 'koth') {
      const teams = hud.teams || [];
      const best = Math.max(...teams.map((t) => t.score), 0);
      const strip = `<div class="score-strip">
        ${teams.map((t, i) => (i === 1 ? `<div class="mid">
            <span class="clock" data-clock>${time(hud.timeLeft)}</span>
            <span class="lbl">${hud.scoreLimit ? 'to ' + hud.scoreLimit : 'time'}</span>
          </div>` : '') + `<div class="tm ${t.id}${t.score === best && best > 0 ? ' leading' : ''}">${t.score}</div>`).join('')}
      </div>`;
      let extra = '';
      if (hud.kind === 'koth') {
        const cap = hud.capture || 0;
        const w = Math.abs(cap) * 50;
        const left = cap >= 0 ? 50 : 50 - w;
        const color = cap >= 0 ? '#f0a52a' : '#8a6bd8';
        extra = `<div class="objective-bar"><i style="left:${left}%;width:${w}%;background:${color}"></i></div>
          <div class="objective-note">${hud.contested ? '⚠ BEACON CONTESTED'
            : hud.owner ? `${hud.owner.toUpperCase()} holds the Beacon`
              : 'Beacon neutral'} · moves in ${Math.ceil(hud.moveIn || 0)}s</div>`;
      } else if (hud.kind === 'ctf') {
        const f = hud.flags || {};
        const state = (t) => {
          const s = f[t];
          if (!s) return '';
          if (s.state === 'carried') return `⚑ taken by ${esc(s.carrier || '?')}`;
          if (s.state === 'dropped') return '⚑ dropped!';
          return '⚑ at base';
        };
        const br = hud.bridge || {};
        extra = `<div class="objective-note">
          <span style="color:#ff8072">RED ${state('red')}</span> &nbsp;·&nbsp;
          <span style="color:#74b7ff">BLUE ${state('blue')}</span></div>
          <div class="objective-note">Causeway: ${br.extended
            ? `<b style="color:${br.owner === 'red' ? '#ff8072' : '#74b7ff'}">${(br.owner || '').toUpperCase()} EXTENDED</b>`
            : `${Math.round((br.progress || 0) * 100)}% ${br.owner ? '(' + br.owner + ')' : ''}`}</div>`;
      }
      return strip + extra;
    }
    if (hud.kind === 'outbreak') {
      const phase = hud.phase;
      return `<div class="score-strip">
        <div class="tm survivor" style="background:linear-gradient(180deg,rgba(63,169,216,.85),rgba(30,110,150,.85))">
          ${hud.wave || 0}</div>
        <div class="mid"><span class="clock">${phase === 'wave'
          ? hud.enemiesLeft + ' left' : phase === 'over' ? 'OVER'
            : Math.ceil(hud.nextIn) + 's'}</span>
          <span class="lbl">${phase === 'wave' ? 'hostiles'
            : phase === 'over' ? 'restarting' : 'next wave'}</span></div>
        <div class="tm" style="background:rgba(0,0,0,.4);font-size:1em;min-width:96px">
          <div style="font-size:.62em;opacity:.7">POINTS</div>
          <div>${(net.score.points || 0).toLocaleString()}</div></div>
      </div>
      <div class="objective-note">Best wave reached: ${hud.bestWave || 0}</div>`;
    }
    if (hud.kind === 'lavarise') {
      return `<div class="score-strip">
        <div class="tm" style="background:linear-gradient(180deg,rgba(255,122,42,.85),rgba(180,70,15,.85))">
          ${hud.alive}</div>
        <div class="mid"><span class="clock">${hud.phase === 'playing'
          ? (hud.grace > 0 ? Math.ceil(hud.grace) + 's' : 'RISING')
          : Math.ceil(hud.nextIn) + 's'}</span>
          <span class="lbl">${hud.phase === 'playing'
            ? (hud.grace > 0 ? 'grace' : `+${hud.riseRate.toFixed(1)}/s`)
            : 'next round'}</span></div>
        <div class="tm" style="background:rgba(0,0,0,.4);min-width:86px">
          <div style="font-size:.62em;opacity:.7">ROUND</div><div>${hud.round}</div></div>
      </div>
      <div class="objective-note">Lava at ${Math.round(hud.lava)} studs
        ${hud.lastWinner ? ' · last winner: ' + esc(hud.lastWinner) : ''}</div>`;
    }
    return '';
  }

  _updateClocks(hud) {
    const el = $('mode-hud').querySelector('[data-clock]');
    if (el && hud.timeLeft != null) {
      const s = Math.max(0, hud.timeLeft | 0);
      el.textContent = `${(s / 60) | 0}:${String(s % 60).padStart(2, '0')}`;
      el.style.color = s < 30 ? '#ff8072' : '';
    }
  }

  // --------------------------------------------------------- nameplates
  updateNameplates(renderer, net, camPos) {
    const root = $('nameplates');
    const alive = new Set();
    const show = this.settings.showNames;
    const proj = this._proj;

    const place = (key, wx, wy, wz, build, update, maxDist = 340) => {
      const dist = Math.hypot(wx - camPos[0], wy - camPos[1], wz - camPos[2]);
      if (dist > maxDist) return;
      renderer.projectToScreen(wx, wy, wz, proj);
      if (!proj.visible) return;
      alive.add(key);
      let el = this.plateEls.get(key);
      if (!el) { el = build(); root.appendChild(el); this.plateEls.set(key, el); }
      const scale = Math.max(0.42, Math.min(1.25, 34 / Math.max(6, dist) * 1.9));
      el.style.transform =
        `translate(${proj.x.toFixed(1)}px, ${proj.y.toFixed(1)}px) translate(-50%,-100%) scale(${scale.toFixed(3)})`;
      el.style.opacity = dist > maxDist * 0.82
        ? String(1 - (dist - maxDist * 0.82) / (maxDist * 0.18)) : '1';
      update(el, dist);
    };

    if (show) {
      for (const remote of net.players.values()) {
        const r = remote.render;
        if (!r.alive && !r.downed) continue;
        const team = remote.profile.team;
        const mine = net.me && net.me.team;
        const rel = team === 'neutral' || !mine ? ''
          : (team === mine ? ' ally' : ' enemy');
        place(`p${remote.id}`, r.x, r.y + 6.4, r.z, () => {
          const el = document.createElement('div');
          el.className = 'nameplate' + rel;
          el.innerHTML = `<div class="nm"></div>
            <div class="hpbar" style="width:64px"><i></i></div>
            <div class="tagline"></div>`;
          return el;
        }, (el) => {
          el.className = 'nameplate' + rel + (r.downed != null ? ' downed' : '');
          const nm = el.querySelector('.nm');
          const flag = r.flag ? ' <span class="flagmark">⚑</span>' : '';
          const label = esc(remote.profile.name) + flag;
          if (nm.dataset.v !== label) { nm.innerHTML = label; nm.dataset.v = label; }
          const bar = el.querySelector('.hpbar');
          const hp = Math.max(0, Math.min(100, r.hp || 0));
          bar.firstElementChild.style.width = hp + '%';
          bar.classList.toggle('low', hp <= 55 && hp > 25);
          bar.classList.toggle('crit', hp <= 25);
          const tag = el.querySelector('.tagline');
          const txt = r.downed != null ? 'DOWNED — hold E to revive' : '';
          if (tag.textContent !== txt) tag.textContent = txt;
        });
      }
    }

    // objective markers
    const hud = net.hud || {};
    if (hud.kind === 'koth' && hud.beaconPos) {
      const [bx, by, bz] = hud.beaconPos;
      place('beacon', bx, by + 26, bz, () => {
        const el = document.createElement('div');
        el.className = 'world-marker';
        el.innerHTML = '<div class="mi">◉</div><div class="mn">BEACON</div><div class="md"></div>';
        return el;
      }, (el, dist) => {
        el.querySelector('.md').textContent = `${Math.round(dist)} studs`;
        el.style.color = hud.owner === 'sun' ? '#ffc65e'
          : hud.owner === 'moon' ? '#b79bff' : '#ffffff';
      }, 3000);
    }
    if (hud.kind === 'ctf' && hud.flags) {
      for (const [team, f] of Object.entries(hud.flags)) {
        place(`flag${team}`, f.pos[0], f.pos[1] + 6, f.pos[2], () => {
          const el = document.createElement('div');
          el.className = 'world-marker';
          el.innerHTML = '<div class="mi">⚑</div><div class="mn"></div><div class="md"></div>';
          return el;
        }, (el, dist) => {
          el.style.color = team === 'red' ? '#ff8072' : '#74b7ff';
          el.querySelector('.mn').textContent = `${team.toUpperCase()} FLAG`;
          el.querySelector('.md').textContent =
            f.state === 'carried' ? esc(f.carrier || '') : `${Math.round(dist)} studs`;
        }, 3000);
      }
    }
    if (hud.kind === 'outbreak') {
      for (const d of hud.doors || []) {
        if (d.open) continue;
        place(`door${d.id}`, d.p[0], d.p[1] + 8, d.p[2], () => {
          const el = document.createElement('div');
          el.className = 'world-marker';
          el.style.color = '#ffd166';
          el.innerHTML = '<div class="mi">⚿</div><div class="md"></div>';
          return el;
        }, (el) => { el.querySelector('.md').textContent = `${d.cost} pts`; }, 220);
      }
      for (const w of hud.wallbuys || []) {
        if (!w.open) continue;
        place(`wb${w.id}`, w.p[0], w.p[1] + 6, w.p[2], () => {
          const el = document.createElement('div');
          el.className = 'world-marker';
          el.style.color = '#7cff9e';
          el.innerHTML = '<div class="mi">✣</div><div class="mn"></div><div class="md"></div>';
          return el;
        }, (el) => {
          el.querySelector('.mn').textContent = w.weapon.toUpperCase();
          el.querySelector('.md').textContent = `${w.cost} pts`;
        }, 160);
      }
    }

    // chat bubbles
    for (const [id, bubble] of this.bubbles) {
      if (performance.now() > bubble.until) { this.bubbles.delete(id); continue; }
      const remote = net.players.get(id);
      if (!remote) continue;
      const r = remote.render;
      place(`b${id}`, r.x, r.y + 8.4, r.z, () => {
        const el = document.createElement('div');
        el.className = 'chat-bubble';
        return el;
      }, (el) => { if (el.textContent !== bubble.text) el.textContent = bubble.text; }, 200);
    }

    for (const [key, el] of this.plateEls) {
      if (!alive.has(key)) { el.remove(); this.plateEls.delete(key); }
    }
  }

  bubble(playerId, text) {
    this.bubbles.set(playerId, { text: text.slice(0, 90),
                                 until: performance.now() + 5200 });
  }

  // --------------------------------------------------------- scoreboard
  toggleScoreboard(open, rows, net) {
    this.scoreboardOpen = open;
    const sb = $('scoreboard');
    sb.classList.toggle('show', open);
    if (open) this.renderScoreboard(rows, net);
  }

  renderScoreboard(rows, net) {
    if (!this.scoreboardOpen) return;
    const sb = $('scoreboard');
    const teams = (net.hud?.teams || []).map((t) => t.id);
    const byTeam = new Map();
    for (const r of rows) {
      if (!byTeam.has(r.team)) byTeam.set(r.team, []);
      byTeam.get(r.team).push(r);
    }
    const outbreak = net.hud?.kind === 'outbreak';
    const cols = outbreak
      ? ['Player', 'Points', 'Kills', 'Downs', 'Revives', 'Ping']
      : ['Player', 'Score', 'Kills', 'Deaths', 'Streak', 'Ping'];
    const rowHtml = (r) => `<tr class="${r.id === net.myId ? 'me' : ''}${r.alive ? '' : ' dead'}">
      <td><span class="pname" data-user="${r.userId}">${esc(r.name)}</span>
        ${r.flag ? ' <span style="color:#ffd166">⚑</span>' : ''}</td>
      <td class="num">${outbreak ? (r.points || 0).toLocaleString() : r.score}</td>
      <td class="num">${r.kills}</td>
      <td class="num">${outbreak ? (r.downs || 0) : r.deaths}</td>
      <td class="num">${outbreak ? (r.revives || 0) : r.streak}</td>
      <td class="num">${r.ping}ms</td></tr>`;
    let body = '';
    const order = teams.length ? teams : [...byTeam.keys()];
    for (const t of order) {
      const list = (byTeam.get(t) || []);
      if (!list.length && teams.length) continue;
      if (teams.length > 1) {
        const score = (net.hud.teams.find((x) => x.id === t) || {}).score || 0;
        body += `<tr class="team-row"><td colspan="6" style="color:${teamColor(t)}">
          ${t.toUpperCase()} · ${score} pts · ${list.length} players</td></tr>`;
      }
      body += list.map(rowHtml).join('');
    }
    for (const [t, list] of byTeam) {
      if (order.includes(t)) continue;
      body += list.map(rowHtml).join('');
    }
    sb.innerHTML = `<div class="sb-head">
        <h2>${esc(net.config?.world?.name || 'Scoreboard')}</h2>
        <span style="opacity:.6">${esc(net.config?.world?.mode || '')}</span>
        <span style="margin-left:auto;opacity:.6">
          ${rows.length}/${net.config?.world?.maxPlayers || 16} players ·
          ${Math.round(net.ping * 1000)}ms</span>
      </div>
      <table><thead><tr>${cols.map((c, i) =>
        `<th${i ? ' style="text-align:right"' : ''}>${c}</th>`).join('')}</tr></thead>
      <tbody>${body}</tbody></table>
      <div style="padding:10px 18px;opacity:.5;font-size:.85em">
        Double-click a name in chat to open that player's profile in a new tab.</div>`;
    sb.querySelectorAll('.pname').forEach((el) => {
      el.addEventListener('dblclick', () => {
        window.open(`/#/profile/${el.dataset.user}`, '_blank');
      });
      el.style.pointerEvents = 'auto';
    });
  }

  // ------------------------------------------------------------ respawn
  updateRespawn(net) {
    const el = $('respawn');
    const roundEnd = $('round-end').classList.contains('show');
    const showing = !net.alive && !net.downed && net.config && !roundEnd;
    el.classList.toggle('show', !!showing);
    if (!showing) return;
    const t = net.respawnIn || 0;
    $('respawn-timer').textContent = t > 0.05
      ? `Respawning in ${t.toFixed(1)}s`
      : 'Press Space to respawn';
    if (net.hud?.kind === 'lavarise') {
      $('respawn-timer').textContent = 'Waiting for the next round…';
    }
    if (net.hud?.kind === 'outbreak') {
      $('respawn-timer').textContent = 'You will rejoin at the next wave.';
    }
  }

  setLastKiller(name, weapon) {
    $('respawn-killer').textContent = name
      ? `Eliminated by ${name}${weapon ? ` (${weapon})` : ''}`
      : '';
  }

  updateRevive(net) {
    const ring = $('revive-ring');
    const downed = net.downed != null;
    ring.classList.toggle('show', downed);
    if (!downed) return;
    const p = Math.max(0, Math.min(1, net.downed));
    $('revive-arc').setAttribute('stroke-dashoffset', String(327 * (1 - p)));
    $('revive-label').innerHTML = net.reviverName
      ? `<div style="color:#7cff9e">${esc(net.reviverName)}</div><div>reviving…</div>`
      : '<div style="color:#ffd166">DOWNED</div><div style="font-size:.8em">hold on!</div>';
  }

  interactPrompt(target, key) {
    const el = $('interact-prompt');
    if (!target) { el.classList.remove('show'); return; }
    el.classList.add('show');
    $('interact-key').textContent = key;
    $('interact-label').textContent = target.label;
    $('interact-cost').textContent = target.cost ? `${target.cost} pts` : '';
  }
}

function teamColor(t) {
  return ({ red: '#ff8072', blue: '#74b7ff', sun: '#ffc65e', moon: '#b79bff',
            survivor: '#7fdcff' })[t] || '#e6ecf3';
}

export function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
