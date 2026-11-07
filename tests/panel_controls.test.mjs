// What the panel offers for each kind of device, and the Home Assistant action each
// control calls. Run with:  node --test tests/panel_controls.test.mjs
//
// REGRESSION GUARD. The panel is the only way a test device is driven, so a kind of
// device with no control, or a control calling the wrong action, makes that device
// useless for testing without any error. These need no browser and nothing
// installed beyond Node.

import assert from "node:assert/strict";
import { test } from "node:test";

// The panel file defines a custom element when it loads; give it somewhere to.
globalThis.HTMLElement = class {};
globalThis.customElements = { define() {} };
const { controlsFor, callFor, readout, taggedName, buildEntities, toggleWords, partLabel, kindOf,
  categoryOf, isActiveState, lockWithCode } = await import(
  "../custom_components/virtual/frontend/virtual-panel.js");

const E = "x.thing";

// Every platform the add-on provides (see VIRTUAL_PLATFORMS in __init__.py).
const PLATFORMS = ["alarm_control_panel", "binary_sensor", "button", "camera", "climate",
  "cover", "device_tracker", "event", "fan", "humidifier", "light", "lock", "media_player",
  "notify", "number", "select", "sensor", "siren", "switch", "text", "vacuum", "valve"];

test("every platform is either controllable or deliberately read-only", () => {
  const readOnly = PLATFORMS.filter((d) => controlsFor(d, "x", {}).length === 0);
  assert.deepEqual(readOnly.sort(), ["notify"],
    "a platform lost its controls (or one that should be read-only gained some)");
});

test("camera: one button takes a snapshot into the media folder, one fixed file per camera", () => {
  const [control] = controlsFor("camera", "idle", {});
  assert.equal(control.kind, "button");
  assert.equal(control.text, "Take snapshot");
  assert.deepEqual(callFor("camera", control.id, true, "camera.test_front"),
    { domain: "camera", service: "snapshot",
      data: { entity_id: "camera.test_front", filename: "/media/test_front.jpg" } });
  assert.equal(callFor("camera", control.id, true, "camera.test_back").data.filename, "/media/test_back.jpg",
    "a different camera does not overwrite this one's picture");
});

test("an unknown platform shows, and offers nothing", () => {
  assert.deepEqual(controlsFor("something_new", "on", {}), []);
  assert.equal(callFor("something_new", "main", true, E), null);
});

for (const [domain, on, off, state] of [
  ["binary_sensor", ["virtual", "turn_on"], ["virtual", "turn_off"], "on"],
  ["switch", ["switch", "turn_on"], ["switch", "turn_off"], "on"],
  ["light", ["light", "turn_on"], ["light", "turn_off"], "on"],
  ["fan", ["fan", "turn_on"], ["fan", "turn_off"], "on"],
  ["siren", ["siren", "turn_on"], ["siren", "turn_off"], "on"],
  ["lock", ["lock", "unlock"], ["lock", "lock"], "unlocked"],
  ["cover", ["cover", "open_cover"], ["cover", "close_cover"], "open"],
  ["valve", ["valve", "open_valve"], ["valve", "close_valve"], "open"],
]) {
  test(`${domain}: the toggle shows its state and calls the right action both ways`, () => {
    const [control] = controlsFor(domain, state, {});
    assert.equal(control.kind, "toggle");
    assert.equal(control.value, true, "should read as on/open/unlocked");
    assert.equal(controlsFor(domain, "off", {})[0].value, false);
    const up = callFor(domain, "main", true, E);
    const down = callFor(domain, "main", false, E);
    assert.deepEqual([up.domain, up.service], on);
    assert.deepEqual([down.domain, down.service], off);
    assert.deepEqual(up.data, { entity_id: E });
  });
}

test("a closed cover and a locked lock read as off, not just 'not on'", () => {
  assert.equal(controlsFor("cover", "closed", {})[0].value, false);
  assert.equal(controlsFor("lock", "locked", {})[0].value, false);
  assert.equal(controlsFor("valve", "closed", {})[0].value, false);
});

test("sensor and text send the typed value as text; number sends a number", () => {
  assert.deepEqual(callFor("sensor", "main", 42, E),
    { domain: "virtual", service: "set", data: { entity_id: E, value: "42" } });
  assert.deepEqual(callFor("text", "main", "hi", E),
    { domain: "text", service: "set_value", data: { entity_id: E, value: "hi" } });
  assert.deepEqual(callFor("number", "main", "7.5", E),
    { domain: "number", service: "set_value", data: { entity_id: E, value: 7.5 } });
});

test("a select offers its own options and picks one", () => {
  const [control] = controlsFor("select", "b", { options: ["a", "b", "c"] });
  assert.deepEqual(control.options, ["a", "b", "c"]);
  assert.equal(control.value, "b");
  assert.deepEqual(callFor("select", "main", "c", E),
    { domain: "select", service: "select_option", data: { entity_id: E, option: "c" } });
});

test("alarm panel: every state it offers has an action", () => {
  const [control] = controlsFor("alarm_control_panel", "disarmed", {});
  assert.ok(control.options.length >= 6);
  for (const state of control.options) {
    assert.ok(callFor("alarm_control_panel", "main", state, E), `no action for ${state}`);
  }
  assert.equal(callFor("alarm_control_panel", "main", "armed_away", E).service, "alarm_arm_away");
  assert.equal(callFor("alarm_control_panel", "main", "disarmed", E).service, "alarm_disarm");
});

test("vacuum: every state has an action except docked, which nothing can reach", () => {
  const [control] = controlsFor("vacuum", "docked", {});
  for (const state of control.options.filter((s) => s !== "docked")) {
    assert.ok(callFor("vacuum", "main", state, E), `no action for ${state}`);
  }
  assert.equal(callFor("vacuum", "main", "cleaning", E).service, "start");
  // The virtual vacuum's return_to_base ends at "returning", never "docked". Asking
  // for docked must say so, not quietly send the wrong action.
  assert.equal(callFor("vacuum", "main", "docked", E), null);
});

test("humidifier: power and target are separate controls with separate actions", () => {
  const controls = controlsFor("humidifier", "on", { humidity: 45 });
  assert.deepEqual(controls.map((c) => c.id), ["main", "humidity"]);
  assert.equal(controls[1].value, 45);
  assert.equal(callFor("humidifier", "main", false, E).service, "turn_off");
  assert.deepEqual(callFor("humidifier", "humidity", "50", E).data, { entity_id: E, humidity: 50 });
});

test("climate: mode, target and current temperature each reach the right action", () => {
  const controls = controlsFor("climate", "heat", {
    hvac_modes: ["off", "heat"], temperature: 21, current_temperature: 19.5 });
  assert.deepEqual(controls.map((c) => c.id), ["mode", "temperature", "current"]);
  assert.deepEqual(controls[0].options, ["off", "heat"]);
  assert.equal(callFor("climate", "mode", "cool", E).service, "set_hvac_mode");
  assert.deepEqual(callFor("climate", "mode", "cool", E).data, { entity_id: E, hvac_mode: "cool" });
  assert.deepEqual(callFor("climate", "temperature", "22", E),
    { domain: "climate", service: "set_temperature", data: { entity_id: E, temperature: 22 } });
  assert.deepEqual(callFor("climate", "current", "18", E),
    { domain: "virtual", service: "set_current_temperature", data: { entity_id: E, value: 18 } });
});

test("media player: state and volume", () => {
  const controls = controlsFor("media_player", "playing", { volume_level: 0.4 });
  assert.deepEqual(controls.map((c) => c.id), ["state", "volume"]);
  assert.equal(callFor("media_player", "state", "paused", E).service, "media_pause");
  assert.deepEqual(callFor("media_player", "volume", "0.25", E).data, { entity_id: E, volume_level: 0.25 });
});

test("button presses; an event fires the chosen type; a tracker moves", () => {
  assert.deepEqual(callFor("button", "press", true, E),
    { domain: "button", service: "press", data: { entity_id: E } });
  assert.deepEqual(controlsFor("event", "x", { event_types: ["a", "b"] })[0].options, ["a", "b"]);
  assert.ok(controlsFor("event", "x", {})[0].options.includes("press"), "default types");
  assert.deepEqual(callFor("event", "fire", "hold", E),
    { domain: "virtual", service: "fire_event", data: { entity_id: E, event_type: "hold" } });
  assert.deepEqual(callFor("device_tracker", "location", "home", E),
    { domain: "virtual", service: "move", data: { entity_id: E, location: "home" } });
});

test("the readout shows the state with its unit, and says so when there is none", () => {
  assert.equal(readout("sensor", "21", { unit_of_measurement: "°C" }), "21 °C");
  assert.equal(readout("switch", "on", {}), "on");
  assert.equal(readout("switch", undefined, {}), "not loaded");
});

test("a new device is always called Test — something, but never twice", () => {
  assert.equal(taggedName("Garage door"), "Test — Garage door");
  assert.equal(taggedName("  Garage door  "), "Test — Garage door");
  assert.equal(taggedName("Test garage"), "Test garage");
  assert.equal(taggedName("testing 123"), "testing 123");
});

test("a template becomes the entity list create_device takes", () => {
  const one = buildEntities({ entities: [{ platform: "switch" }] }, "Test — Plug");
  assert.deepEqual(one, [{ platform: "switch", name: "Test — Plug" }]);

  const many = buildEntities({ entities: [
    { platform: "binary_sensor", class: "motion" },
    { platform: "sensor", class: "temperature", unit_of_measurement: "°C" },
    { platform: "alarm_control_panel" },
  ] }, "Test — Hall");
  assert.deepEqual(many.map((e) => e.name),
    ["Test — Hall motion", "Test — Hall temperature", "Test — Hall alarm control panel"]);
  assert.equal(many[1].unit_of_measurement, "°C", "the rest of the entity is kept");
});

test("building entities does not change the template it came from", () => {
  const template = { entities: [{ platform: "switch" }] };
  buildEntities(template, "Test — Plug");
  assert.deepEqual(template, { entities: [{ platform: "switch" }] });
});

test("a control is only offered when the device says it can do it", () => {
  const ids = (domain, attrs) => controlsFor(domain, "x", attrs).map((c) => c.id);
  // a thermostat with no target temperature gets no target control, one with does
  assert.deepEqual(ids("climate", { supported_features: 0 }), ["mode", "current"]);
  assert.deepEqual(ids("climate", { supported_features: 1 }), ["mode", "temperature", "current"]);
  // a speaker without volume gets no slider
  assert.deepEqual(ids("media_player", { supported_features: 0 }), ["state"]);
  assert.deepEqual(ids("media_player", { supported_features: 4 }), ["state", "volume"]);
  // nothing reported means nothing is hidden (an entity not loaded yet)
  assert.deepEqual(ids("climate", {}), ["mode", "temperature", "current"]);
  assert.deepEqual(ids("media_player", {}), ["state", "volume"]);
});

// --- the words, names and groupings the tiles are drawn from -----------------------

test("a switch says what it does in words that fit the device", () => {
  assert.deepEqual(toggleWords("lock"), ["Locked", "Unlocked"]);
  assert.deepEqual(toggleWords("cover"), ["Closed", "Open"]);
  assert.deepEqual(toggleWords("valve"), ["Closed", "Open"]);
  assert.deepEqual(toggleWords("light"), ["Off", "On"]);
  assert.deepEqual(toggleWords("binary_sensor", { device_class: "motion" }), ["Clear", "Detected"]);
  assert.deepEqual(toggleWords("binary_sensor", { device_class: "door" }), ["Closed", "Open"]);
  assert.deepEqual(toggleWords("binary_sensor", { device_class: "moisture" }), ["Dry", "Wet"]);
  assert.deepEqual(toggleWords("binary_sensor", {}), ["Off", "On"], "no class: plain words");
  assert.deepEqual(toggleWords("binary_sensor", { device_class: "nonsense" }), ["Off", "On"]);
});

test("a toggle control carries those words", () => {
  const [lock] = controlsFor("lock", "locked", {});
  assert.deepEqual(lock.words, ["Locked", "Unlocked"]);
  const [motion] = controlsFor("binary_sensor", "on", { device_class: "motion" });
  assert.deepEqual(motion.words, ["Clear", "Detected"]);
  assert.equal(motion.value, true);
});

test("a part is named for what it is, not by repeating the device's name", () => {
  assert.equal(partLabel("Test — Hall multi-sensor motion", "Test — Hall multi-sensor", "binary_sensor"), "Motion");
  assert.equal(partLabel("Test — Hall temperature", "Test — Hall", "sensor"), "Temperature");
  assert.equal(partLabel("Test — Lamp", "Test — Lamp", "light"), "Light", "nothing left: its kind");
  assert.equal(partLabel("Something else", "Test — Lamp", "light"), "Something else", "not our prefix: unchanged");
  assert.equal(partLabel("Test — Door code lock", "Test — Door code", "lock"), "Lock");
  assert.equal(partLabel("Test — Alarm panel alarm control panel", "Test — Alarm panel", "alarm_control_panel"), "Alarm control panel");
});

test("a device is described by what is in it", () => {
  assert.equal(kindOf(["light"]), "Light");
  assert.equal(kindOf(["binary_sensor", "sensor", "sensor"]), "Sensor");
  assert.equal(kindOf(["device_tracker", "notify"]), "Tracker + Alert target");
  assert.equal(kindOf(["climate"]), "Thermostat");
  assert.equal(kindOf([]), "Device");
});

test("a real device falls into a clone group by its most telling part", () => {
  assert.equal(categoryOf(["lock"]), "Doors and locks");
  assert.equal(categoryOf(["light", "sensor"]), "Lights and switches", "a bulb with a sensor is still a light");
  assert.equal(categoryOf(["climate", "sensor"]), "Climate and home");
  assert.equal(categoryOf(["device_tracker", "sensor", "notify"]), "Phones and alerts");
  assert.equal(categoryOf(["binary_sensor", "sensor"]), "Sensors and values");
  assert.equal(categoryOf(["camera", "binary_sensor"]), "Media and cameras");
  assert.equal(categoryOf(["something_new"]), "Other");
});

test("what counts as 'doing something right now'", () => {
  for (const s of ["on", "open", "opening", "unlocked", "playing", "heat", "cleaning", "armed_away", "triggered"]) {
    assert.equal(isActiveState(s), true, s);
  }
  for (const s of ["off", "closed", "locked", "idle", "disarmed", "docked", "unavailable", "unknown", "", undefined]) {
    assert.equal(isActiveState(s), false, String(s));
  }
});

test("a lock used with a code sends it with Home Assistant's own code field", () => {
  assert.deepEqual(lockWithCode("lock.front", "unlock", 4821),
    { domain: "lock", service: "unlock", data: { entity_id: "lock.front", code: "4821" } });
  assert.deepEqual(lockWithCode("lock.front", "lock", "0042"),
    { domain: "lock", service: "lock", data: { entity_id: "lock.front", code: "0042" } }, "a leading zero survives");
});

test("a phone template gets the notifier the caller chose; nothing else does", () => {
  const phone = { receives: true, entities: [{ platform: "device_tracker" }, { platform: "notify", class: "app" }] };
  assert.equal(buildEntities(phone, "Test — Mum", "Text").find((e) => e.platform === "notify").class, "sms");
  assert.equal(buildEntities(phone, "Test — Mum", "Push").find((e) => e.platform === "notify").class, "app");
  assert.equal(buildEntities(phone, "Test — Mum").find((e) => e.platform === "notify").class, "app", "no choice: the template's own");
  const target = { entities: [{ platform: "notify", class: "sms" }] };
  assert.equal(buildEntities(target, "Test — T", "Push")[0].class, "sms", "a plain target ignores the choice");
});

test("a value that merely starts with 'on' or 'open' is not 'doing something'", () => {
  for (const s of ["one", "online", "opening_soon", "automatic", "heating_up", "wetness", "armed"]) {
    assert.equal(isActiveState(s), false, s);
  }
  for (const s of ["on", "armed_away", "heat_cool", "triggered"]) assert.equal(isActiveState(s), true, s);
});

test("states that mean 'in the middle of something' light a tile", () => {
  for (const s of ["arming", "pending", "disarming", "returning", "locking", "closing", "jammed"]) {
    assert.equal(isActiveState(s), true, s);
  }
});
