// Pause menu: resume, settings, rebindable controls, help, and quit-to-profile.

import { BIND_LABELS, DEFAULT_BINDS, DEFAULT_SETTINGS, keyLabel, saveBinds,
         saveSettings } from './input.js';

const $ = (id) => document.getElementById(id);

const SETTINGS_SCHEMA = [
  { key: 'sensitivity', label: 'Mouse sensitivity', type: 'range',
    min: 0.0004, max: 0.008, step: 0.0001,
    format: (v) => (v * 1000).toFixed(1) },
  { key: 'adsSensitivity', label: 'Aim-down-sights multiplier', type: 'range',
    min: 0.2, max: 1.4, step: 0.02, format: (v) => v.toFixed(2) },
  { key: 'invertY', label: 'Invert vertical look', type: 'toggle' },
  { key: 'fov', label: 'Field of view', type: 'range', min: 60, max: 110,
    step: 1, format: (v) => `${v}°` },
  { key: 'hudScale', label: 'HUD scale', type: 'range', min: 0.8, max: 1.6,
    step: 0.05, format: (v) => `${Math.round(v * 100)}%` },
  { key: 'crosshairColor', label: 'Crosshair colour', type: 'color' },
  { key: 'crosshairStyle', label: 'Crosshair style', type: 'select',
    options: ['cross', 'dot', 'both', 'none'] },
  { key: 'masterVolume', label: 'Master volume', type: 'range', min: 0,
    max: 1, step: 0.02, format: (v) => `${Math.round(v * 100)}%` },
  { key: 'sfxVolume', label: 'Effects volume', type: 'range', min: 0, max: 1,
    step: 0.02, format: (v) => `${Math.round(v * 100)}%` },
  { key: 'showNames', label: 'Show player name plates', type: 'toggle' },
  { key: 'hitMarkers', label: 'Hit markers', type: 'toggle' },
  { key: 'chatFade', label: 'Fade old chat messages', type: 'toggle' },
  { key: 'viewBob', label: 'View bobbing', type: 'toggle' },
  { key: 'shake', label: 'Screen shake', type: 'toggle' },
  { key: 'toggleSprint', label: 'Sprint is a toggle', type: 'toggle' },
  { key: 'toggleCrouch', label: 'Crouch is a toggle', type: 'toggle' },
  { key: 'killFeedSize', label: 'Kill feed length', type: 'range', min: 3,
    max: 12, step: 1, format: (v) => `${v} lines` },
  { key: 'quality', label: 'Render quality', type: 'select',
    options: ['low', 'medium', 'high', 'ultra'] },
  { key: 'showFps', label: 'Show performance overlay', type: 'toggle' },
];

export class PauseMenu {
  constructor(game) {
    this.game = game;
    this.root = $('pause');
    this.tab = 'menu';
    this.open = false;
    this.capturing = null;

    $('pause').querySelectorAll('.pause-tabs button').forEach((b) => {
      b.addEventListener('click', () => {
        this.tab = b.dataset.tab;
        this.root.querySelectorAll('.pause-tabs button')
          .forEach((x) => x.classList.toggle('active', x === b));
        this.render();
      });
    });
    $('btn-resume').addEventListener('click', () => this.hide(true));
    $('btn-profile').addEventListener('click', () => {
      window.open(`/#/profile/${game.selfUserId || ''}`, '_blank', 'noopener');
    });
    $('btn-quit').addEventListener('click', () => game.quit());

    game.input.addEventListener('bindcaptured', (e) => {
      const { action, code } = e.detail;
      if (code) {
        for (const [k, v] of Object.entries(game.input.binds)) {
          if (v === code && k !== action) game.input.binds[k] = null;
        }
        game.input.binds[action] = code;
        saveBinds(game.input.binds);
      }
      this.capturing = null;
      this.render();
    });
  }

  show() {
    this.open = true;
    this.root.classList.add('show');
    this.game.input.blocked = true;
    this.game.input.releaseLock();
    document.body.classList.add('unlocked');
    this.render();
  }

  hide(relock) {
    this.open = false;
    this.root.classList.remove('show');
    this.capturing = null;
    this.game.input.blocked = this.game.chat.open;
    if (relock) this.game.input.requestLock();
  }

  toggle() { this.open ? this.hide(true) : this.show(); }

  render() {
    const body = $('pause-body');
    $('pause-world').textContent = this.game.net.config
      ? `${this.game.net.config.world.name} · ${this.game.net.config.world.mode}` : '';
    $('pause-ping').textContent =
      `${Math.round(this.game.net.ping * 1000)} ms · ${this.game.fps | 0} fps`;
    if (this.tab === 'menu') body.innerHTML = this.menuHtml();
    else if (this.tab === 'settings') body.innerHTML = this.settingsHtml();
    else if (this.tab === 'controls') body.innerHTML = this.controlsHtml();
    else body.innerHTML = this.helpHtml();
    this.wire();
  }

  menuHtml() {
    const net = this.game.net;
    const s = net.score || {};
    const acc = net.shotsFired ? (net.shotsHit / net.shotsFired * 100) : null;
    return `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:10px;margin-bottom:16px">
        ${stat('Score', s.score ?? 0)}
        ${stat('Eliminations', s.kills ?? 0)}
        ${stat('Deaths', s.deaths ?? 0)}
        ${stat('Streak', s.streak ?? 0)}
        ${net.hud?.kind === 'outbreak' ? stat('Points', (s.points ?? 0).toLocaleString()) : ''}
      </div>
      <p style="opacity:.75;line-height:1.7">
        <b>${esc(net.config?.world?.name || '')}</b> — ${esc(net.config?.world?.tagline || '')}
      </p>
      <div class="divider" style="background:rgba(255,255,255,.1)"></div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">
        <div><b>Loadout</b><div style="opacity:.7">
          ${(net.weapons || []).map((w) => esc(net.config?.weapons?.[w.id]?.name || w.id)).join(' · ')}
        </div></div>
        <div><b>Connection</b><div style="opacity:.7">
          ${Math.round(net.ping * 1000)} ms · ${net.reconciliations} corrections
        </div></div>
      </div>`;
  }

  settingsHtml() {
    const s = this.game.input.settings;
    return SETTINGS_SCHEMA.map((f) => {
      const v = s[f.key];
      let control = '';
      if (f.type === 'range') {
        control = `<input type="range" data-set="${f.key}" min="${f.min}"
          max="${f.max}" step="${f.step}" value="${v}">`;
      } else if (f.type === 'toggle') {
        control = `<div class="switch ${v ? 'on' : ''}" data-toggle="${f.key}"></div>`;
      } else if (f.type === 'select') {
        control = `<select data-set="${f.key}">${f.options.map((o) =>
          `<option value="${o}" ${o === v ? 'selected' : ''}>${o}</option>`).join('')}</select>`;
      } else if (f.type === 'color') {
        control = `<input type="color" data-set="${f.key}" value="${v}">`;
      }
      const shown = f.format ? f.format(v) : '';
      return `<div class="setting-row">
        <div><div class="sname">${f.label}</div></div>
        <div>${control}</div>
        <div class="sval" data-val="${f.key}">${shown}</div>
      </div>`;
    }).join('') +
      `<div style="margin-top:14px"><button class="gbtn" id="reset-settings"
        style="flex:none">Reset settings to defaults</button></div>`;
  }

  controlsHtml() {
    const binds = this.game.input.binds;
    return `<p style="opacity:.65;margin-top:0">Click a key to rebind it.
      Bindings are ignored while the chat box is open, so you can type freely.</p>`
      + Object.keys(BIND_LABELS).map((action) => `
      <div class="bind-row">
        <div>${BIND_LABELS[action]}</div>
        <div class="bind-key ${this.capturing === action ? 'capturing' : ''}"
             data-bind="${action}">${this.capturing === action
          ? 'press a key…' : keyLabel(binds[action])}</div>
      </div>`).join('')
      + `<div class="bind-row"><div>Fire</div><div class="bind-key"
            style="cursor:default;opacity:.6">Left mouse</div></div>
         <div class="bind-row"><div>Aim down sights</div><div class="bind-key"
            style="cursor:default;opacity:.6">Right mouse</div></div>
         <div class="bind-row"><div>Cycle weapon</div><div class="bind-key"
            style="cursor:default;opacity:.6">Mouse wheel</div></div>
         <div class="bind-row"><div>Pause / release cursor</div>
            <div class="bind-key" style="cursor:default;opacity:.6">Esc</div></div>
         <div style="margin-top:14px"><button class="gbtn" id="reset-binds"
            style="flex:none">Reset controls to defaults</button></div>`;
  }

  helpHtml() {
    const mode = this.game.net.config?.world?.mode || '';
    const tips = {
      'Team Deathmatch': [
        'Eliminate the other team. First to 60 wins the match.',
        'Grab the Speed Coil at the north road and the Gravity Coil at the south.',
        'The central tower gives you sight lines over both bases — and a Damage Boost on top.',
        'The southern ruins hide a tunnel that pops out behind the enemy line.',
      ],
      'King of the Hill': [
        'Gravity is 46% of normal — jumps are long, falls are fatal.',
        'Stand inside the Beacon ring to capture it; hold it to bank points.',
        'The Beacon relocates every 75 seconds. Get moving before it does.',
        'Blue pads launch you between islands. Use them, there is no floor.',
      ],
      'Co-op Survival': [
        'Shoot things, earn points, spend points on doors and wall weapons.',
        'Going down is not dying — a teammate has 26 seconds to revive you (hold E).',
        'Every fifth wave is a boss wave. Open the reactor before that gets ugly.',
        'The Mystery Box in the Vault costs 950 and respects nobody.',
      ],
      'Battle Royale': [
        'The lava starts rising 20 seconds into the round and never stops.',
        'Orange platforms crumble about a second after you land on them.',
        'Friendly fire is on. There are no teams. Last one dry wins.',
        'The higher you climb, the better the pickups.',
      ],
      'Capture the Flag': [
        'Take the enemy banner to your keep. Three captures wins.',
        'Your own flag must be at home for a capture to count.',
        'Hold the central platform to extend the causeway across the canyon.',
        'Ziplines run from each watchtower to the middle. Press E at the anchor.',
      ],
    }[mode] || ['Have fun out there.'];
    return `<h3 style="margin-top:0">${esc(mode)}</h3>
      <ul style="line-height:1.9;padding-left:18px;opacity:.85">
        ${tips.map((t) => `<li>${esc(t)}</li>`).join('')}</ul>
      <div class="divider" style="background:rgba(255,255,255,.1)"></div>
      <h4>Universal</h4>
      <ul style="line-height:1.9;padding-left:18px;opacity:.85">
        <li><b>P</b> switches between first and third person.</li>
        <li><b>Y</b> opens chat, <b>U</b> opens team chat. Double-click a name in
            chat to open that player's profile in a new tab.</li>
        <li><b>Tab</b> holds the scoreboard open.</li>
        <li>Rocket splash launches you — rocket jumping works exactly like you hope.</li>
        <li>Falling more than 34 studs hurts.</li>
      </ul>`;
  }

  wire() {
    const s = this.game.input.settings;
    this.root.querySelectorAll('[data-set]').forEach((el) => {
      el.addEventListener('input', () => {
        const key = el.dataset.set;
        let v = el.type === 'range' ? parseFloat(el.value) : el.value;
        s[key] = v;
        saveSettings(s);
        const schema = SETTINGS_SCHEMA.find((f) => f.key === key);
        const valEl = this.root.querySelector(`[data-val="${key}"]`);
        if (valEl && schema && schema.format) valEl.textContent = schema.format(v);
        this.game.applySettings();
      });
    });
    this.root.querySelectorAll('[data-toggle]').forEach((el) => {
      el.addEventListener('click', () => {
        const key = el.dataset.toggle;
        s[key] = !s[key];
        el.classList.toggle('on', s[key]);
        saveSettings(s);
        this.game.applySettings();
      });
    });
    this.root.querySelectorAll('[data-bind]').forEach((el) => {
      el.addEventListener('click', () => {
        this.capturing = el.dataset.bind;
        this.game.input.captureBind = this.capturing;
        this.render();
      });
    });
    const rb = $('reset-binds');
    if (rb) rb.addEventListener('click', () => {
      Object.assign(this.game.input.binds, DEFAULT_BINDS);
      saveBinds(this.game.input.binds);
      this.render();
    });
    const rs = $('reset-settings');
    if (rs) rs.addEventListener('click', () => {
      Object.assign(this.game.input.settings, DEFAULT_SETTINGS);
      saveSettings(this.game.input.settings);
      this.game.applySettings();
      this.render();
    });
  }
}

function stat(label, value) {
  return `<div style="background:rgba(255,255,255,.06);border-radius:5px;padding:9px 12px">
    <div style="font-size:1.7em;font-weight:700;font-family:'Trebuchet MS',Verdana,sans-serif">${value}</div>
    <div style="font-size:.78em;opacity:.6;text-transform:uppercase;letter-spacing:.6px">${label}</div>
  </div>`;
}

function esc(s) {
  return String(s == null ? '' : s).replace(/&/g, '&amp;')
    .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
