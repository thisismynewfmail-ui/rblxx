// In-game chat. Bound to Y (all) and U (team) by default.
// While the input is focused every other binding is suppressed so the
// player can type freely, and double-clicking a name opens that profile.

import { esc } from './hud.js';

const TEAM_COLOR = {
  red: '#ff8072', blue: '#74b7ff', sun: '#ffc65e', moon: '#b79bff',
  survivor: '#7fdcff', neutral: '#dfe6ee',
};

export class Chat {
  constructor(net, input) {
    this.net = net;
    this.input = input;              // InputManager
    this.root = document.getElementById('chat');
    this.log = document.getElementById('chat-log');
    this.field = document.getElementById('chat-input');
    this.prefix = document.getElementById('chat-prefix');
    this.open = false;
    this.channel = 'all';
    this.history = [];
    this.historyIndex = -1;
    this.messages = [];
    this.onBubble = null;

    this.field.addEventListener('keydown', (e) => {
      e.stopPropagation();
      if (e.key === 'Enter') { this.submit(); }
      else if (e.key === 'Escape') { this.close(); }
      else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (this.history.length) {
          this.historyIndex = Math.min(this.history.length - 1,
                                       this.historyIndex + 1);
          this.field.value = this.history[this.historyIndex] || '';
        }
      } else if (e.key === 'ArrowDown') {
        e.preventDefault();
        this.historyIndex = Math.max(-1, this.historyIndex - 1);
        this.field.value = this.historyIndex < 0
          ? '' : this.history[this.historyIndex];
      } else if (e.key === 'Tab') {
        e.preventDefault();
        this.completeName();
      }
    });
    this.field.addEventListener('keyup', (e) => e.stopPropagation());
    this.field.addEventListener('keypress', (e) => e.stopPropagation());
  }

  openChat(channel = 'all') {
    this.open = true;
    this.channel = channel;
    this.root.classList.add('open');
    this.prefix.textContent = channel === 'team' ? 'Team:' : 'Say:';
    this.prefix.style.color = channel === 'team' ? '#7cff9e' : '#8fd8ff';
    this.input.blocked = true;
    this.input.releaseLock();
    this.historyIndex = -1;
    // Focusing on the next frame keeps the opening keystroke out of the box.
    requestAnimationFrame(() => { this.field.value = ''; this.field.focus(); });
    this.messages.forEach((m) => m.el.classList.remove('dim'));
  }

  close() {
    this.open = false;
    this.root.classList.remove('open');
    this.field.blur();
    this.field.value = '';
    this.input.blocked = false;
    this.scheduleFade();
  }

  toggle(channel = 'all') {
    if (this.open && this.channel === channel) this.close();
    else if (this.open) { this.channel = channel; this.openChat(channel); }
    else this.openChat(channel);
  }

  submit() {
    const text = this.field.value.trim();
    if (text) {
      this.net.chat(text, this.channel);
      this.history.unshift(text);
      if (this.history.length > 30) this.history.pop();
    }
    this.close();
  }

  completeName() {
    const value = this.field.value;
    const m = value.match(/(\S+)$/);
    if (!m) return;
    const frag = m[1].toLowerCase();
    const names = [...this.net.players.values()].map((p) => p.profile.name);
    if (this.net.me) names.push(this.net.me.name);
    const hit = names.find((n) => n.toLowerCase().startsWith(frag));
    if (hit) this.field.value = value.slice(0, m.index) + hit + ' ';
  }

  addMessage(msg) {
    const el = document.createElement('div');
    const isTeam = msg.channel === 'team';
    el.className = 'cmsg' + (isTeam ? ' team' : '');
    const color = msg.color || TEAM_COLOR[msg.team] || '#dfe6ee';
    el.innerHTML =
      `${isTeam ? '<span class="tag">[TEAM]</span> ' : ''}` +
      `<span class="cname" style="color:${color}" data-user="${msg.userId || ''}"
        title="Double-click to open ${esc(msg.from)}'s profile">${esc(msg.from)}</span>` +
      `<span style="opacity:.5">:</span> <span class="ctext">${esc(msg.text)}</span>`;
    const nameEl = el.querySelector('.cname');
    if (msg.userId) {
      nameEl.addEventListener('dblclick', (e) => {
        e.preventDefault();
        window.open(`/#/profile/${msg.userId}`, '_blank', 'noopener');
      });
    }
    this._push(el);
    if (msg.id && this.onBubble) this.onBubble(msg.id, msg.text);
  }

  addSystem(text, kind = 'system') {
    const el = document.createElement('div');
    el.className = `cmsg ${kind}`;
    el.innerHTML = `<span class="ctext">${esc(text)}</span>`;
    this._push(el);
  }

  _push(el) {
    this.log.appendChild(el);
    this.messages.push({ el, at: performance.now() });
    while (this.messages.length > 40) {
      const old = this.messages.shift();
      old.el.remove();
    }
    this.log.scrollTop = this.log.scrollHeight;
    this.scheduleFade();
  }

  scheduleFade() {
    clearTimeout(this._fadeTimer);
    if (!this._fadeEnabled) return;
    this._fadeTimer = setTimeout(() => this.fadeOld(), 500);
  }

  set fade(on) {
    this._fadeEnabled = on;
    if (!on) this.messages.forEach((m) => m.el.classList.remove('dim'));
    else this.scheduleFade();
  }

  fadeOld() {
    if (this.open || !this._fadeEnabled) return;
    const now = performance.now();
    let again = false;
    for (const m of this.messages) {
      if (now - m.at > 12000) m.el.classList.add('dim');
      else again = true;
    }
    if (again) this._fadeTimer = setTimeout(() => this.fadeOld(), 1000);
  }
}
