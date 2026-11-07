/* Virtual Test Devices: the sidebar panel.
 *
 * Plain JavaScript, no build step. It uses Home Assistant's own colours (CSS variables),
 * so it follows the user's light or dark theme, but draws its own flat tiles and rows,
 * not Home Assistant's cards.
 *
 * Two kinds of data, kept apart on purpose:
 *   - STRUCTURE (which devices exist, what each is made of) comes from the integration's
 *     admin-only websocket commands.
 *   - STATE comes from Home Assistant itself (`hass.states`), which keeps it current, so
 *     the panel shows what is true now and nothing is polled.
 * Every control calls an ordinary Home Assistant action (light.turn_on, lock.unlock with
 * a code, ...), the same one a user would call from Developer tools.
 *
 * `controlsFor` and `callFor` are the whole of "what can be done to each kind of device"
 * and are exported, with the naming helpers, so they can be checked without a browser.
 */

const ALARM_STATES = ["disarmed", "armed_home", "armed_away", "armed_night",
  "armed_vacation", "triggered"];
// No "docked" here: a test vacuum has no action that ends there (return_to_base only
// reaches "returning"), so it can be created docked but not driven to it.
const VACUUM_STATES = ["docked", "cleaning", "paused", "returning", "idle"];
const MEDIA_STATES = ["off", "on", "idle", "playing", "paused"];
const CLIMATE_MODES = ["off", "heat", "cool", "heat_cool", "auto"];
const EVENT_TYPES = ["press", "double_press", "hold", "release"];

const ALARM_SERVICE = {
  disarmed: "alarm_disarm", armed_away: "alarm_arm_away", armed_home: "alarm_arm_home",
  armed_night: "alarm_arm_night", armed_vacation: "alarm_arm_vacation",
  triggered: "alarm_trigger",
};
const VACUUM_SERVICE = {
  cleaning: "start", idle: "stop", paused: "pause", returning: "return_to_base",
};
const MEDIA_SERVICE = {
  playing: "media_play", paused: "media_pause", idle: "media_stop",
  on: "turn_on", off: "turn_off",
};

// Home Assistant's own feature bits, as the entity reports them in `supported_features`.
// An entity that reports none is assumed to do everything.
const CLIMATE_TARGET_TEMPERATURE = 1;   // ClimateEntityFeature.TARGET_TEMPERATURE
const MEDIA_VOLUME_SET = 4;             // MediaPlayerEntityFeature.VOLUME_SET
const supports = (attrs, bit) =>
  typeof attrs.supported_features !== "number" || (attrs.supported_features & bit) !== 0;

/* The two words a switch shows: what it says when off, and when on. */
const DOMAIN_WORDS = { lock: ["Locked", "Unlocked"], cover: ["Closed", "Open"], valve: ["Closed", "Open"] };
const CLASS_WORDS = {
  motion: ["Clear", "Detected"], occupancy: ["Clear", "Detected"], presence: ["Away", "Home"],
  moving: ["Still", "Moving"], door: ["Closed", "Open"], window: ["Closed", "Open"],
  garage_door: ["Closed", "Open"], opening: ["Closed", "Open"], moisture: ["Dry", "Wet"],
  smoke: ["Clear", "Smoke"], gas: ["Clear", "Gas"], carbon_monoxide: ["Clear", "Detected"],
  tamper: ["Clear", "Tampered"], vibration: ["Still", "Vibrating"], sound: ["Quiet", "Noise"],
  light: ["Dark", "Light"], connectivity: ["Offline", "Online"], battery: ["OK", "Low"],
  problem: ["OK", "Problem"], safety: ["Safe", "Unsafe"], lock: ["Locked", "Unlocked"],
};
export function toggleWords(domain, attrs = {}) {
  if (domain === "binary_sensor") return CLASS_WORDS[attrs.device_class] || ["Off", "On"];
  return DOMAIN_WORDS[domain] || ["Off", "On"];
}

const toggle = (value, words, label = "", id = "main") => ({ id, label, kind: "toggle", value, words });
const select = (id, label, options, value) => ({ id, label, kind: "select", options, value });
const number = (id, label, value, step = "any") => ({ id, label, kind: "number", value, step });
const text = (id, label, value) => ({ id, label, kind: "text", value });

/* The controls one entity offers, from its domain, state and attributes. */
export function controlsFor(domain, state, attrs = {}) {
  const words = toggleWords(domain, attrs);
  switch (domain) {
    case "binary_sensor":
    case "switch":
    case "light":
    case "fan":
    case "siren":
      return [toggle(state === "on", words)];
    case "lock":
      return [toggle(state === "unlocked", words)];
    case "cover":
    case "valve":
      return [toggle(state === "open", words)];
    case "sensor":
      return [text("main", "", state)];
    case "number":
      return [number("main", "", state)];
    case "text":
      return [text("main", "", state)];
    case "select":
      return [select("main", "", attrs.options || [], state)];
    case "alarm_control_panel":
      return [select("main", "", ALARM_STATES, state)];
    case "vacuum":
      return [select("main", "", VACUUM_STATES, state)];
    case "humidifier":
      return [toggle(state === "on", words), number("humidity", "target %", attrs.humidity, "1")];
    case "climate":
      return [
        select("mode", "mode", attrs.hvac_modes || CLIMATE_MODES, state),
        // Only what the device says it can do: offering a target temperature to a
        // thermostat without one just produces an error when it is used.
        ...(supports(attrs, CLIMATE_TARGET_TEMPERATURE)
          ? [number("temperature", "target", attrs.temperature, "0.5")] : []),
        number("current", "current", attrs.current_temperature, "0.5"),
      ];
    case "media_player":
      return [
        select("state", "state", MEDIA_STATES, state),
        ...(supports(attrs, MEDIA_VOLUME_SET)
          ? [{ id: "volume", label: "volume", kind: "slider", value: attrs.volume_level }] : []),
      ];
    case "button":
      return [{ id: "press", label: "", kind: "button", text: "Press" }];
    case "camera":
      return [{ id: "snapshot", label: "", kind: "button", text: "Take snapshot" }];
    case "event":
      return [{ id: "fire", label: "", kind: "fire",
        options: (attrs.event_types && attrs.event_types.length) ? attrs.event_types : EVENT_TYPES }];
    case "device_tracker":
      return [text("location", "location", state)];
    default:
      return [];   // notify: shown, nothing to set
  }
}

/* The Home Assistant action for one control change, or null. `value` is what the control
 * now holds (a boolean for a toggle). */
export function callFor(domain, id, value, entityId) {
  const ent = { entity_id: entityId };
  const on = value === true;
  switch (domain) {
    case "binary_sensor":
      return { domain: "virtual", service: on ? "turn_on" : "turn_off", data: ent };
    case "switch": case "light": case "fan": case "siren":
      return { domain, service: on ? "turn_on" : "turn_off", data: ent };
    case "lock":
      return { domain, service: on ? "unlock" : "lock", data: ent };
    case "cover":
      return { domain, service: on ? "open_cover" : "close_cover", data: ent };
    case "valve":
      return { domain, service: on ? "open_valve" : "close_valve", data: ent };
    case "sensor":
      return { domain: "virtual", service: "set", data: { ...ent, value: String(value) } };
    case "number":
      return { domain, service: "set_value", data: { ...ent, value: Number(value) } };
    case "text":
      return { domain, service: "set_value", data: { ...ent, value: String(value) } };
    case "select":
      return { domain, service: "select_option", data: { ...ent, option: String(value) } };
    case "alarm_control_panel":
      return ALARM_SERVICE[value] ? { domain, service: ALARM_SERVICE[value], data: ent } : null;
    case "vacuum":
      return VACUUM_SERVICE[value] ? { domain, service: VACUUM_SERVICE[value], data: ent } : null;
    case "humidifier":
      if (id === "humidity") return { domain, service: "set_humidity", data: { ...ent, humidity: Number(value) } };
      return { domain, service: on ? "turn_on" : "turn_off", data: ent };
    case "climate":
      if (id === "temperature") return { domain, service: "set_temperature", data: { ...ent, temperature: Number(value) } };
      if (id === "current") return { domain: "virtual", service: "set_current_temperature", data: { ...ent, value: Number(value) } };
      return { domain, service: "set_hvac_mode", data: { ...ent, hvac_mode: String(value) } };
    case "media_player":
      if (id === "volume") return { domain, service: "volume_set", data: { ...ent, volume_level: Number(value) } };
      return MEDIA_SERVICE[value] ? { domain, service: MEDIA_SERVICE[value], data: ent } : null;
    case "button":
      return { domain, service: "press", data: ent };
    case "camera":
      // Into Home Assistant's media folder, one fixed file per camera, overwritten each time.
      return { domain, service: "snapshot", data: { ...ent, filename: `/media/${entityId.split(".")[1]}.jpg` } };
    case "event":
      return { domain: "virtual", service: "fire_event", data: { ...ent, event_type: String(value) } };
    case "device_tracker":
      return { domain: "virtual", service: "move", data: { ...ent, location: String(value) } };
    default:
      return null;
  }
}

/* A lock used with a code: Home Assistant's own lock actions take a `code`. */
export function lockWithCode(entityId, action, code) {
  return { domain: "lock", service: action === "lock" ? "lock" : "unlock",
    data: { entity_id: entityId, code: String(code) } };
}

/* What the entity says its state is, with its unit when it has one. */
export function readout(domain, state, attrs = {}) {
  if (state === undefined || state === null) return "not loaded";
  const unit = attrs.unit_of_measurement;
  return unit ? `${state} ${unit}` : String(state);
}

/* A test device is always called "Test — ...", so it reads as test gear inside Home
 * Assistant itself (dashboards, logbook, entity ids), not only here. A name that already
 * starts with "test" is left alone. */
export function taggedName(name) {
  const clean = (name || "").trim();
  return clean.toLowerCase().startsWith("test") ? clean : `Test — ${clean}`;
}

/* The entity list for `virtual.create_device`, from a template: one entity keeps the
 * device's name, several are named for the device and what each is. A template that
 * receives messages (a phone) gets the notifier the caller chose: "Push" or "Text". */
export function buildEntities(template, deviceName, alertKind) {
  const entities = template.entities;
  return entities.map((entity) => {
    const what = entity.class || entity.platform.replace(/_/g, " ");
    const built = { ...entity, name: entities.length === 1 ? deviceName : `${deviceName} ${what}` };
    if (template.receives && entity.platform === "notify" && alertKind) {
      built.class = alertKind === "Text" ? "sms" : "app";
    }
    return built;
  });
}

const capital = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

/* What to call one part of a device: its entity's name with the device's name taken off the
 * front ("Test — Hall motion" on "Test — Hall" is "Motion"), or its kind if nothing is left. */
export function partLabel(entityName, deviceName, domain) {
  let rest = entityName || "";
  if (deviceName && rest.startsWith(deviceName)) rest = rest.slice(deviceName.length).replace(/^[\s—:-]+/, "");
  return capital(rest) || capital((domain || "").replace(/_/g, " "));
}

const KIND_NAME = {
  binary_sensor: "Sensor", sensor: "Sensor", number: "Value", text: "Value", select: "Choice",
  switch: "Switch", light: "Light", fan: "Fan", siren: "Siren", lock: "Lock", cover: "Cover",
  valve: "Valve", climate: "Thermostat", humidifier: "Humidifier", vacuum: "Vacuum",
  alarm_control_panel: "Alarm panel", media_player: "Speaker", camera: "Camera",
  button: "Button", event: "Remote", device_tracker: "Tracker", notify: "Alert target",
};
/* A short kind for a device, from the kinds of entity in it. */
export function kindOf(domains) {
  const names = [...new Set((domains || []).map((d) => KIND_NAME[d] || capital(d.replace(/_/g, " "))))];
  return names.join(" + ") || "Device";
}

const CATEGORY_ORDER = [
  ["Doors and locks", ["lock", "cover", "valve"]],
  ["Lights and switches", ["light", "switch", "fan", "siren"]],
  ["Climate and home", ["climate", "humidifier", "vacuum"]],
  ["Alarm", ["alarm_control_panel"]],
  ["Media and cameras", ["media_player", "camera"]],
  ["Phones and alerts", ["device_tracker", "notify"]],
  ["Buttons and remotes", ["button", "event"]],
  ["Sensors and values", ["binary_sensor", "sensor", "number", "text", "select"]],
];
/* Which group a real device belongs to in the clone list (the first that matches). */
export function categoryOf(domains) {
  for (const [name, members] of CATEGORY_ORDER) {
    if ((domains || []).some((d) => members.includes(d))) return name;
  }
  return "Other";
}

/* Is a device doing something right now? (A coloured edge on its tile.) */
const ACTIVE_STATE = /^(on|open|opening|unlocked|unlocking|playing|heat|cool|heat_cool|auto|cleaning|armed_[a-z_]+|arming|pending|disarming|triggered|detected|wet|returning|locking|closing|jammed)$/i;
export const isActiveState = (state) => ACTIVE_STATE.test(String(state || ""));

/* Things worth remembering in this browser only (lock codes, pinned attributes). It may be
 * unavailable (a private window), and the panel must still work without it. */
const memory = {};         // what the browser would not store, kept until the page closes
const unstored = new Set();  // keys whose last write to the browser failed
const store = {
  get(key, fallback) {
    // A key the browser REFUSED to store is served from memory, even when the browser still
    // holds an older value: memory is the newer one. Otherwise empty means empty.
    if (unstored.has(key) && key in memory) return JSON.parse(memory[key]);
    try {
      const raw = localStorage.getItem("virtual-panel:" + key);
      if (raw) {
        const value = JSON.parse(raw);
        if (value !== null) return value;   // a literal "null" is as good as nothing
      }
    } catch (_e) { /* unreadable: as good as nothing */ }
    return fallback;
  },
  set(key, value) {
    memory[key] = JSON.stringify(value);
    try {
      localStorage.setItem("virtual-panel:" + key, memory[key]);
      unstored.delete(key);
    } catch (_e) { unstored.add(key); }
  },
};

const FOLD_AT = 6;   // a device with more parts than this shows the rest on request

const make = (tag, className, textContent) => {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (textContent !== undefined) el.textContent = textContent;
  return el;
};

/* ------------------------------------------------------------------ the panel */

class VirtualTestDevicesPanel extends HTMLElement {
  constructor() {
    super();
    this._hass = null;
    this._devices = [];
    this._groups = [];
    this._templates = [];
    this._clonable = [];
    this._group = null;          // the group new devices are added to
    this._tab = "devices";
    this._kind = "All";          // the kind chip chosen on the Devices tab
    this._closed = new Set();    // group names folded shut
    this._rows = new Map();      // entity_id -> { rows, entity, early }
    this._readouts = new Map();  // entity_id -> element showing its state
    this._extras = new Map();    // entity_id -> function(attrs) for lock details
    this._started = false;
    this._unsub = [];
    this._watchToken = null;
    this._shown = "";            // what the list was last drawn from (see _loadStructure)
    this._loadError = false;
    this._timer = null;
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; min-height: 100vh; box-sizing: border-box;
          background: var(--primary-background-color); color: var(--primary-text-color);
          font-family: var(--paper-font-body1_-_font-family, Roboto, sans-serif); font-size: 15px; }
        [hidden] { display: none !important; }
        header { display: flex; align-items: center; gap: 10px; height: var(--header-height, 56px);
          padding: 0 12px; box-sizing: border-box;
          background: var(--app-header-background-color, var(--primary-color));
          color: var(--app-header-text-color, #fff); }
        header h1 { font-size: 20px; font-weight: 400; margin: 0; flex: 1; }
        header h1 .ver { font-size: 12px; opacity: .7; margin-left: 6px; }
        header button { background: none; border: 0; color: inherit; cursor: pointer;
          font-size: 15px; padding: 8px 10px; border-radius: 4px; }
        header button.menu { font-size: 24px; line-height: 1; border-radius: 50%; }
        .live { font-size: 12px; display: flex; align-items: center; gap: 6px; opacity: .9; }
        .live::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: #66bb6a; }
        nav.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--divider-color);
          padding: 0 8px; overflow-x: auto; }
        nav.tabs button { background: none; border: 0; border-bottom: 3px solid transparent;
          color: var(--secondary-text-color); font: inherit; padding: 14px 16px; cursor: pointer; white-space: nowrap; }
        nav.tabs button.sel { color: var(--primary-color); border-bottom-color: var(--primary-color); font-weight: 500; }
        main { max-width: 1280px; margin: 0 auto; padding: 8px 20px 60px; }
        .status { min-height: 20px; margin: 8px 0 2px; font-size: 13px; color: var(--secondary-text-color); }
        .status.error { color: var(--error-color, #db4437); }
        .lead { color: var(--secondary-text-color); margin: 8px 0 14px; }
        .note { color: var(--secondary-text-color); padding: 20px 0; }
        .fine { font-size: 12px; color: var(--secondary-text-color); }
        input[type=text], input[type=search], input[type=number], select {
          font: inherit; color: inherit; background: var(--primary-background-color);
          border: 1px solid var(--divider-color); border-radius: 4px; padding: 8px 10px; }
        input[type=search] { width: 100%; box-sizing: border-box; }
        button.primary { font: inherit; color: var(--text-primary-color, #fff); background: var(--primary-color);
          border: 0; border-radius: 4px; padding: 8px 16px; cursor: pointer; }
        button.quiet { font: inherit; font-size: 13px; color: inherit; background: none;
          border: 1px solid var(--divider-color); border-radius: 4px; padding: 4px 10px; cursor: pointer; }
        button.link { font: inherit; font-size: 13px; background: none; border: 0;
          color: var(--secondary-text-color); cursor: pointer; padding: 4px 6px; }
        button.link.sure { color: var(--error-color, #db4437); font-weight: 500; }
        button:disabled { opacity: .5; cursor: default; }
        .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0 2px; }
        .chip { font: inherit; font-size: 13px; background: none; color: var(--secondary-text-color);
          border: 1px solid var(--divider-color); border-radius: 999px; padding: 4px 12px; cursor: pointer; }
        .chip.sel { background: var(--primary-color); border-color: var(--primary-color); color: var(--text-primary-color, #fff); }
        .count { font-size: 13px; color: var(--secondary-text-color); margin: 10px 0 0; }

        /* devices: a heading per group, then flat tiles. A coloured edge marks a device that
           is doing something right now. */
        details.group { margin-top: 18px; }
        details.group > summary { cursor: pointer; font-size: 13px; text-transform: uppercase; letter-spacing: .06em;
          color: var(--secondary-text-color); padding: 6px 0; list-style: none; border-bottom: 2px solid var(--divider-color); }
        details.group > summary::before { content: "\\25BE  "; }
        details.group:not([open]) > summary::before { content: "\\25B8  "; }
        .tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 10px; margin-top: 10px; }
        .tile { display: grid; grid-template-columns: 1fr auto; align-items: baseline; align-content: start;
          border: 1px solid var(--divider-color); border-left: 4px solid var(--divider-color); border-radius: 10px;
          padding: 10px 12px; background: var(--secondary-background-color, transparent); }
        .tile[data-on="1"] { border-left-color: var(--primary-color); }
        .who { grid-column: 1; min-width: 0; }
        .dname { font-size: 16px; font-weight: 500; overflow-wrap: anywhere; }
        .dkind { font-size: 12px; color: var(--secondary-text-color); }
        .tile > button.remove { grid-column: 2; }
        .parts { grid-column: 1 / -1; margin-top: 4px; }
        .part { display: flex; align-items: center; flex-wrap: wrap; gap: 4px 8px; padding: 4px 0; }
        .part .what { flex: 1 1 28%; min-width: 0; font-size: 13px; color: var(--secondary-text-color); overflow-wrap: anywhere; }
        .part .state { flex: 0 1 auto; font-size: 14px; font-weight: 500; text-align: right; }
        .part .ctl { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
        .part .ctl input[type=number], .part .ctl input[type=text] { width: 96px; padding: 4px 6px; }
        .part .ctl select { padding: 4px 6px; max-width: 150px; }
        .part .ctl input[type=range] { width: 130px; accent-color: var(--primary-color); }
        .seg { display: inline-flex; border: 1px solid var(--divider-color); border-radius: 4px; overflow: hidden; }
        .seg button { font: inherit; font-size: 13px; background: none; color: var(--secondary-text-color);
          border: 0; padding: 4px 10px; cursor: pointer; }
        .seg button + button { border-left: 1px solid var(--divider-color); }
        .seg button.on { background: var(--primary-color); color: var(--text-primary-color, #fff); }
        .events { display: flex; flex-wrap: wrap; gap: 4px; }
        .flash { animation: flash 1.6s ease-out; }
        @keyframes flash { from { background: var(--divider-color); } to { background: transparent; } }
        details.more, .codewrap { grid-column: 1 / -1; margin-top: 4px; }
        details summary { cursor: pointer; color: var(--primary-color); font-size: 13px; padding: 2px 0; }
        details.more input[type=search] { margin: 6px 0; padding: 5px 8px; }
        .pin { font-size: 15px; padding: 0 4px; }
        .pin.on { color: #f9a825; }
        .codeinfo { font-size: 13px; padding: 2px 0; }
        .code { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 3px 0; }
        .code .cname { min-width: 64px; }
        .code .cval { color: var(--secondary-text-color); min-width: 44px; letter-spacing: .1em; }
        .code input { width: 90px; padding: 3px 6px; }

        /* the other tabs: plain rows and divider lines */
        .groupbar { display: flex; align-items: center; gap: 8px; margin: 12px 0; font-size: 14px; }
        .row { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
        .row .what { flex: 1; min-width: 0; overflow-wrap: anywhere; }
        .row .what small { display: block; color: var(--secondary-text-color); font-size: 12px; }
        .row.picked { background: var(--secondary-background-color, transparent); }
        .cat { font-size: 12px; text-transform: uppercase; letter-spacing: .06em; color: var(--secondary-text-color); margin: 18px 0 2px; }
        .form { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 12px 0; }
        .form input[type=text] { flex: 1 1 200px; }
        .opt { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--divider-color); }
        .opt label { flex: 1; }
        .opt label small { display: block; color: var(--secondary-text-color); font-size: 12px; }
        .sect { font-size: 17px; font-weight: 500; margin: 24px 0 4px; }
        .piclist { max-height: 460px; overflow-y: auto; }
        @media (max-width: 560px) { main { padding: 4px 12px 60px; } .tiles { grid-template-columns: 1fr; } }
      </style>
      <header>
        <button class="menu" aria-label="Open the sidebar" title="Open the sidebar">&#9776;</button>
        <h1>Test Devices <small class="ver"></small></h1>
        <span class="live" title="Shows what Home Assistant reports right now">Live</span>
        <button class="refresh" title="Read the lists again">Refresh</button>
      </header>
      <nav class="tabs" role="tablist">
        <button data-tab="devices" class="sel" role="tab">Devices</button>
        <button data-tab="create" role="tab">Create</button>
        <button data-tab="clone" role="tab">Clone a device</button>
        <button data-tab="all" role="tab">Clone everything</button>
      </nav>
      <main>
        <div class="status" role="status" aria-live="polite"></div>
        <section data-pane="devices">
          <input class="search" type="search" placeholder="Search your test devices" aria-label="Search your test devices">
          <div class="chips kinds"></div>
          <div class="count"></div>
          <div class="list"></div>
        </section>
        <section data-pane="create" hidden></section>
        <section data-pane="clone" hidden></section>
        <section data-pane="all" hidden></section>
      </main>`;
    const $ = (s) => this.shadowRoot.querySelector(s);
    $("button.menu").addEventListener("click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true })));
    $("button.refresh").addEventListener("click", () => { this._loadChoices(); this._loadStructure(); });
    $("input.search").addEventListener("input", () => this._applyFilter());
    $("nav.tabs").addEventListener("click", (ev) => {
      const button = ev.target.closest("button");
      if (button) this._showTab(button.dataset.tab);
    });
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._started) {
      this._started = true;
      this._loadChoices();
      this._loadStructure();
      this._watchRegistries();
    } else {
      this._updateLive();
    }
  }

  // Home Assistant sets these too; the panel has no use for them yet.
  set narrow(_value) {}
  set route(_value) {}
  set panel(_value) {}

  disconnectedCallback() {
    for (const stop of this._unsub) { try { stop(); } catch (_e) { /* already gone */ } }
    this._unsub = [];
    this._watchToken = null;
    clearTimeout(this._timer);
    this._started = false;   // read everything again if the panel is opened later
    this._shown = "";        // and draw the list again
  }

  /* Devices added or removed from anywhere (this panel, PistonCore, a service call) change
   * the registries; read the list again shortly after. */
  _watchRegistries() {
    const conn = this._hass && this._hass.connection;
    if (!conn || !conn.subscribeEvents) return;
    const again = () => { clearTimeout(this._timer); this._timer = setTimeout(() => this._loadStructure(), 700); };
    // A subscription that finishes AFTER the panel was closed must be undone, not kept: it
    // would go on reading the list into a panel that is no longer there.
    const token = (this._watchToken = {});
    for (const type of ["entity_registry_updated", "device_registry_updated"]) {
      Promise.resolve(conn.subscribeEvents(again, type))
        .then((stop) => {
          if (typeof stop !== "function") return;
          if (this._watchToken === token) this._unsub.push(stop); else stop();
        })
        .catch(() => { /* the Refresh button still works */ });
    }
  }

  _say(message, isError = false) {
    const el = this.shadowRoot.querySelector(".status");
    el.textContent = message;
    el.className = "status" + (isError ? " error" : "");
  }

  _showTab(tab) {
    this._tab = tab;
    for (const button of this.shadowRoot.querySelectorAll("nav.tabs button")) {
      button.classList.toggle("sel", button.dataset.tab === tab);
    }
    for (const pane of this.shadowRoot.querySelectorAll("[data-pane]")) pane.hidden = pane.dataset.pane !== tab;
  }

  /* ----------------------------------------------------------- what can be added */

  async _loadChoices() {
    try {
      const [groups, templates, clonable] = await Promise.all([
        this._hass.callWS({ type: "virtual/groups" }),
        this._hass.callWS({ type: "virtual/templates" }),
        this._hass.callWS({ type: "virtual/clonable" }),
      ]);
      this._groups = groups.groups || [];
      this._templates = templates.templates || [];
      this._clonable = clonable.devices || [];
      this.shadowRoot.querySelector(".ver").textContent = groups.version || "";
      // New devices go to a group that is running; one that failed to load cannot take them.
      const running = this._groups.filter((g) => g.state === "loaded");
      if (!running.some((g) => g.name === this._group)) this._group = running.length ? running[0].name : null;
    } catch (err) {
      this._say((err && err.message) || "Could not read what can be added.", true);
      return;
    }
    this._renderCreate();
    this._renderClone();
    this._renderAll();
  }

  /* Run one add (create or clone), keep the button from being pressed twice, and say what
   * happened. The new device shows up through the registry events. */
  async _add(button, doing, done, action) {
    button.disabled = true;
    this._say(doing);
    try {
      await action();
      this._say(done);
      clearTimeout(this._timer);
      this._timer = setTimeout(() => this._loadStructure(), 1500);
    } catch (err) {
      this._say((err && err.message) || "That did not work.", true);
    } finally {
      button.disabled = false;
    }
  }

  /* The group new devices go to: a picker when there is more than one, a note when none is
   * running, nothing when there is just the one. */
  _groupBar() {
    if (!this._group) {
      return make("div", "note", "No group is running, so nothing can be added. Reload the group in Settings, then Refresh.");
    }
    if (this._groups.length < 2) return null;
    const bar = make("div", "groupbar", "Add to");
    const pick = make("select");
    pick.setAttribute("aria-label", "Group to add to");
    for (const group of this._groups) {
      const running = group.state === "loaded";
      const o = make("option", "", running ? group.name : `${group.name} (not running)`);
      o.value = group.name;
      o.disabled = !running;
      pick.appendChild(o);
    }
    pick.value = this._group;
    pick.addEventListener("change", () => {
      this._group = pick.value;
      for (const other of this.shadowRoot.querySelectorAll(".groupbar select")) other.value = pick.value;
    });
    bar.appendChild(pick);
    return bar;
  }

  /* ----------------------------------------------------------------- Create tab */

  _renderCreate() {
    const pane = this.shadowRoot.querySelector('[data-pane="create"]');
    pane.textContent = "";
    pane.appendChild(make("p", "lead", 'Make a new test device from scratch. Its name always starts with "Test —".'));
    if (!this._groups.length) { pane.appendChild(make("div", "note", "There is no group to add to yet.")); return; }
    const bar = this._groupBar();
    if (bar) pane.appendChild(bar);
    if (!this._group) return;

    let picked = null;
    const hint = make("div", "status", "Pick a kind below, then give it a name.");
    const form = make("div", "form");
    const name = make("input"); name.type = "text";
    name.placeholder = "Name, for example Garage door";
    name.setAttribute("aria-label", "Name for the new device");
    const go = make("button", "primary", "Create"); go.disabled = true;
    form.append(name, go);

    // Only a kind that receives messages (a phone) offers push or text.
    const alert = make("div", "opt"); alert.hidden = true;
    const alertLabel = make("label", "", "This kind receives messages");
    alertLabel.appendChild(make("small", "", "A piston that sends a notification will find it. Choose how."));
    const alertSeg = make("div", "seg");
    let alertKind = "Push";
    for (const kind of ["Push", "Text"]) {
      const b = make("button", kind === alertKind ? "on" : "", kind);
      b.addEventListener("click", () => {
        alertKind = kind;
        for (const x of alertSeg.children) x.classList.toggle("on", x === b);
      });
      alertSeg.appendChild(b);
    }
    alert.append(alertLabel, alertSeg);

    const list = make("div");
    const draw = () => {
      list.textContent = "";
      let category = null;
      const order = [...new Set(this._templates.map((t) => t.category))];
      const sorted = this._templates.map((template, i) => ({ template, i }))
        .sort((a, b) => order.indexOf(a.template.category) - order.indexOf(b.template.category) || a.i - b.i);
      sorted.forEach(({ template, i }) => {
        if (template.category !== category) { category = template.category; list.appendChild(make("div", "cat", category)); }
        const row = make("div", "row" + (i === picked ? " picked" : ""));
        row.appendChild(make("div", "what", template.name));
        const b = make("button", "link", i === picked ? "Picked" : "Pick");
        b.addEventListener("click", () => {
          picked = i;
          alert.hidden = !template.receives;
          hint.textContent = `Making: ${template.name}. Give it a name.`;
          go.disabled = go.dataset.busy === "1";
          draw();
          name.focus();
        });
        row.appendChild(b);
        list.appendChild(row);
      });
    };
    const submit = () => {
      const typed = name.value.trim();
      if (picked === null || go.disabled) return;
      if (!typed) { name.focus(); return; }
      const template = this._templates[picked];
      const deviceName = taggedName(typed);
      go.dataset.busy = "1";
      this._add(go, `Creating ${deviceName}…`, `Created ${deviceName}.`, async () => {
        await this._hass.callService("virtual", "create_device", {
          group_name: this._group, device_name: deviceName,
          entities: buildEntities(template, deviceName, template.receives ? alertKind : undefined) });
        name.value = "";
      }).finally(() => { delete go.dataset.busy; });
    };
    go.addEventListener("click", submit);
    name.addEventListener("keydown", (ev) => { if (ev.key === "Enter") submit(); });
    pane.append(form, alert, hint, list);
    draw();
  }

  /* ------------------------------------------------------------ Clone a device tab */

  _renderClone() {
    const pane = this.shadowRoot.querySelector('[data-pane="clone"]');
    pane.textContent = "";
    pane.appendChild(make("p", "lead",
      "Make a test copy of one of your real devices. It reports the same abilities, so a piston can be tried against it."));
    if (!this._groups.length) { pane.appendChild(make("div", "note", "There is no group to add to yet.")); return; }
    const bar = this._groupBar();
    if (bar) pane.appendChild(bar);
    if (!this._group) return;

    // One option, instead of guessing which device is a phone.
    const opt = make("div", "opt");
    const label = make("label", "", "Also give the copy a way to receive a push or a text");
    label.htmlFor = "notifyon";
    label.appendChild(make("small", "", "Off for most things. Turn it on when you clone a phone, or anything a piston sends a message to."));
    const seg = make("div", "seg"); seg.hidden = true;
    let notifyAs = "app";
    for (const [value, words] of [["app", "Push"], ["sms", "Text"]]) {
      const b = make("button", value === notifyAs ? "on" : "", words);
      b.addEventListener("click", () => { notifyAs = value; for (const x of seg.children) x.classList.toggle("on", x === b); });
      seg.appendChild(b);
    }
    const on = make("input"); on.type = "checkbox"; on.id = "notifyon";
    on.setAttribute("aria-label", "Also give the copy a way to receive a push or a text");
    on.addEventListener("change", () => { seg.hidden = !on.checked; });
    opt.append(label, seg, on);
    pane.appendChild(opt);

    const search = make("input"); search.type = "search";
    search.placeholder = "Search your devices"; search.setAttribute("aria-label", "Search your devices");
    search.style.marginTop = "14px";
    const chips = make("div", "chips");
    const list = make("div", "piclist");
    pane.append(search, chips, list);

    let category = "All";
    const categories = () => [...new Set(this._clonable.map((d) => categoryOf(d.domains)))].sort();
    const drawChips = () => {
      chips.textContent = "";
      for (const c of ["All", ...categories()]) {
        const b = make("button", "chip" + (c === category ? " sel" : ""), c);
        b.addEventListener("click", () => { category = c; drawChips(); draw(); });
        chips.appendChild(b);
      }
    };
    const SHOWN = 60;
    const draw = () => {
      list.textContent = "";
      const needle = search.value.trim().toLowerCase();
      const matches = this._clonable.filter((d) =>
        (category === "All" || categoryOf(d.domains) === category) &&
        (!needle || `${d.name} ${d.kind} ${d.domains.join(" ")}`.toLowerCase().includes(needle)));
      if (!this._clonable.length) list.appendChild(make("div", "note", "Nothing here can be cloned yet."));
      for (const device of matches.slice(0, SHOWN)) {
        const row = make("div", "row");
        const what = make("div", "what", device.name);
        what.appendChild(make("small", "", [device.kind, device.domains.join(", "),
          `${device.entities} ${device.entities === 1 ? "entity" : "entities"}`].filter(Boolean).join(" · ")));
        const button = make("button", "primary", "Clone");
        button.addEventListener("click", () => {
          this._add(button, `Cloning ${device.name}…`, `Cloned ${device.name}.`, () =>
            this._hass.callService("virtual", "clone_device", {
              group_name: this._group, device_id: device.device_id,
              ...(on.checked ? { notify_as: notifyAs, add_notifier: true } : {}) }));
        });
        row.append(what, button);
        list.appendChild(row);
      }
      if (matches.length > SHOWN) list.appendChild(make("div", "note", `Showing ${SHOWN} of ${matches.length}. Search to narrow it down.`));
    };
    search.addEventListener("input", draw);
    drawChips();
    draw();
  }

  /* ---------------------------------------------------------- Clone everything tab */

  _renderAll() {
    const pane = this.shadowRoot.querySelector('[data-pane="all"]');
    pane.textContent = "";
    pane.appendChild(make("p", "lead",
      "Copy a whole Home Assistant: export it from the real one, then bring chosen devices into a test one."));

    pane.appendChild(make("div", "sect", "1. Export this Home Assistant"));
    pane.appendChild(make("p", "lead", "Run this on the real one. It only reads, and writes one file in the configuration folder. Lock and alarm codes and passwords are never copied."));
    const field = (labelText, hint, value) => {
      const row = make("div", "opt");
      const label = make("label", "", labelText);
      if (hint) label.appendChild(make("small", "", hint));
      const input = make("input"); input.type = "text"; input.value = value || "";
      input.setAttribute("aria-label", labelText); input.style.width = "260px";
      row.append(label, input);
      pane.appendChild(row);
      return input;
    };
    const file = field("File name", "Written inside your configuration folder", "virtual_export.yaml");
    const skipIntegrations = field("Leave out these integrations", "Separate with commas. Empty keeps the usual list (hassio, backup, sun, hacs, virtual)", "");
    const skipDevices = field("Leave out devices", "Names or patterns, for example ??:??:??:??:??:??", "");
    const skipEntities = field("Leave out entities", "Names or patterns, for example sensor.*_power", "");
    const keepRow = make("div", "opt");
    const keepLabel = make("label", "", "Keep their state across restarts");
    const keep = make("input"); keep.type = "checkbox"; keep.setAttribute("aria-label", "Keep their state across restarts");
    keepRow.append(keepLabel, keep);
    pane.appendChild(keepRow);

    const out = make("div", "status");
    const button = make("button", "primary", "Export");
    const split = (input) => input.value.split(",").map((s) => s.trim()).filter(Boolean);
    button.addEventListener("click", async () => {
      button.disabled = true;
      out.className = "status"; out.textContent = "Exporting…";
      const data = { file: file.value.trim() || "virtual_export.yaml" };
      if (split(skipIntegrations).length) data.exclude_integrations = split(skipIntegrations);
      if (split(skipDevices).length) data.exclude_devices = split(skipDevices);
      if (split(skipEntities).length) data.exclude_entities = split(skipEntities);
      if (keep.checked) data.persistent = true;
      try {
        const reply = await this._hass.callWS({ type: "call_service", domain: "virtual", service: "export_devices",
          service_data: data, return_response: true });
        const result = (reply && reply.response) || {};
        const skipped = result.skipped || [];
        out.textContent = `Wrote ${result.file || data.file}: ${result.entities} entities in ${result.devices} devices. ` +
          `${skipped.length} left out.`;
        if (skipped.length) {
          const details = make("details");
          details.appendChild(make("summary", "", "What was left out"));
          for (const item of skipped.slice(0, 200)) {
            const what = item.entity_id || item.device || `${item.count} x ${item.domain}.*`;
            details.appendChild(make("div", "fine", `${what}: ${item.reason}`));
          }
          out.appendChild(details);
        }
      } catch (err) {
        out.className = "status error";
        out.textContent = (err && err.message) || "The export did not work.";
      } finally { button.disabled = false; }
    });
    const exportForm = make("div", "form");
    exportForm.appendChild(button);
    pane.append(exportForm, out);

    pane.appendChild(make("div", "sect", "2. Bring devices in"));
    pane.appendChild(make("p", "note",
      "Coming next: read an export file, tick the devices you want, and add them to a group here. " +
      "A name that is already taken will be kept and the new one renamed. Until then, load the exported file as a group's devices file."));
  }

  /* ------------------------------------------------------------------ Devices tab */

  async _loadStructure() {
    let devices;
    try {
      devices = (await this._hass.callWS({ type: "virtual/devices" })).devices || [];
    } catch (err) {
      this._loadError = true;
      this._say((err && err.message) || "Could not read the devices.", true);
      return;
    }
    if (this._loadError) { this._loadError = false; this._say(""); }
    // Redrawing throws away whatever is half typed and any "Remove it?" waiting for its
    // second click, and registry events arrive for changes that are not ours. Nothing
    // changed in what is SHOWN, so nothing is redrawn.
    const shown = JSON.stringify(devices);
    if (shown === this._shown) return;
    this._shown = shown;
    this._devices = devices;
    this._renderStructure();
  }

  async _call(domain, id, value, entityId) {
    const call = callFor(domain, id, value, entityId);
    if (!call) {
      this._say(`A test ${domain.replace(/_/g, " ")} cannot be set to "${value}".`, true);
      this._revert(entityId);
      return;
    }
    await this._send(call);
  }

  /* Send one action. True if Home Assistant took it, false (with the reason shown) if not. */
  async _send(call) {
    try {
      await this._hass.callService(call.domain, call.service, call.data);
      this._say("");
      return true;
    } catch (err) {
      this._say((err && err.message) || `${call.domain}.${call.service} failed.`, true);
      this._revert(call.data && call.data.entity_id);
      return false;
    }
  }

  /* Put every control back to what Home Assistant says is true, even one that has focus (a
   * select keeps focus after a choice, so "leave the field being typed in alone" would
   * otherwise leave a refused choice showing). */
  _revert(entityId) {
    this._forceSync = entityId;
    try { this._updateLive(); } finally { this._forceSync = null; }
  }

  _renderStructure() {
    const list = this.shadowRoot.querySelector(".list");
    list.textContent = "";
    this._rows.clear();
    this._readouts.clear();
    this._extras.clear();
    this._drawKinds();

    if (!this._devices.length) {
      list.appendChild(make("div", "note", "No test devices yet. Make one on the Create or Clone tab."));
      this._applyFilter();
      return;
    }

    let group = null, tiles = null;
    for (const device of this._devices) {
      if (device.group !== group) {
        group = device.group;
        const det = make("details", "group");
        det.open = !this._closed.has(group);
        det.dataset.group = group;
        det.addEventListener("toggle", () => {
          if (det.open) this._closed.delete(det.dataset.group); else this._closed.add(det.dataset.group);
        });
        det.appendChild(make("summary", "", group));
        tiles = make("div", "tiles");
        det.appendChild(tiles);
        list.appendChild(det);
      }
      tiles.appendChild(this._tile(device));
    }
    this._updateLive();
    this._applyFilter();
  }

  _kindOfDevice(device) { return kindOf(device.entities.map((e) => e.domain)); }

  _drawKinds() {
    const chips = this.shadowRoot.querySelector(".kinds");
    chips.textContent = "";
    const kinds = [...new Set(this._devices.map((d) => this._kindOfDevice(d)))].sort();
    if (!kinds.includes(this._kind)) this._kind = "All";
    for (const kind of ["All", ...kinds]) {
      const b = make("button", "chip" + (kind === this._kind ? " sel" : ""), kind);
      b.addEventListener("click", () => { this._kind = kind; this._drawKinds(); this._applyFilter(); });
      chips.appendChild(b);
    }
  }

  _tile(device) {
    const tile = make("div", "tile");
    tile.dataset.search = `${device.name} ${device.group} ${this._kindOfDevice(device)}`.toLowerCase();
    tile.dataset.kind = this._kindOfDevice(device);
    tile.dataset.on = "0";
    tile.dataset.entities = device.entities.map((e) => e.entity_id).join(" ");

    const who = make("div", "who");
    who.append(make("div", "dname", device.name), make("div", "dkind", this._kindOfDevice(device)));

    const remove = make("button", "link remove", "Remove");
    remove.disabled = !device.key;
    let armed = null;
    let removing = false;   // the reload after a removal takes a second or more
    remove.addEventListener("click", async () => {
      if (removing) return;
      if (!armed) {
        remove.textContent = "Remove it?";
        remove.classList.add("sure");
        armed = setTimeout(() => { armed = null; remove.textContent = "Remove"; remove.classList.remove("sure"); }, 4000);
        return;
      }
      clearTimeout(armed);
      removing = true;
      remove.textContent = "Removing…";
      try {
        await this._hass.callService("virtual", "remove_device",
          { group_name: device.group, device_name: device.key });
      } catch (err) {
        this._say((err && err.message) || "Could not remove it.", true);
        remove.textContent = "Remove"; remove.classList.remove("sure"); armed = null;
        removing = false;
        return;
      }
      this._loadStructure();
    });

    const parts = make("div", "parts");
    tile.append(who, remove, parts);

    // A device with a lot of parts shows its main few; the rest are one click away,
    // searchable, and any can be pinned up to the main list (remembered in this browser).
    const pins = new Set(store.get("pins", {})[device.key] || []);
    const folding = device.entities.length > FOLD_AT;
    const main = folding ? device.entities.filter((e, i) => i < FOLD_AT || pins.has(e.entity_id)) : device.entities;
    const rest = folding ? device.entities.filter((e) => !main.includes(e)) : [];
    for (const entity of main) this._entityRows(entity, device, parts, folding ? pins : null);
    if (rest.length) {
      const more = make("details", "more");
      more.appendChild(make("summary", "", `Show ${rest.length} more`));
      const search = make("input"); search.type = "search"; search.placeholder = "Search these";
      search.setAttribute("aria-label", "Search the other parts");
      const holder = make("div");
      more.append(search, holder);
      for (const entity of rest) this._entityRows(entity, device, holder, pins);
      search.addEventListener("input", () => {
        const needle = search.value.trim().toLowerCase();
        for (const row of holder.querySelectorAll(".part")) row.hidden = !!needle && !row.textContent.toLowerCase().includes(needle);
      });
      tile.appendChild(more);
    }
    return tile;
  }

  /* The rows for one entity: one per control, the first carrying its name and live state.
   * `pins` (a Set) turns on the pin star. */
  _entityRows(entity, device, into, pins) {
    const state = this._hass.states[entity.entity_id];
    const descs = controlsFor(entity.domain, state && state.state, state && state.attributes);
    const rows = [];
    const readoutEl = make("div", "state");
    this._readouts.set(entity.entity_id, readoutEl);
    const label = partLabel(entity.name, device.name, entity.domain);

    const build = (desc, first) => {
      const row = make("div", "part");
      const what = make("div", "what");
      if (first && pins) {
        const pinned = pins.has(entity.entity_id);
        const pin = make("button", "link pin" + (pinned ? " on" : ""), pinned ? "★" : "☆");
        pin.title = pinned ? "Unpin" : "Pin to the main list";
        pin.addEventListener("click", () => this._pin(device, entity.entity_id, !pinned));
        what.appendChild(pin);
      }
      what.appendChild(document.createTextNode(desc.label ? `${label} — ${desc.label}` : label));
      row.appendChild(what);
      if (first) row.appendChild(readoutEl);
      const ctl = make("div", "ctl");
      const input = this._input(entity, desc);
      ctl.appendChild(input.el);
      row.appendChild(ctl);
      rows.push({ desc, set: input.set, row });
      return row;
    };
    if (!descs.length) {
      const row = make("div", "part");
      row.append(make("div", "what", label), readoutEl);
      into.appendChild(row);
    }
    descs.forEach((desc, i) => into.appendChild(build(desc, i === 0)));
    if (entity.domain === "lock") into.appendChild(this._codes(entity));
    // Built before this entity's state had loaded? It may offer different controls once it
    // has (see _updateLive).
    this._rows.set(entity.entity_id, { rows, entity, early: !state });
  }

  _pin(device, entityId, pinned) {
    const all = store.get("pins", {});
    const set = new Set(all[device.key] || []);
    if (pinned) set.add(entityId); else set.delete(entityId);
    all[device.key] = [...set];
    store.set("pins", all);
    this._shown = "";            // the layout changes, so draw it again
    this._renderStructure();
  }

  /* A lock's codes. Type a code and press Lock or Unlock: it is sent with Home Assistant's
   * own `code` field, and the lock records it as `last_code`, so an automation that reacts to
   * a code being used can be tried. Nothing needs saving first. After a code that is not
   * already saved goes through, a line offers to save it. Saved codes are kept in THIS
   * BROWSER only, never in the add-on or Home Assistant. */
  _codes(entity) {
    const wrap = make("div", "codewrap");
    const quick = make("div", "code quick");
    const typed = make("input"); typed.type = "text"; typed.placeholder = "Code";
    typed.setAttribute("aria-label", `${entity.name}: code to send`);
    const lockNow = make("button", "quiet", "Lock"), unlockNow = make("button", "quiet", "Unlock");
    lockNow.setAttribute("aria-label", `${entity.name}: lock with the typed code`);
    unlockNow.setAttribute("aria-label", `${entity.name}: unlock with the typed code`);
    const pick = make("select"); pick.setAttribute("aria-label", `${entity.name}: saved codes`);
    quick.append(typed, lockNow, unlockNow, pick);
    const offer = make("div", "code offer"); offer.hidden = true;
    const details = make("details", "codes");
    const summary = make("summary", "");
    details.appendChild(summary);
    const info = make("div", "codeinfo");
    const list = make("div");
    const form = make("div", "code");
    const name = make("input"); name.type = "text"; name.placeholder = "Name"; name.setAttribute("aria-label", "Name for the code");
    const code = make("input"); code.type = "text"; code.placeholder = "Code"; code.setAttribute("aria-label", "Code");
    const save = make("button", "quiet", "Save a code");
    form.append(name, code, save);
    const fine = make("div", "fine",
      "Saved in this browser only. Home Assistant is sent the code itself (it shows as last_code), so use made-up test codes, never a real one.");
    details.append(info, list, form, fine);

    const all = () => store.get("codes", {});
    const draw = () => {
      const mine = all()[entity.entity_id] || [];
      summary.textContent = `Codes (${mine.length})`;
      pick.textContent = "";
      pick.hidden = mine.length === 0;
      pick.appendChild(make("option", "", "Saved codes…")).value = "";
      mine.forEach((c, i) => { pick.appendChild(make("option", "", `${c.n} — ${c.c}`)).value = String(i); });
      list.textContent = "";
      for (const c of mine) {
        const row = make("div", "code");
        row.append(make("span", "cname", c.n), make("span", "cval", c.c));
        const unlock = make("button", "quiet", "Unlock with it");
        unlock.addEventListener("click", () => this._send(lockWithCode(entity.entity_id, "unlock", c.c)));
        const lock = make("button", "quiet", "Lock with it");
        lock.addEventListener("click", () => this._send(lockWithCode(entity.entity_id, "lock", c.c)));
        const forget = make("button", "link", "Forget");
        forget.addEventListener("click", () => {
          const next = all();
          next[entity.entity_id] = (next[entity.entity_id] || []).filter((x) => x !== c && !(x.n === c.n && x.c === c.c));
          store.set("codes", next);
          draw();
        });
        row.append(unlock, lock, forget);
        list.appendChild(row);
      }
    };
    save.addEventListener("click", () => {
      if (!name.value.trim() || !code.value.trim()) return;
      saveCode(name.value.trim(), code.value.trim());
      name.value = ""; code.value = "";
    });
    const saveCode = (n, c) => {
      const next = all();
      const mine = next[entity.entity_id] || [];
      if (!mine.some((x) => x.n === n && x.c === c)) {   // the same entry twice adds nothing
        next[entity.entity_id] = [...mine, { n, c }];
        store.set("codes", next);
      }
      draw();
    };
    const showOffer = (value) => {
      offer.textContent = "";
      const name = make("input"); name.type = "text"; name.placeholder = "Name (optional)";
      name.setAttribute("aria-label", `${entity.name}: name for the code ${value}`);
      const yes = make("button", "quiet", "Save");
      yes.setAttribute("aria-label", `${entity.name}: save the code ${value}`);
      const no = make("button", "link", "No thanks");
      no.setAttribute("aria-label", `${entity.name}: do not save the code ${value}`);
      yes.addEventListener("click", () => { saveCode(name.value.trim() || value, value); offer.hidden = true; });
      no.addEventListener("click", () => { offer.hidden = true; });
      offer.append(make("span", "", `Save ${value}?`), name, yes, no);
      offer.hidden = false;
    };
    const sendTyped = async (action) => {
      const value = typed.value.trim();
      if (!value) return;
      offer.hidden = true;
      const sent = await this._send(lockWithCode(entity.entity_id, action, value));
      // Not if the box was changed while Home Assistant was answering: the offer would name
      // a code that is no longer the one on screen.
      if (sent && typed.value.trim() === value && !(all()[entity.entity_id] || []).some((x) => x.c === value)) showOffer(value);
    };
    lockNow.addEventListener("click", () => sendTyped("lock"));
    unlockNow.addEventListener("click", () => sendTyped("unlock"));
    // Enter that only finishes an input-method composition is not a send.
    typed.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.isComposing) sendTyped("unlock"); });
    typed.addEventListener("input", () => { offer.hidden = true; });
    pick.addEventListener("change", () => {
      if (!pick.value) return;   // the heading is not a code
      const chosen = (all()[entity.entity_id] || [])[Number(pick.value)];
      if (chosen) typed.value = chosen.c;
      pick.value = "";
      offer.hidden = true;
      typed.focus();
    });
    this._extras.set(entity.entity_id, (attrs) => {
      const last = attrs.last_code;
      info.textContent = last === undefined ? "" : (last ? `Last code used: ${last}` : "No code used on the last action.");
    });
    draw();
    wrap.append(quick, offer, details);
    return wrap;
  }

  /* One control element, wired to its Home Assistant action. `set(desc)` brings it up to
   * date with the current state without disturbing someone typing. */
  _input(entity, desc) {
    const send = (value) => this._call(entity.domain, desc.id, value, entity.entity_id);
    const typing = (el) => this._forceSync !== entity.entity_id && this.shadowRoot.activeElement === el;
    let el;
    switch (desc.kind) {
      case "toggle": {
        el = make("div", "seg");
        const [offWord, onWord] = desc.words || ["Off", "On"];
        const off = make("button", "", offWord), on = make("button", "", onWord);
        off.setAttribute("aria-label", `${entity.name}: ${offWord}`);
        on.setAttribute("aria-label", `${entity.name}: ${onWord}`);
        off.addEventListener("click", () => send(false));
        on.addEventListener("click", () => send(true));
        el.append(off, on);
        return { el, set: (d) => { on.classList.toggle("on", !!d.value); off.classList.toggle("on", !d.value); } };
      }
      case "select": {
        el = make("select");
        el.setAttribute("aria-label", entity.name);
        let signature = "";
        el.addEventListener("change", () => send(el.value));
        return { el, set: (d) => {
          const sig = (d.options || []).join("\u0001");
          if (sig !== signature) {
            signature = sig;
            el.textContent = "";
            for (const option of d.options || []) {
              const o = make("option", "", option);
              o.value = option;
              el.appendChild(o);
            }
          }
          if (!typing(el)) el.value = d.value === undefined || d.value === null ? "" : String(d.value);
        } };
      }
      case "number": case "text": {
        el = make("input");
        el.type = desc.kind === "number" ? "number" : "text";
        if (desc.kind === "number") el.step = desc.step || "any";
        el.setAttribute("aria-label", entity.name);
        let last = "";
        el.addEventListener("change", () => {
          // An emptied number is not a zero: put back what it was, send nothing.
          if (desc.kind === "number" && el.value.trim() === "") { el.value = last; return; }
          send(el.value);
        });
        return { el, set: (d) => {
          last = d.value === undefined || d.value === null ? "" : d.value;
          if (!typing(el)) el.value = last;
        } };
      }
      case "slider": {
        el = make("input");
        el.type = "range"; el.min = "0"; el.max = "1"; el.step = "0.05";
        el.setAttribute("aria-label", entity.name + " volume");
        el.addEventListener("change", () => send(parseFloat(el.value)));
        return { el, set: (d) => { if (!typing(el) && d.value !== undefined && d.value !== null) el.value = d.value; } };
      }
      case "button": {
        el = make("button", "quiet", desc.text);
        el.addEventListener("click", () => send(true));
        return { el, set: () => {} };
      }
      case "fire": {
        // One button per press type; a remote with many types gets a menu instead.
        el = make("div", "events");
        let signature = "";
        return { el, set: (d) => {
          const options = d.options || [];
          const sig = options.join("\u0001");
          if (sig === signature) return;
          signature = sig;
          el.textContent = "";
          if (options.length <= 6) {
            for (const type of options) {
              const b = make("button", "quiet", capital(type.replace(/_/g, " ")));
              b.addEventListener("click", () => send(type));
              el.appendChild(b);
            }
          } else {
            const pick = make("select");
            pick.setAttribute("aria-label", entity.name + " event type");
            for (const type of options) { const o = make("option", "", type); o.value = type; pick.appendChild(o); }
            const go = make("button", "quiet", "Fire");
            go.addEventListener("click", () => send(pick.value));
            el.append(pick, go);
          }
        } };
      }
      default:
        el = make("span");
        return { el, set: () => {} };
    }
  }

  /* Bring every shown control and readout up to date with Home Assistant's own state. Cheap
   * enough to run on every state change anywhere. */
  _updateLive() {
    if (!this._hass) return;
    for (const [entityId, { rows, entity, early }] of this._rows) {
      const state = this._hass.states[entityId];
      const attrs = (state && state.attributes) || {};
      if (early && state) {
        // The controls were chosen without knowing what this entity can do, and controls
        // cannot be taken away in place: draw the list again, once.
        this._renderStructure();
        return;
      }
      const descs = controlsFor(entity.domain, state && state.state, attrs);
      // By id, not position: what an entity offers can change once its state loads.
      for (const row of rows) {
        const desc = descs.find((d) => d.id === row.desc.id);
        if (desc) row.set(desc);
      }
      const out = this._readouts.get(entityId);
      if (out) {
        const shown = readout(entity.domain, state && state.state, attrs);
        if (out.textContent !== shown) {
          const had = out.textContent;
          out.textContent = shown;
          // A change after the first draw is highlighted briefly; the first draw is not.
          if (had && out.parentNode) {
            out.parentNode.classList.remove("flash");
            void out.parentNode.offsetWidth;   // restart the animation if it is already running
            out.parentNode.classList.add("flash");
          }
        }
      }
      const extra = this._extras.get(entityId);
      if (extra && state) extra(attrs);
    }
    // A tile is "on" while any of its parts is doing something.
    for (const tile of this.shadowRoot.querySelectorAll(".tile")) {
      const active = tile.dataset.entities.split(" ").some((id) => {
        const s = this._hass.states[id];
        return s && isActiveState(s.state);
      });
      tile.dataset.on = active ? "1" : "0";
    }
  }

  _applyFilter() {
    const root = this.shadowRoot;
    const needle = root.querySelector("input.search").value.trim().toLowerCase();
    let visible = 0;
    const groups = new Set();
    for (const tile of root.querySelectorAll(".tile")) {
      const show = (!needle || tile.dataset.search.includes(needle)) &&
        (this._kind === "All" || tile.dataset.kind === this._kind);
      tile.hidden = !show;
      if (show) { visible += 1; groups.add(tile.closest("details.group").dataset.group); }
    }
    for (const group of root.querySelectorAll("details.group")) group.hidden = !groups.has(group.dataset.group);
    root.querySelector(".count").textContent = this._devices.length
      ? `${visible} device${visible === 1 ? "" : "s"} in ${groups.size} group${groups.size === 1 ? "" : "s"}` : "";
  }
}

customElements.define("virtual-test-devices-panel", VirtualTestDevicesPanel);
