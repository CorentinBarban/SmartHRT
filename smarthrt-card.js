/**
 * SmartHRT Card — Custom Lovelace Card for Home Assistant
 * type: custom:smarthrt-card
 * prefix: room       # required — instance name
 * name: Room         # optional
 * min_temp: 13       # optional, default 13 (display range only)
 * max_temp: 26       # optional, default 26 (display range only)
 */

// Entity suffix mapping — change values to match your HA language
// Current language: French
const SMARTHRT_KEYS = {
  sensor_state: "etat_machine",
  sensor_temp_int: "temperature_interieure",
  sensor_relay: "heure_de_relance",
  sensor_time_to: "temps_avant_relance",
  label_time_to: "Temps avant relance",
  number_setpoint: "consigne",
  time_stop: "heure_coupure_chauffage",
  time_target: "heure_cible",
  switch_enabled: "mode_chauffage_intelligent",
  mode_values: {
    // language-neutral keys
    initializing: { label: "INIT", color: "#78909c", icon: "○" },
    heating_on: { label: "ON", color: "#ef4444", icon: "●" },
    detecting_lag: { label: "LAG", color: "#f59e0b", icon: "◐" },
    monitoring: { label: "MONITORING", color: "#3b82f6", icon: "◉" },
    recovery: { label: "BOOST", color: "#ef4444", icon: "●" },
    heating_process: { label: "BOOST", color: "#ef4444", icon: "●" },
    unknown: { label: "?", color: "#78909c", icon: "○" },
    // French (strings.json)
    initialisation: { label: "INIT", color: "#78909c", icon: "○" },
    "chauffage actif": { label: "ON", color: "#ef4444", icon: "●" },
    "détection lag": { label: "LAG", color: "#f59e0b", icon: "◐" },
    surveillance: { label: "MONITORING", color: "#3b82f6", icon: "◉" },
    relance: { label: "BOOST", color: "#ef4444", icon: "●" },
    "montée en température": { label: "BOOST", color: "#ef4444", icon: "●" },
    inconnu: { label: "?", color: "#78909c", icon: "○" },
  },
};

// Temperature color scale -10°C → 42°C
const TEMP_CS = [
  { t: -10, r: 26, g: 26, b: 26 },
  { t: -3, r: 220, g: 208, b: 255 },
  { t: 3, r: 255, g: 255, b: 255 },
  { t: 10, r: 193, g: 232, b: 255 },
  { t: 15, r: 142, g: 185, b: 245 },
  { t: 17, r: 161, g: 214, b: 178 },
  { t: 20, r: 254, g: 243, b: 199 },
  { t: 25, r: 255, g: 179, b: 138 },
  { t: 30, r: 229, g: 115, b: 115 },
  { t: 35, r: 94, g: 39, b: 26 },
  { t: 42, r: 0, g: 0, b: 0 },
];
function tempToColor(temp) {
  const t = Math.max(-10, Math.min(42, temp));
  let lo = TEMP_CS[0],
    hi = TEMP_CS[TEMP_CS.length - 1];
  for (let i = 0; i < TEMP_CS.length - 1; i++) {
    if (t >= TEMP_CS[i].t && t <= TEMP_CS[i + 1].t) {
      lo = TEMP_CS[i];
      hi = TEMP_CS[i + 1];
      break;
    }
  }
  const f = lo.t === hi.t ? 0 : (t - lo.t) / (hi.t - lo.t);
  const rv = Math.round(lo.r + f * (hi.r - lo.r));
  const gv = Math.round(lo.g + f * (hi.g - lo.g));
  const bv = Math.round(lo.b + f * (hi.b - lo.b));
  return `#${rv.toString(16).padStart(2, "0")}${gv.toString(16).padStart(2, "0")}${bv.toString(16).padStart(2, "0")}`;
}

class SmartHRTCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._hass = null;
    this._config = null;
    this._dragging = false;
    this._rendered = false;
    this._locked = true;
    this._dialogSuffix = null;
    this._svgReady = false;
    this._el = null;
    // Stable references for window listeners (required for proper cleanup)
    this._onMouseMove = (e) => this._onDrag(e);
    this._onTouchMove = (e) => this._onDrag(e);
    this._onMouseUp = () => this._endDrag();
    this._onTouchEnd = () => this._endDrag();
  }

  disconnectedCallback() {
    window.removeEventListener("mousemove", this._onMouseMove);
    window.removeEventListener("touchmove", this._onTouchMove);
    window.removeEventListener("mouseup", this._onMouseUp);
    window.removeEventListener("touchend", this._onTouchEnd);
  }

  setConfig(config) {
    if (!config.prefix) throw new Error('SmartHRT Card: "prefix" required.');
    this._config = {
      prefix: config.prefix,
      name:
        config.name ||
        config.prefix.charAt(0).toUpperCase() + config.prefix.slice(1),
      min_temp: config.min_temp ?? 13,
      max_temp: config.max_temp ?? 26,
    };
  }

  set hass(hass) {
    this._hass = hass;
    try {
      if (!this._rendered) {
        this._render();
        this._rendered = true;
      } else this._update();
    } catch (e) {
      console.error("SmartHRT Card error:", e);
      this.shadowRoot.innerHTML = `<ha-card style="padding:12px;color:red;font-size:0.8em;">
        <b>SmartHRT Card error</b><br>${e.message}<br><pre>${e.stack}</pre></ha-card>`;
    }
  }

  _eid(key) {
    const suffix = SMARTHRT_KEYS[key];
    const domain = key.startsWith("sensor")
      ? "sensor"
      : key.startsWith("number")
        ? "number"
        : key.startsWith("switch")
          ? "switch"
          : "time";
    return `${domain}.${this._config.prefix}_${suffix}`;
  }
  _estate(key) {
    return this._hass?.states[this._eid(key)]?.state ?? null;
  }
  _eattr(key, attr) {
    return this._hass?.states[this._eid(key)]?.attributes?.[attr] ?? null;
  }

  _isDark() {
    const bg =
      getComputedStyle(document.documentElement)
        .getPropertyValue("--primary-background-color")
        .trim() || "#fff";
    const hex = bg.replace(/^#/, "");
    if (hex.length !== 6) return true;
    const [r, g, b] = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
    return r * 0.299 + g * 0.587 + b * 0.114 < 128;
  }
  _hexToRgba(hex, a) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return m
      ? `rgba(${parseInt(m[1], 16)},${parseInt(m[2], 16)},${parseInt(m[3], 16)},${a})`
      : `rgba(120,144,156,${a})`;
  }
  _datetimeToLocalHHMM(raw) {
    try {
      const dt = new Date(raw.replace(" ", "T"));
      return new Intl.DateTimeFormat(undefined, {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).format(dt);
    } catch (e) {
      return raw;
    }
  }
  _modeInfo(mode) {
    const info = SMARTHRT_KEYS.mode_values[(mode || "").toLowerCase()] || {
      label: mode || "—",
      color: "#78909c",
      icon: "○",
    };
    return { ...info, glow: this._hexToRgba(info.color, 0.3) };
  }
  _polarToXY(cx, cy, r, deg) {
    const rad = ((deg - 90) * Math.PI) / 180;
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  }
  _arc(cx, cy, r, a1, a2) {
    const s = this._polarToXY(cx, cy, r, a1),
      e = this._polarToXY(cx, cy, r, a2);
    return `M${s.x.toFixed(2)} ${s.y.toFixed(2)} A${r} ${r} 0 ${a2 - a1 > 180 ? 1 : 0} 1 ${e.x.toFixed(2)} ${e.y.toFixed(2)}`;
  }
  _tempToAngle(t, mn, mx) {
    return -135 + Math.max(0, Math.min(1, (t - mn) / (mx - mn))) * 270;
  }

  _render() {
    const dark = this._isDark();
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; container-type: inline-size; }
        ha-card { display: block; }
        .card-inner { overflow: hidden; padding: 6px 10px 10px; position: relative; }
        .thermo-wrap { position: relative; width: 160px; height: 160px; margin: 0 auto -5px; }
        .thermo-wrap.unlocked { cursor: grab; }
        .thermo-wrap.unlocked:active { cursor: grabbing; user-select: none; }
        .thermo-svg { position: absolute; top: 0; left: 0; }
        .thermo-center {
          position: absolute; top: 50%; left: 50%;
          transform: translate(-50%,-50%);
          text-align: center; pointer-events: none; width: 120px;
        }
        .mode-icon  { font-size: 1.1em; line-height: 1; margin-bottom: 2px; pointer-events: all; cursor: pointer; }
        .mode-label { font-size: 0.58em; font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; margin-bottom: 5px; pointer-events: all; cursor: pointer; }
        .tsp-value  { font-size: 2em; font-weight: 300; line-height: 1; }
        .tsp-unit   { font-size: 0.45em; color: var(--secondary-text-color); vertical-align: super; }
        .current-temp { font-size: 0.8em; color: var(--secondary-text-color); margin-top: 4px; cursor: pointer; text-decoration: underline dotted; pointer-events: all; }
        .switch-toggle { position: absolute; top: 6px; left: 6px; width: 34px; height: 20px; z-index: 10; cursor: pointer; }
        .switch-toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
        .switch-track { position: absolute; inset: 0; border-radius: 20px; background: var(--divider-color); transition: background 0.25s; }
        .switch-toggle input:checked + .switch-track { background: var(--primary-color); }
        .switch-knob { position: absolute; top: 3px; left: 3px; width: 14px; height: 14px; border-radius: 50%; background: white; transition: transform 0.25s; box-shadow: 0 1px 3px rgba(0,0,0,0.3); pointer-events: none; }
        .switch-toggle input:checked ~ .switch-knob { transform: translateX(14px); }
        .controls-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; gap: 8px; }
        .card-title { font-size: 0.75em; font-weight: 700; text-transform: uppercase; color: var(--secondary-text-color); cursor: pointer; flex: 1; }
        .time-to-relay { font-size: 0.75em; color: var(--secondary-text-color); text-align: right; flex: 1; }
        .btn-group { display: flex; align-items: center; gap: 6px; }
        .adj-btn, .lock-btn { width: 32px; height: 32px; border-radius: 50%; border: 1px solid var(--divider-color); background: transparent; color: var(--secondary-text-color); display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; }
        .lock-btn.locked   { border-color: var(--divider-color); filter: grayscale(0) brightness(1); background: var(--secondary-background-color); box-shadow: inset 0 2px 4px rgba(255,255,255,0.2), inset 0 -2px 4px rgba(0,0,0,0.35); }
        .lock-btn.unlocked { border-color: var(--divider-color); filter: grayscale(1) brightness(0.5); opacity: 0.6; }
        .adj-btn.active    { color: var(--primary-color); border-color: var(--divider-color); background: var(--secondary-background-color); box-shadow: inset 0 2px 4px rgba(255,255,255,0.2), inset 0 -2px 4px rgba(0,0,0,0.35); opacity: 0.85; }
        .adj-btn:disabled  { opacity: 0.35; cursor: default; color: var(--primary-text-color); }
        .time-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; }
        .time-block { background: var(--secondary-background-color); border: 1px solid var(--divider-color); border-radius: 10px; padding: 8px 10px; cursor: pointer; text-align: center; }
        .time-block.readonly { cursor: default; opacity: 0.35; }
        .time-block-label { font-size: 0.6em; font-weight: 600; color: var(--secondary-text-color); text-transform: uppercase; }
        .time-block-label .emoji { font-size: 1.9em; line-height: 1; display: block; margin-bottom: 2px; filter: grayscale(1) brightness(0.5); }
        .time-block-value { font-size: 1.2em; font-weight: 300; }
        .tick       { stroke: var(--divider-color); stroke-width: 1.5; }
        .tick-major { stroke: var(--secondary-text-color); stroke-width: 2; opacity: 0.4; }
        .dialog-overlay { display: none; position: fixed; inset: 0; z-index: 9999; background: rgba(0,0,0,0.7); align-items: center; justify-content: center; backdrop-filter: blur(2px); }
        .dialog-overlay.open { display: flex; }
        .dialog-box { background: var(--ha-card-background, var(--card-background-color, white)); border-radius: var(--ha-card-border-radius, 12px); border: 1px solid var(--divider-color); padding: 24px; min-width: 260px; text-align: center; color: var(--primary-text-color); box-shadow: 0 8px 25px rgba(0,0,0,0.5); }
        .dialog-box h3 { margin: 0 0 15px; font-size: 0.9em; text-transform: uppercase; color: var(--secondary-text-color); letter-spacing: 0.1em; }
        .dialog-box input { font-size: 2.5em; width: 100%; text-align: center; margin: 15px 0; border-radius: 10px; border: 1px solid var(--divider-color); background: var(--secondary-background-color); color: var(--primary-text-color); outline: none; padding: 10px 0; color-scheme: ${dark ? "dark" : "light"}; }
        .dialog-btns { display: flex; gap: 12px; justify-content: center; margin-top: 10px; }
        .btn-ok     { background: var(--primary-color); color: var(--text-primary-color, white); border: none; padding: 10px 20px; border-radius: 8px; font-weight: bold; cursor: pointer; }
        .btn-cancel { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); padding: 10px 20px; border-radius: 8px; cursor: pointer; }
        @container (max-width: 219px) {
          .card-inner { padding: 4px 6px 8px; }
          .thermo-wrap { width: 130px; height: 130px; }
          .thermo-svg  { width: 130px; height: 130px; }
          .tsp-value   { font-size: 1.65em; }
          .current-temp { font-size: 0.7em; }
          .adj-btn, .lock-btn { width: 26px; height: 26px; font-size: 0.9em; }
          .btn-group { gap: 4px; }
          .controls-row { gap: 4px; }
          .card-title, .time-to-relay { font-size: 0.65em; }
          .time-block { padding: 5px 6px; }
          .time-block-label .emoji { font-size: 1.5em; }
          .time-block-value { font-size: 1em; }
          .time-row { gap: 4px; }
        }
      </style>
      <ha-card><div class="card-inner">
        <label class="switch-toggle" title="SmartHRT on/off">
          <input type="checkbox" id="switch-enabled" checked>
          <div class="switch-track"></div>
          <div class="switch-knob"></div>
        </label>
        <div class="thermo-wrap locked" id="thermo-wrap">
          <svg class="thermo-svg" id="thermo-svg" width="160" height="160" viewBox="0 0 200 200"></svg>
          <div class="thermo-center">
            <div class="mode-icon" id="mode-icon">○</div>
            <div class="mode-label" id="mode-label">—</div>
            <div class="tsp-value"><span id="tsp-val">—</span><span class="tsp-unit" id="tsp-unit">°C</span></div>
            <div class="current-temp" id="current-temp"></div>
          </div>
        </div>
        <div class="controls-row">
          <div class="card-title" id="card-title">—</div>
          <div class="btn-group">
            <button class="adj-btn" id="btn-minus" disabled>−</button>
            <button class="lock-btn locked" id="btn-lock">🔒</button>
            <button class="adj-btn" id="btn-plus" disabled>+</button>
          </div>
          <div class="time-to-relay" id="time-to-relay"></div>
        </div>
        <div class="time-row">
          <div class="time-block" id="block-stop">
            <div class="time-block-label"><span class="emoji">⏹</span>Arrêt</div>
            <div class="time-block-value" id="val-stop">—</div>
          </div>
          <div class="time-block readonly">
            <div class="time-block-label"><span class="emoji">⏰</span>Relance</div>
            <div class="time-block-value" id="val-relay">—</div>
          </div>
          <div class="time-block" id="block-target">
            <div class="time-block-label"><span class="emoji">🎯</span>Cible</div>
            <div class="time-block-value" id="val-target">—</div>
          </div>
        </div>
      </div></ha-card>
      <div class="dialog-overlay" id="dialog-overlay">
        <div class="dialog-box">
          <h3 id="dialog-title">Modifier l'heure</h3>
          <input type="time" id="dialog-input">
          <div class="dialog-btns">
            <button class="btn-cancel" id="dialog-cancel">Annuler</button>
            <button class="btn-ok" id="dialog-ok">OK</button>
          </div>
        </div>
      </div>`;

    // Cache DOM refs once — avoids repeated getElementById and cross-instance bugs on Android
    this._el = {
      wrap: this.shadowRoot.getElementById("thermo-wrap"),
      svg: this.shadowRoot.getElementById("thermo-svg"),
      modeIcon: this.shadowRoot.getElementById("mode-icon"),
      modeLabel: this.shadowRoot.getElementById("mode-label"),
      tspVal: this.shadowRoot.getElementById("tsp-val"),
      tspUnit: this.shadowRoot.getElementById("tsp-unit"),
      curTemp: this.shadowRoot.getElementById("current-temp"),
      cardTitle: this.shadowRoot.getElementById("card-title"),
      valStop: this.shadowRoot.getElementById("val-stop"),
      valRelay: this.shadowRoot.getElementById("val-relay"),
      valTarget: this.shadowRoot.getElementById("val-target"),
      timeTo: this.shadowRoot.getElementById("time-to-relay"),
      switchEl: this.shadowRoot.getElementById("switch-enabled"),
      dialogOverlay: this.shadowRoot.getElementById("dialog-overlay"),
      dialogInput: this.shadowRoot.getElementById("dialog-input"),
    };
    this._el.wrap.style.touchAction = "auto";
    this._bindEvents();
    this._update();
  }

  _bindEvents() {
    const r = this.shadowRoot;
    const fireMoreInfo = (key) => () =>
      this.dispatchEvent(
        new CustomEvent("hass-more-info", {
          detail: { entityId: this._eid(key) },
          bubbles: true,
          composed: true,
        }),
      );
    r.getElementById("card-title").addEventListener(
      "click",
      fireMoreInfo("sensor_state"),
    );
    r.getElementById("current-temp").addEventListener(
      "click",
      fireMoreInfo("sensor_temp_int"),
    );
    r.getElementById("mode-icon").addEventListener(
      "click",
      fireMoreInfo("sensor_state"),
    );
    r.getElementById("mode-label").addEventListener(
      "click",
      fireMoreInfo("sensor_state"),
    );
    r.getElementById("btn-lock").addEventListener("click", () =>
      this._toggleLock(),
    );
    r.getElementById("btn-plus").addEventListener("click", () =>
      this._adjustTemp(0.5),
    );
    r.getElementById("btn-minus").addEventListener("click", () =>
      this._adjustTemp(-0.5),
    );
    r.getElementById("block-stop").addEventListener("click", () =>
      this._openDialog(
        "Heure d'arrêt",
        SMARTHRT_KEYS.time_stop,
        this._el.valStop.textContent,
      ),
    );
    r.getElementById("block-target").addEventListener("click", () =>
      this._openDialog(
        "Heure cible",
        SMARTHRT_KEYS.time_target,
        this._el.valTarget.textContent,
      ),
    );
    r.getElementById("dialog-cancel").addEventListener("click", () =>
      this._closeDialog(),
    );
    r.getElementById("dialog-ok").addEventListener("click", () =>
      this._confirmDialog(),
    );
    this._el.switchEl.addEventListener("change", (e) => {
      this._hass.callService(
        "switch",
        e.target.checked ? "turn_on" : "turn_off",
        {
          entity_id: this._eid("switch_enabled"),
        },
      );
    });
    this._el.wrap.addEventListener("mousedown", (e) => {
      if (!this._locked) {
        e.preventDefault();
        this._startDrag(e);
      }
    });
    this._el.wrap.addEventListener(
      "touchstart",
      (e) => {
        if (!this._locked) this._startDrag(e);
      },
      { passive: true },
    );
    window.removeEventListener("mousemove", this._onMouseMove);
    window.removeEventListener("touchmove", this._onTouchMove);
    window.removeEventListener("mouseup", this._onMouseUp);
    window.removeEventListener("touchend", this._onTouchEnd);
    window.addEventListener("mousemove", this._onMouseMove);
    window.addEventListener("touchmove", this._onTouchMove, { passive: true });
    window.addEventListener("mouseup", this._onMouseUp);
    window.addEventListener("touchend", this._onTouchEnd);
  }

  _toggleLock() {
    this._locked = !this._locked;
    const wrap = this._el.wrap;
    const btnPlus = this.shadowRoot.getElementById("btn-plus");
    const btnMinus = this.shadowRoot.getElementById("btn-minus");
    const btnLock = this.shadowRoot.getElementById("btn-lock");
    wrap.className = `thermo-wrap ${this._locked ? "locked" : "unlocked"}`;
    wrap.style.touchAction = this._locked ? "auto" : "none";
    btnPlus.disabled = this._locked;
    btnMinus.disabled = this._locked;
    btnPlus.className = this._locked ? "adj-btn" : "adj-btn active";
    btnMinus.className = this._locked ? "adj-btn" : "adj-btn active";
    btnLock.textContent = this._locked ? "🔒" : "🔓";
    btnLock.className = `lock-btn ${this._locked ? "locked" : "unlocked"}`;
    this._update();
  }

  _openDialog(title, suffix, currentVal) {
    this._dialogSuffix = suffix;
    this.shadowRoot.getElementById("dialog-title").textContent = title;
    this._el.dialogInput.value =
      currentVal && currentVal !== "—" ? currentVal.trim() : "";
    this._el.dialogOverlay.classList.add("open");
  }
  _closeDialog() {
    this._el.dialogOverlay.classList.remove("open");
  }
  _confirmDialog() {
    const val = this._el.dialogInput.value;
    if (val && this._dialogSuffix) {
      this._hass.callService("time", "set_value", {
        entity_id: `time.${this._config.prefix}_${this._dialogSuffix}`,
        time: val,
      });
    }
    this._closeDialog();
  }

  _startDrag(e) {
    this._dragging = true;
    this._onDrag(e);
  }
  _endDrag() {
    this._dragging = false;
  }
  _onDrag(e) {
    if (!this._dragging || this._locked) return;
    const { left, top, width, height } = this._el.wrap.getBoundingClientRect();
    const pt = e.touches ? e.touches[0] : e;
    let ang =
      (Math.atan2(
        pt.clientY - (top + height / 2),
        pt.clientX - (left + width / 2),
      ) *
        180) /
        Math.PI +
      90;
    if (ang > 180) ang -= 360;
    if (ang < -180) ang += 360;
    if (ang < -135 || ang > 135) return;
    const { min_temp: mn, max_temp: mx } = this._config;
    this._setTemp(Math.round((mn + ((ang + 135) / 270) * (mx - mn)) * 2) / 2);
  }

  _setTemp(value) {
    this._hass.callService("number", "set_value", {
      entity_id: this._eid("number_setpoint"),
      value,
    });
  }
  _adjustTemp(delta) {
    const cur = parseFloat(this._estate("number_setpoint"));
    const { min_temp: mn, max_temp: mx } = this._config;
    if (!isNaN(cur)) this._setTemp(Math.max(mn, Math.min(mx, cur + delta)));
  }

  _update() {
    if (!this._hass || !this._el) return;

    this._el.cardTitle.textContent = this._config.name;

    const switchState = this._estate("switch_enabled");
    const isOn = switchState !== "off";
    this._el.switchEl.checked = isOn;

    const mode = this._modeInfo(this._estate("sensor_state"));
    this._el.modeIcon.textContent = mode.icon;
    this._el.modeIcon.style.color = mode.color;
    this._el.modeLabel.textContent = mode.label;
    this._el.modeLabel.style.color = mode.color;

    const tsp = parseFloat(this._estate("number_setpoint"));
    this._el.tspVal.textContent = isNaN(tsp) ? "—" : tsp.toFixed(1);

    const dimmed = isOn ? "1" : "0.5";
    this._el.tspVal.style.opacity = dimmed;
    this._el.tspUnit.style.opacity = dimmed;
    this._el.modeIcon.style.opacity = dimmed;
    this._el.modeLabel.style.opacity = dimmed;

    const cur = parseFloat(this._estate("sensor_temp_int"));
    const unit = this._eattr("sensor_temp_int", "unit_of_measurement") || "°C";
    this._el.tspUnit.textContent = unit;
    this._el.curTemp.textContent = isNaN(cur)
      ? ""
      : `🌡 ${cur.toFixed(1)}${unit}`;

    const relay = this._estate("sensor_relay");
    this._el.valRelay.textContent =
      relay && relay !== "unknown" && relay !== "unavailable"
        ? this._datetimeToLocalHHMM(relay)
        : "—";

    const timeTo = this._estate("sensor_time_to");
    if (timeTo && timeTo !== "unknown" && timeTo !== "unavailable") {
      const h = Math.floor(parseFloat(timeTo));
      const m = Math.round((parseFloat(timeTo) - h) * 60);
      const timeVal = isNaN(h)
        ? timeTo
        : h > 0
          ? h + "h" + (m > 0 ? m + "min" : "")
          : m + "min";
      this._el.timeTo.innerHTML = `<span style="font-size:0.75em;opacity:0.7;display:block">${SMARTHRT_KEYS.label_time_to}</span><span style="font-size:1.1em;font-weight:500">${timeVal}</span>`;
    } else {
      this._el.timeTo.textContent = "";
    }

    const stop = this._estate("time_stop");
    const target = this._estate("time_target");
    this._el.valStop.textContent = stop ? stop.slice(0, 5) : "—";
    this._el.valTarget.textContent = target ? target.slice(0, 5) : "—";
    // Griser Arrêt et Cible quand désactivé (cohérent avec la relance readonly)
    const blockStop = this.shadowRoot.getElementById("block-stop");
    const blockTarget = this.shadowRoot.getElementById("block-target");
    if (blockStop) blockStop.style.opacity = isOn ? "1" : "0.35";
    if (blockTarget) blockTarget.style.opacity = isOn ? "1" : "0.35";

    this._drawArc(tsp, cur, isOn);
  }

  _drawArc(tsp, curTemp, isOn = true) {
    const svg = this._el?.svg || this.shadowRoot.getElementById("thermo-svg");
    const cx = 100,
      cy = 100,
      r = 85,
      p = this._config.prefix;
    const svgNS = "http://www.w3.org/2000/svg";
    const mn = this._config.min_temp,
      mx = this._config.max_temp;
    const arcColor = !isOn
      ? "var(--secondary-background-color)"
      : isNaN(tsp)
        ? "#546e7a"
        : tempToColor(tsp);
    const rimColor = isNaN(curTemp) ? "#546e7a" : tempToColor(curTemp);
    const dark = this._isDark();

    if (!this._svgReady) {
      this._svgReady = true;
      while (svg.firstChild) svg.removeChild(svg.firstChild);
      const defs = document.createElementNS(svgNS, "defs");

      const grad = document.createElementNS(svgNS, "radialGradient");
      grad.setAttribute("id", `tg_${p}`);
      grad.setAttribute("cx", "50%");
      grad.setAttribute("cy", "50%");
      grad.setAttribute("r", "50%");
      [
        ["0%", "0"],
        ["70%", "0"],
        ["100%", "0.5"],
      ].forEach(([offset, opacity]) => {
        const s = document.createElementNS(svgNS, "stop");
        s.setAttribute("offset", offset);
        s.setAttribute("stop-color", rimColor);
        s.setAttribute("stop-opacity", opacity);
        grad.appendChild(s);
      });
      defs.appendChild(grad);

      const fKnob = document.createElementNS(svgNS, "filter");
      fKnob.setAttribute("id", `fk_${p}`);
      fKnob.setAttribute("x", "-80%");
      fKnob.setAttribute("y", "-80%");
      fKnob.setAttribute("width", "260%");
      fKnob.setAttribute("height", "260%");
      fKnob.innerHTML = `<feDropShadow dx="0" dy="2" stdDeviation="2.5" flood-color="${dark ? "rgba(0,0,0,0.7)" : "rgba(0,0,0,0.4)"}"/>`;
      defs.appendChild(fKnob);

      const fArc = document.createElementNS(svgNS, "filter");
      fArc.setAttribute("id", `fa_${p}`);
      fArc.setAttribute("x", "-10%");
      fArc.setAttribute("y", "-10%");
      fArc.setAttribute("width", "120%");
      fArc.setAttribute("height", "120%");
      fArc.innerHTML = `<feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-color="${dark ? "rgba(0,0,0,0.6)" : "rgba(0,0,0,0.3)"}"/>`;
      defs.appendChild(fArc);

      const clip = document.createElementNS(svgNS, "clipPath");
      clip.setAttribute("id", `dc_${p}`);
      const cc = document.createElementNS(svgNS, "circle");
      cc.setAttribute("cx", cx);
      cc.setAttribute("cy", cy);
      cc.setAttribute("r", "75");
      clip.appendChild(cc);
      defs.appendChild(clip);
      svg.appendChild(defs);

      const base = document.createElementNS(svgNS, "circle");
      base.setAttribute("cx", cx);
      base.setAttribute("cy", cy);
      base.setAttribute("r", "75");
      base.setAttribute(
        "fill",
        dark ? "rgba(255,255,255,0.04)" : "rgba(0,0,0,0.03)",
      );
      base.setAttribute(
        "stroke",
        dark ? "rgba(255,255,255,0.15)" : "rgba(0,0,0,0.12)",
      );
      base.setAttribute("stroke-width", "0.75");
      svg.appendChild(base);

      const gradCircle = document.createElementNS(svgNS, "circle");
      gradCircle.setAttribute("cx", cx);
      gradCircle.setAttribute("cy", cy);
      gradCircle.setAttribute("r", "75");
      gradCircle.setAttribute("fill", `url(#tg_${p})`);
      svg.appendChild(gradCircle);

      [
        { dy: 6, sw: 4, op: dark ? 0.45 : 0.18 },
        { dy: 7, sw: 6, op: dark ? 0.25 : 0.1 },
        { dy: 8, sw: 9, op: dark ? 0.12 : 0.05 },
      ].forEach(({ dy, sw, op }) => {
        const c = document.createElementNS(svgNS, "circle");
        c.setAttribute("cx", cx);
        c.setAttribute("cy", String(cy + dy));
        c.setAttribute("r", String(75 + dy));
        c.setAttribute("fill", "none");
        c.setAttribute("stroke", `rgba(0,0,0,${op})`);
        c.setAttribute("stroke-width", String(sw));
        c.setAttribute("clip-path", `url(#dc_${p})`);
        svg.appendChild(c);
      });

      const tickGroup = document.createElementNS(svgNS, "g");
      let ticks = "";
      for (let i = 0; i <= 30; i++) {
        const ang = -135 + (i / 30) * 270,
          major = i % 5 === 0;
        const p1 = this._polarToXY(cx, cy, r + 2, ang);
        const p2 = this._polarToXY(cx, cy, r + (major ? 12 : 7), ang);
        ticks += `<line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" class="${major ? "tick-major" : "tick"}"/>`;
      }
      tickGroup.innerHTML = ticks;
      svg.appendChild(tickGroup);

      const track = document.createElementNS(svgNS, "path");
      track.setAttribute("d", this._arc(cx, cy, r, -135, 135));
      track.setAttribute("stroke", "rgba(128,128,128,0.15)");
      track.setAttribute("stroke-width", "5");
      track.setAttribute("fill", "none");
      track.setAttribute("stroke-linecap", "round");
      svg.appendChild(track);

      const fg = document.createElementNS(svgNS, "g");
      fg.setAttribute("id", `svg-fg_${p}`);
      svg.appendChild(fg);
    }

    const gradEl = svg.querySelector(`#tg_${p}`);
    if (gradEl)
      gradEl
        .querySelectorAll("stop")
        .forEach((s) => s.setAttribute("stop-color", rimColor));

    const fgEl = svg.querySelector(`#svg-fg_${p}`);
    if (fgEl) {
      let activePath = "",
        knob = "";
      if (!isNaN(tsp)) {
        const a = this._tempToAngle(tsp, mn, mx);
        activePath = `<path d="${this._arc(cx, cy, r, -135, a)}" stroke="${arcColor}" stroke-width="5" fill="none" stroke-linecap="round" filter="url(#fa_${p})"/>`;
        const kp = this._polarToXY(cx, cy, r, a);
        knob = `<circle cx="${kp.x}" cy="${kp.y}" r="6" fill="${arcColor}" stroke="white" stroke-width="2" filter="url(#fk_${p})"/>`;
      }
      fgEl.innerHTML = activePath + knob;
    }
  }

  get subscribedEntities() {
    if (!this._config) return [];
    return Object.keys(SMARTHRT_KEYS)
      .filter((k) => k !== "mode_values" && !k.startsWith("label_"))
      .map((k) => this._eid(k));
  }

  static getStubConfig() {
    return { prefix: "", name: "" };
  }
  getCardSize() {
    return 4;
  }
}

customElements.define("smarthrt-card", SmartHRTCard);
window.customCards = window.customCards || [];
window.customCards.push({
  type: "smarthrt-card",
  name: "SmartHRT Card",
  description: "Thermostat SmartHRT",
  preview: false,
});
