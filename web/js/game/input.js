// Keyboard/mouse handling, rebindable controls and pointer-lock plumbing.
// Every binding is suppressed while the chat box has focus.

export const DEFAULT_BINDS = {
  forward: 'KeyW', back: 'KeyS', left: 'KeyA', right: 'KeyD',
  jump: 'Space', sprint: 'ShiftLeft', crouch: 'ControlLeft',
  reload: 'KeyR', interact: 'KeyE', chat: 'KeyY', teamChat: 'KeyU',
  scoreboard: 'Tab', toggleCamera: 'KeyP', emote: 'KeyG', vote: 'KeyV',
  slot1: 'Digit1', slot2: 'Digit2', slot3: 'Digit3', slot4: 'Digit4',
  zoomOut: 'BracketLeft', zoomIn: 'BracketRight',
};

export const BIND_LABELS = {
  forward: 'Move forward', back: 'Move back', left: 'Strafe left',
  right: 'Strafe right', jump: 'Jump', sprint: 'Sprint', crouch: 'Crouch',
  reload: 'Reload', interact: 'Interact / revive', chat: 'Open chat',
  teamChat: 'Team chat', scoreboard: 'Scoreboard (hold)',
  toggleCamera: 'First / third person', emote: 'Emote', vote: 'Vote panel',
  slot1: 'Weapon 1', slot2: 'Weapon 2', slot3: 'Weapon 3', slot4: 'Weapon 4',
  zoomOut: 'Camera out', zoomIn: 'Camera in',
};

export const DEFAULT_SETTINGS = {
  sensitivity: 0.0022,
  adsSensitivity: 0.62,
  invertY: false,
  fov: 78,
  showFps: false,
  hudScale: 1,
  crosshairColor: '#7cff9e',
  crosshairStyle: 'cross',
  masterVolume: 0.7,
  sfxVolume: 0.8,
  hitMarkers: true,
  showNames: true,
  killFeedSize: 6,
  chatFade: true,
  viewBob: true,
  shake: true,
  quality: 'high',
  toggleSprint: false,
  toggleCrouch: false,
};

const STORE_BINDS = 'rblxx.binds';
const STORE_SETTINGS = 'rblxx.settings';

export function loadBinds() {
  try {
    return { ...DEFAULT_BINDS, ...JSON.parse(localStorage.getItem(STORE_BINDS) || '{}') };
  } catch { return { ...DEFAULT_BINDS }; }
}

export function saveBinds(binds) {
  try { localStorage.setItem(STORE_BINDS, JSON.stringify(binds)); } catch { /* */ }
}

export function loadSettings() {
  try {
    return { ...DEFAULT_SETTINGS,
             ...JSON.parse(localStorage.getItem(STORE_SETTINGS) || '{}') };
  } catch { return { ...DEFAULT_SETTINGS }; }
}

export function saveSettings(s) {
  try { localStorage.setItem(STORE_SETTINGS, JSON.stringify(s)); } catch { /* */ }
}

export function keyLabel(code) {
  if (!code) return '—';
  return code
    .replace(/^Key/, '')
    .replace(/^Digit/, '')
    .replace(/^Arrow/, '')
    .replace('ControlLeft', 'L Ctrl').replace('ControlRight', 'R Ctrl')
    .replace('ShiftLeft', 'L Shift').replace('ShiftRight', 'R Shift')
    .replace('AltLeft', 'L Alt').replace('AltRight', 'R Alt')
    .replace('BracketLeft', '[').replace('BracketRight', ']')
    .replace('Space', 'Space').replace('Escape', 'Esc');
}

export class InputManager extends EventTarget {
  constructor(canvas) {
    super();
    this.canvas = canvas;
    this.binds = loadBinds();
    this.settings = loadSettings();
    this.down = new Set();
    this.mouse = { left: false, right: false, dx: 0, dy: 0, wheel: 0 };
    this.yaw = 0;
    this.pitch = 0;
    this.locked = false;
    this.blocked = false;       // true while chat/menu owns the keyboard
    this.captureBind = null;
    this.sprintToggle = false;
    this.crouchToggle = false;
    this._install();
  }

  emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }

  action(code) {
    for (const [name, key] of Object.entries(this.binds)) {
      if (key === code) return name;
    }
    return null;
  }

  isDown(action) {
    const code = this.binds[action];
    return code ? this.down.has(code) : false;
  }

  _install() {
    this._onKeyDown = (e) => {
      if (this.captureBind) {
        e.preventDefault();
        if (e.code !== 'Escape') {
          this.emit('bindcaptured', { action: this.captureBind, code: e.code });
        } else {
          this.emit('bindcaptured', { action: this.captureBind, code: null });
        }
        this.captureBind = null;
        return;
      }
      if (e.code === 'Escape') {
        this.emit('escape', {});
        return;
      }
      if (e.repeat) {
        if (!this.blocked && e.code === this.binds.scoreboard) e.preventDefault();
        return;
      }
      if (this.blocked) {
        // Chat is open: let the browser handle typing, but still allow Enter.
        if (e.code === 'Enter' || e.code === 'NumpadEnter') {
          this.emit('chatsubmit', {});
        }
        return;
      }
      const action = this.action(e.code);
      if (action) {
        if (action === 'scoreboard' || action === 'chat' || action === 'teamChat') {
          e.preventDefault();
        }
        this.emit('action', { action, pressed: true });
      }
      if (e.code === 'Space') e.preventDefault();
      this.down.add(e.code);
    };

    this._onKeyUp = (e) => {
      this.down.delete(e.code);
      if (this.blocked) return;
      const action = this.action(e.code);
      if (action) this.emit('action', { action, pressed: false });
    };

    this._onMouseDown = (e) => {
      if (this.blocked) return;
      if (!this.locked && e.button === 0) { this.emit('requestlock', {}); return; }
      if (e.button === 0) this.mouse.left = true;
      if (e.button === 2) this.mouse.right = true;
      this.emit('mouse', { button: e.button, pressed: true });
    };

    this._onMouseUp = (e) => {
      if (e.button === 0) this.mouse.left = false;
      if (e.button === 2) this.mouse.right = false;
      this.emit('mouse', { button: e.button, pressed: false });
    };

    this._onMouseMove = (e) => {
      if (!this.locked || this.blocked) return;
      const sens = this.settings.sensitivity
        * (this.adsActive ? this.settings.adsSensitivity : 1);
      this.yaw -= e.movementX * sens;
      this.pitch += (this.settings.invertY ? 1 : -1) * e.movementY * sens;
      this.pitch = Math.max(-1.54, Math.min(1.54, this.pitch));
      this.yaw = ((this.yaw % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
    };

    this._onWheel = (e) => {
      if (this.blocked) return;
      this.mouse.wheel += Math.sign(e.deltaY);
      this.emit('wheel', { delta: Math.sign(e.deltaY) });
      e.preventDefault();
    };

    this._onLockChange = () => {
      this.locked = document.pointerLockElement === this.canvas;
      this.emit('lockchange', { locked: this.locked });
      if (!this.locked) {
        this.mouse.left = false;
        this.mouse.right = false;
        this.down.clear();
      }
    };

    this._onBlur = () => {
      this.down.clear();
      this.mouse.left = this.mouse.right = false;
    };

    window.addEventListener('keydown', this._onKeyDown, { capture: true });
    window.addEventListener('keyup', this._onKeyUp, { capture: true });
    window.addEventListener('mousedown', this._onMouseDown);
    window.addEventListener('mouseup', this._onMouseUp);
    window.addEventListener('mousemove', this._onMouseMove);
    window.addEventListener('wheel', this._onWheel, { passive: false });
    window.addEventListener('blur', this._onBlur);
    document.addEventListener('pointerlockchange', this._onLockChange);
    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());
  }

  requestLock() {
    if (this.locked) return;
    try {
      const p = this.canvas.requestPointerLock?.({ unadjustedMovement: true });
      if (p && p.catch) {
        p.catch(() => {
          try {
            const q = this.canvas.requestPointerLock();
            if (q && q.catch) q.catch(() => {});
          } catch { /* needs a user gesture; the next click retries */ }
        });
      }
    } catch { /* a user gesture is required; the next click will retry */ }
  }

  releaseLock() {
    if (document.pointerLockElement) document.exitPointerLock();
  }

  /** Build the per-tick command from the current key state. */
  sample() {
    let moveX = 0, moveZ = 0;
    if (!this.blocked) {
      if (this.isDown('forward')) moveZ -= 1;
      if (this.isDown('back')) moveZ += 1;
      if (this.isDown('left')) moveX -= 1;
      if (this.isDown('right')) moveX += 1;
    }
    const len = Math.hypot(moveX, moveZ);
    if (len > 1) { moveX /= len; moveZ /= len; }
    const sprint = this.settings.toggleSprint ? this.sprintToggle
      : this.isDown('sprint');
    const crouch = this.settings.toggleCrouch ? this.crouchToggle
      : this.isDown('crouch');
    return {
      moveX, moveZ,
      yaw: this.yaw, pitch: this.pitch,
      jump: !this.blocked && this.isDown('jump'),
      sprint: !this.blocked && sprint,
      crouch: !this.blocked && crouch,
      fire: !this.blocked && this.mouse.left && this.locked,
      ads: !this.blocked && this.mouse.right && this.locked,
      use: !this.blocked && this.isDown('interact'),
    };
  }

  dispose() {
    window.removeEventListener('keydown', this._onKeyDown, { capture: true });
    window.removeEventListener('keyup', this._onKeyUp, { capture: true });
    window.removeEventListener('mousedown', this._onMouseDown);
    window.removeEventListener('mouseup', this._onMouseUp);
    window.removeEventListener('mousemove', this._onMouseMove);
    window.removeEventListener('wheel', this._onWheel);
    window.removeEventListener('blur', this._onBlur);
    document.removeEventListener('pointerlockchange', this._onLockChange);
  }
}
