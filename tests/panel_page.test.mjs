// The panel as a page: load the real file into a simulated browser and click through it.
// Run with:   cd tests && npm install --no-save jsdom && node --test panel_page.test.mjs
//
// Needs `jsdom`; without it every test here skips (and says why) rather than fail. It does
// NOT replace opening the panel in a real browser: layout, theme colours and narrow screens
// are not exercised by a simulated page.
//
// REGRESSION GUARD for what a person does with the panel: what each click sends to Home
// Assistant, what a refused action shows, and what is kept or lost when the list refreshes.

import assert from "node:assert/strict";
import { test } from "node:test";
import { pathToFileURL, fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";

let JSDOM = null;
try { ({ JSDOM } = await import("jsdom")); } catch (_e) { /* skipped below */ }
const skip = JSDOM ? false : "jsdom is not installed (cd tests && npm install --no-save jsdom)";

let dom;
if (JSDOM) {
  dom = new JSDOM("<!doctype html><body></body>", { pretendToBeVisual: true, url: "https://example.test/" });
  for (const key of ["HTMLElement", "customElements", "Event", "Node", "localStorage"]) globalThis[key] = dom.window[key];
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  const here = dirname(fileURLToPath(import.meta.url));
  await import(pathToFileURL(resolve(here, "../custom_components/virtual/frontend/virtual-panel.js")).href);
}

const tick = (ms = 20) => new Promise((r) => setTimeout(r, ms));
const fire = (node, type) => node.dispatchEvent(new dom.window.Event(type, { bubbles: true }));

const ent = (entity_id, name) => ({ entity_id, domain: entity_id.split(".")[0], name });
const BIG = Array.from({ length: 8 }, (_, i) => ent(`sensor.t_big_${i}`, `Test — Freezer item ${i}`));
const DEVICES = [
  { group: "Bench", name: "Test — Plug", key: "plug.key", entities: [
    ent("switch.t_plug", "Test — Plug power"), ent("sensor.t_plug_w", "Test — Plug watts")] },
  { group: "Bench", name: "Test — Lamp", key: "lamp.key", entities: [ent("light.t_lamp", "Test — Lamp")] },
  { group: "Other", name: "Test — Mode", key: "mode.key", entities: [ent("select.t_mode", "Test — Mode")] },
];
const baseStates = () => ({
  "switch.t_plug": { state: "off", attributes: {} },
  "light.t_lamp": { state: "on", attributes: {} },
  "sensor.t_plug_w": { state: "3", attributes: { unit_of_measurement: "W" } },
  "select.t_mode": { state: "one", attributes: { options: ["one", "two"] } },
});
const GROUPS = [{ name: "Bench", state: "loaded" }, { name: "Other", state: "loaded" }];
const TEMPLATES = [
  { name: "Switch", category: "Switches and lights", entities: [{ platform: "switch" }] },
  { name: "Multi", category: "Sensors", entities: [{ platform: "binary_sensor", class: "motion" }, { platform: "sensor", class: "temperature" }] },
  { name: "Phone (location and notifications)", category: "Phones and alerts", receives: true,
    entities: [{ platform: "device_tracker" }, { platform: "notify", class: "app" }] },
  { name: "Text message target", category: "Phones and alerts", entities: [{ platform: "notify", class: "sms" }] },
];
const CLONABLE = [
  { device_id: "r1", name: "Hall Thermostat", kind: "ecobee Smart", domains: ["climate", "sensor"], entities: 2 },
  { device_id: "r2", name: "Porch Light", kind: "Hue", domains: ["light"], entities: 1 },
  { device_id: "r3", name: "Jeremy's phone", kind: "Companion app", domains: ["device_tracker", "notify"], entities: 5 },
];

/* A panel on a fake Home Assistant that records every action it is asked to run. */
async function mount({ devices = DEVICES, states = baseStates(), groups = GROUPS, failWith, slowRemove,
  readFails, failType, removeRemoves, exportReply, exportFails, templates = TEMPLATES, slowCreate, slowUnlock } = {}) {
  dom.window.localStorage.clear();
  const calls = [];
  const reads = [];
  const subscriptions = [];
  const hass = {
    states,
    connection: { subscribeEvents: (cb, type) => new Promise((resolveSub) => {
      subscriptions.push({ type, resolveSub });
    }) },
    callWS: async (msg) => {
      reads.push(msg.type);
      if (readFails && (!failType || msg.type === failType)) throw new Error(readFails);
      if (msg.type === "virtual/devices") return { devices };
      if (msg.type === "virtual/groups") return { version: "9.9.9", groups };
      if (msg.type === "virtual/templates") return { templates };
      if (msg.type === "virtual/clonable") return { devices: CLONABLE };
      if (msg.type === "call_service") {
        calls.push([msg.domain, msg.service, msg.service_data, msg.return_response]);
        if (exportFails) throw new Error(exportFails);
        return { response: exportReply || { file: "/config/virtual_export.yaml", devices: 5, entities: 9, skipped: [] } };
      }
      throw new Error("unexpected " + msg.type);
    },
    callService: async (domain, service, data) => {
      calls.push([domain, service, data]);
      if (failWith) throw new Error(failWith);
      if (slowRemove && service === "remove_device") await slowRemove;
      if (slowCreate && service === "create_device") await slowCreate;
      if (slowUnlock && service === "unlock") await slowUnlock;
      if (removeRemoves && service === "remove_device") {
        const at = devices.findIndex((d) => d.key === data.device_name);
        if (at >= 0) devices.splice(at, 1);
      }
    },
  };
  const el = document.createElement("virtual-test-devices-panel");
  document.body.appendChild(el);
  el.hass = hass;
  await tick();
  const root = el.shadowRoot;
  const p = { el, root, calls, reads, hass, subscriptions,
    $: (s) => root.querySelector(s), $$: (s) => [...root.querySelectorAll(s)],
    tab: async (name) => { p.$(`nav.tabs button[data-tab=${name}]`).click(); await tick(); },
    tiles: () => p.$$(".tile"),
    tile: (name) => p.$$(".tile").find((t) => t.querySelector(".dname").textContent === name),
    update: (changes) => { p.el.hass = { ...p.hass, states: { ...p.hass.states, ...changes } }; } };
  return p;
}

// ---------------------------------------------------------------- tabs and layout

test("four tabs, and only the chosen one is shown", { skip }, async () => {
  const p = await mount();
  assert.deepEqual(p.$$("nav.tabs button").map((b) => b.textContent), ["Devices", "Create", "Clone a device", "Clone everything"]);
  const shown = () => p.$$("[data-pane]").filter((x) => !x.hidden).map((x) => x.dataset.pane);
  assert.deepEqual(shown(), ["devices"]);
  for (const name of ["create", "clone", "all", "devices"]) {
    await p.tab(name);
    assert.deepEqual(shown(), [name]);
    assert.ok(p.$(`nav.tabs button[data-tab=${name}]`).classList.contains("sel"));
  }
});

test("the version is shown, for reports", { skip }, async () => {
  assert.equal((await mount()).$(".ver").textContent, "9.9.9");
});

test("the menu button asks Home Assistant to toggle its sidebar", { skip }, async () => {
  const p = await mount();
  let heard = 0;
  document.addEventListener("hass-toggle-menu", () => { heard += 1; });
  p.$("button.menu").click();
  assert.equal(heard, 1);
});

test("Refresh reads everything again", { skip }, async () => {
  const p = await mount();
  const before = p.reads.length;
  p.$("button.refresh").click(); await tick();
  const again = p.reads.slice(before);
  for (const kind of ["virtual/devices", "virtual/groups", "virtual/templates", "virtual/clonable"]) {
    assert.ok(again.includes(kind), `${kind} not read again`);
  }
});

test("each first read that fails is reported on its own", { skip }, async () => {
  for (const type of ["virtual/devices", "virtual/groups", "virtual/templates", "virtual/clonable"]) {
    const p = await mount({ readFails: `broken ${type}`, failType: type });
    assert.match(p.$(".status").textContent, new RegExp(`broken ${type}`), `${type} failure not shown`);
    assert.ok(p.$(".status").classList.contains("error"));
  }
});

// ------------------------------------------------------------- the Devices tab

test("a tile per device under its group, with kind, live state and a count", { skip }, async () => {
  const p = await mount();
  assert.deepEqual(p.$$("details.group > summary").map((s) => s.textContent), ["Bench", "Other"]);
  assert.deepEqual(p.tiles().map((t) => t.querySelector(".dname").textContent), ["Test — Plug", "Test — Lamp", "Test — Mode"]);
  assert.equal(p.tile("Test — Plug").querySelector(".dkind").textContent, "Switch + Sensor");
  assert.deepEqual(p.$$(".part .state").map((s) => s.textContent), ["off", "3 W", "on", "one"]);
  assert.equal(p.$(".count").textContent, "3 devices in 2 groups");
});

test("a part is labelled by what it is, not by the whole name again", { skip }, async () => {
  const p = await mount();
  assert.deepEqual([...p.tile("Test — Plug").querySelectorAll(".what")].map((w) => w.textContent), ["Power", "Watts"]);
  assert.equal(p.tile("Test — Lamp").querySelector(".what").textContent, "Light");
});

test("a switch shows labelled words with the current one lit, and a click sends the action", { skip }, async () => {
  const p = await mount();
  const lamp = p.tile("Test — Lamp");
  const [off, on] = lamp.querySelectorAll(".seg button");
  assert.deepEqual([off.textContent, on.textContent], ["Off", "On"]);
  assert.ok(on.classList.contains("on") && !off.classList.contains("on"));
  off.click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["light", "turn_off", { entity_id: "light.t_lamp" }]);
});

test("a lock and a motion sensor use their own words", { skip }, async () => {
  const devices = [
    { group: "Bench", name: "Test — Door", key: "d", entities: [ent("lock.t_door", "Test — Door")] },
    { group: "Bench", name: "Test — Hall", key: "h", entities: [ent("binary_sensor.t_hall", "Test — Hall")] }];
  const p = await mount({ devices, states: {
    "lock.t_door": { state: "locked", attributes: {} },
    "binary_sensor.t_hall": { state: "on", attributes: { device_class: "motion" } } } });
  assert.deepEqual([...p.tile("Test — Door").querySelectorAll(".seg button")].map((b) => b.textContent), ["Locked", "Unlocked"]);
  assert.deepEqual([...p.tile("Test — Hall").querySelectorAll(".seg button")].map((b) => b.textContent), ["Clear", "Detected"]);
  assert.equal(p.tile("Test — Hall").querySelector(".seg .on").textContent, "Detected");
});

test("a state change from anywhere shows up with no redraw, and lights the tile", { skip }, async () => {
  const p = await mount();
  const before = p.tile("Test — Plug");
  assert.equal(before.dataset.on, "0");
  p.update({ "switch.t_plug": { state: "on", attributes: {} } });
  assert.equal(p.$$(".part .state")[0].textContent, "on");
  assert.ok(before.querySelector(".seg button:last-child").classList.contains("on"));
  assert.equal(p.tile("Test — Plug"), before, "the same element, not a rebuilt one");
  assert.equal(before.dataset.on, "1", "the coloured edge follows what is doing something");
});

test("the other kinds of control send the right action", { skip }, async () => {
  const p = await mount();
  const sel = p.tile("Test — Mode").querySelector("select");
  assert.deepEqual([...sel.options].map((o) => o.value), ["one", "two"]);
  sel.value = "two"; fire(sel, "change");
  assert.deepEqual(p.calls.at(-1), ["select", "select_option", { entity_id: "select.t_mode", option: "two" }]);
  const box = p.tile("Test — Plug").querySelector("input[type=text]");
  box.value = "12"; fire(box, "change");
  assert.deepEqual(p.calls.at(-1), ["virtual", "set", { entity_id: "sensor.t_plug_w", value: "12" }]);
});

test("an emptied number is put back, not sent as zero", { skip }, async () => {
  const devices = [{ group: "Bench", name: "Test — Dial", key: "dial.key", entities: [ent("number.t_dial", "Test — Dial")] }];
  const p = await mount({ devices, states: { "number.t_dial": { state: "7", attributes: {} } } });
  const box = p.$("input[type=number]");
  assert.equal(box.value, "7");
  box.value = ""; fire(box, "change");
  assert.equal(p.calls.length, 0);
  assert.equal(box.value, "7");
  box.value = "9"; fire(box, "change");
  assert.deepEqual(p.calls.at(-1), ["number", "set_value", { entity_id: "number.t_dial", value: 9 }]);
});

test("a camera has a Take snapshot button that saves into the media folder", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Cam", key: "cam", entities: [ent("camera.t_cam", "Test — Cam")] }];
  const p = await mount({ devices, states: { "camera.t_cam": { state: "idle", attributes: {} } } });
  const button = [...p.tile("Test — Cam").querySelectorAll("button")].find((b) => b.textContent === "Take snapshot");
  assert.ok(button, "the camera tile has a Take snapshot button");
  button.click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["camera", "snapshot", { entity_id: "camera.t_cam", filename: "/media/t_cam.jpg" }]);
});

test("a remote gets one button per press type; one with many types gets a menu", { skip }, async () => {
  const devices = [
    { group: "B", name: "Test — Remote", key: "r", entities: [ent("event.t_r", "Test — Remote")] },
    { group: "B", name: "Test — Big remote", key: "b", entities: [ent("event.t_b", "Test — Big remote")] }];
  const p = await mount({ devices, states: {
    "event.t_r": { state: "unknown", attributes: { event_types: ["press", "double_press", "hold"] } },
    "event.t_b": { state: "unknown", attributes: { event_types: ["a", "b", "c", "d", "e", "f", "g"] } } } });
  const buttons = [...p.tile("Test — Remote").querySelectorAll(".events button")];
  assert.deepEqual(buttons.map((b) => b.textContent), ["Press", "Double press", "Hold"]);
  buttons[1].click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["virtual", "fire_event", { entity_id: "event.t_r", event_type: "double_press" }]);
  const big = p.tile("Test — Big remote");
  assert.equal(big.querySelectorAll(".events button").length, 1, "just Fire, behind a menu");
  big.querySelector(".events select").value = "e";
  big.querySelector(".events button").click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["virtual", "fire_event", { entity_id: "event.t_b", event_type: "e" }]);
});

test("search and a kind chip narrow the tiles, and the count follows", { skip }, async () => {
  const p = await mount();
  const s = p.$("input.search");
  s.value = "lamp"; fire(s, "input");
  assert.deepEqual(p.tiles().filter((t) => !t.hidden).map((t) => t.querySelector(".dname").textContent), ["Test — Lamp"]);
  assert.equal(p.$(".count").textContent, "1 device in 1 group");
  s.value = ""; fire(s, "input");
  const chips = p.$$(".kinds .chip").map((c) => c.textContent);
  assert.deepEqual(chips, ["All", "Choice", "Light", "Switch + Sensor"]);
  p.$$(".kinds .chip").find((c) => c.textContent === "Light").click();
  assert.deepEqual(p.tiles().filter((t) => !t.hidden).map((t) => t.querySelector(".dname").textContent), ["Test — Lamp"]);
  assert.ok(p.$$("details.group").find((g) => g.dataset.group === "Other").hidden, "a group with nothing to show is hidden");
  p.$$(".kinds .chip")[0].click();
  assert.equal(p.tiles().filter((t) => !t.hidden).length, 3);
});

test("a group folded shut stays shut when the list is read again", { skip }, async () => {
  const devices = [...DEVICES];
  const p = await mount({ devices });
  const bench = p.$$("details.group")[0];
  bench.open = false; fire(bench, "toggle");
  devices.push({ group: "Other", name: "Test — New", key: "n", entities: [] });
  await p.el._loadStructure();
  assert.equal(p.$$("details.group")[0].open, false);
  assert.equal(p.$$("details.group")[1].open, true);
});

// ------------------------------------------------------------------- big devices

test("a device with many parts shows its main few, and the rest on request, searchable", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Freezer", key: "fz", entities: BIG }];
  const states = Object.fromEntries(BIG.map((e, i) => [e.entity_id, { state: String(i), attributes: {} }]));
  const p = await mount({ devices, states });
  const tile = p.tile("Test — Freezer");
  assert.equal(tile.querySelectorAll(".parts > .part").length, 6, "six up front");
  const more = tile.querySelector("details.more");
  assert.match(more.querySelector("summary").textContent, /Show 2 more/);
  assert.equal(more.querySelectorAll(".part").length, 2);
  const s = more.querySelector("input[type=search]");
  s.value = "item 7"; fire(s, "input");
  const visible = [...more.querySelectorAll(".part")].filter((x) => !x.hidden);
  assert.equal(visible.length, 1);
  assert.match(visible[0].textContent, /7/);
});

test("a part can be pinned to the main list, and it is remembered", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Freezer", key: "fz", entities: BIG }];
  const states = Object.fromEntries(BIG.map((e, i) => [e.entity_id, { state: String(i), attributes: {} }]));
  const p = await mount({ devices, states });
  p.tile("Test — Freezer").querySelector("details.more .pin").click(); await tick();
  const tile = p.tile("Test — Freezer");
  assert.equal(tile.querySelectorAll(".parts > .part").length, 7, "pinned part moved up");
  assert.match(tile.querySelector("details.more summary").textContent, /Show 1 more/);
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:pins")), { fz: ["sensor.t_big_6"] });
});

// ------------------------------------------------------------------- lock codes

const LOCK = [{ group: "Bench", name: "Test — Door", key: "door", entities: [ent("lock.t_door", "Test — Door")] }];
const lockStates = (attrs = {}) => ({ "lock.t_door": { state: "locked", attributes: attrs } });
const redraw = (p) => { p.el._shown = ""; p.el._renderStructure(); };

test("lock codes are saved in the browser, not sent anywhere, and listed", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const codes = p.tile("Test — Door").querySelector("details.codes");
  assert.match(codes.querySelector("summary").textContent, /Codes \(0\)/);
  const [name, code] = codes.querySelectorAll(".code input");
  name.value = "Dana"; code.value = "4821";
  [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
  assert.match(codes.querySelector("summary").textContent, /Codes \(1\)/);
  assert.equal(p.calls.length, 0, "saving a code sends nothing to Home Assistant");
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")), { "lock.t_door": [{ n: "Dana", c: "4821" }] });
});

test("using a code sends it in Home Assistant's own code field, to lock or unlock", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_door": [{ n: "Dana", c: "4821" }] }));
  redraw(p);
  const buttons = [...p.tile("Test — Door").querySelectorAll("details.codes .code button")];
  buttons.find((b) => b.textContent === "Unlock with it").click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "unlock", { entity_id: "lock.t_door", code: "4821" }]);
  buttons.find((b) => b.textContent === "Lock with it").click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "lock", { entity_id: "lock.t_door", code: "4821" }]);
});

test("the last code the lock was sent is shown, and a code can be forgotten", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates({ last_code: "4821", sequence: 3 }) });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_door": [{ n: "Dana", c: "4821" }] }));
  redraw(p);
  const codes = p.tile("Test — Door").querySelector("details.codes");
  assert.match(codes.querySelector(".codeinfo").textContent, /Last code used: 4821/);
  p.update({ "lock.t_door": { state: "unlocked", attributes: { last_code: null, sequence: 4 } } });
  assert.match(codes.querySelector(".codeinfo").textContent, /No code used/);
  [...codes.querySelectorAll("button")].find((b) => b.textContent === "Forget").click();
  assert.match(codes.querySelector("summary").textContent, /Codes \(0\)/);
});

// ------------------------------------------------------- removing, errors, refresh

test("remove takes two clicks, sends the file name in its group, and ignores a third", { skip }, async () => {
  let release;
  const p = await mount({ slowRemove: new Promise((r) => { release = r; }) });
  const btn = p.tile("Test — Lamp").querySelector(".remove");
  btn.click();
  assert.equal(p.calls.length, 0, "the first click only asks");
  assert.match(btn.textContent, /Remove it\?/);
  btn.click(); btn.click(); btn.click();
  await tick();
  assert.deepEqual(p.calls, [["virtual", "remove_device", { group_name: "Bench", device_name: "lamp.key" }]]);
  release();
});

test("a removal that works takes the device off the list without a manual refresh", { skip }, async () => {
  const devices = [...DEVICES];
  const p = await mount({ devices, removeRemoves: true });
  const btn = p.tile("Test — Lamp").querySelector(".remove");
  btn.click(); btn.click(); await tick();
  assert.deepEqual(p.tiles().map((t) => t.querySelector(".dname").textContent), ["Test — Plug", "Test — Mode"]);
});

test("a refused removal is shown and the button comes back", { skip }, async () => {
  const p = await mount({ failWith: "Validation error: no such device" });
  const btn = p.tile("Test — Plug").querySelector(".remove");
  btn.click(); btn.click(); await tick();
  assert.match(p.$(".status").textContent, /no such device/);
  assert.equal(btn.textContent, "Remove");
  btn.click(); assert.match(btn.textContent, /Remove it\?/);
});

test("a device with no file name cannot be removed", { skip }, async () => {
  const p = await mount({ devices: [{ group: "Bench", name: "Orphan", key: null, entities: [] }] });
  assert.equal(p.$(".remove").disabled, true);
});

test("a refused control change is shown and the control goes back to what is true", { skip }, async () => {
  const p = await mount({ failWith: "Validation error: not allowed" });
  const [off, on] = p.tile("Test — Lamp").querySelectorAll(".seg button");
  off.click(); await tick();
  assert.match(p.$(".status").textContent, /not allowed/);
  assert.ok(p.$(".status").classList.contains("error"));
  assert.ok(on.classList.contains("on"), "back to the real state, not left looking changed");
});

test("a refresh that changes nothing does not redraw, so typing and a waiting Remove survive", { skip }, async () => {
  const p = await mount();
  const tile = p.tile("Test — Plug");
  const box = tile.querySelector("input[type=text]");
  box.value = "half typed";
  tile.querySelector(".remove").click();
  await p.el._loadStructure();
  assert.equal(p.tile("Test — Plug"), tile, "not redrawn");
  assert.equal(tile.querySelector("input[type=text]").value, "half typed");
  assert.match(tile.querySelector(".remove").textContent, /Remove it\?/);
});

test("a refresh that does change the list redraws it, and a search stays applied", { skip }, async () => {
  const devices = [...DEVICES];
  const p = await mount({ devices });
  const s = p.$("input.search"); s.value = "lamp"; fire(s, "input");
  devices.push({ group: "Other", name: "Test — Fresh", key: "f", entities: [] });
  await p.el._loadStructure();
  assert.equal(p.tiles().length, 4, "the new device was read");
  assert.deepEqual(p.tiles().filter((t) => !t.hidden).map((t) => t.querySelector(".dname").textContent), ["Test — Lamp"]);
});

test("a field being typed in is not overwritten by a state change", { skip }, async () => {
  const p = await mount();
  const box = p.tile("Test — Plug").querySelector("input[type=text]");
  box.focus();
  assert.equal(p.root.activeElement, box);
  box.value = "half typed";
  p.update({ "sensor.t_plug_w": { state: "99", attributes: {} } });
  assert.equal(box.value, "half typed");
  box.blur();
  p.update({ "sensor.t_plug_w": { state: "98", attributes: {} } });
  assert.equal(box.value, "98");
});

test("controls chosen before state loaded are redrawn once it has", { skip }, async () => {
  const devices = [{ group: "Bench", name: "Test — Heat", key: "h", entities: [ent("climate.t_heat", "Test — Heat")] }];
  const p = await mount({ devices, states: {} });
  assert.equal(p.$$(".part").length >= 3, true, "no state yet: every control is offered");
  p.update({ "climate.t_heat": { state: "off", attributes: { supported_features: 0, hvac_modes: ["off"] } } });
  const labels = p.$$('[data-pane="devices"] .what').map((l) => l.textContent);
  assert.equal(labels.some((l) => /target/.test(l)), false, "target removed once we know it cannot");
  assert.equal(labels.some((l) => /current/.test(l)), true);
});

test("a subscription that finishes after the panel closed is undone; one that finishes while open is kept", { skip }, async () => {
  const closed = await mount();
  closed.el.remove();
  let undone = 0;
  for (const s of closed.subscriptions) s.resolveSub(() => { undone += 1; });
  await tick();
  assert.equal(undone, 2, "both undone");
  const open = await mount();
  let kept = 0;
  for (const s of open.subscriptions) s.resolveSub(() => { kept += 1; });
  await tick();
  assert.equal(kept, 0, "kept while open");
  open.el.remove();
  assert.equal(kept, 2, "undone on close");
});

// --------------------------------------------------------------------- Create tab

test("Create lists the kinds under their category, and needs a pick and a name", { skip }, async () => {
  const p = await mount();
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  assert.deepEqual([...pane.querySelectorAll(".cat")].map((c) => c.textContent), ["Switches and lights", "Sensors", "Phones and alerts"]);
  const go = pane.querySelector(".form button");
  assert.equal(go.disabled, true, "nothing picked yet");
  [...pane.querySelectorAll(".row button")][0].click();
  assert.equal(go.disabled, false);
  go.click(); await tick();
  assert.equal(p.calls.length, 0, "no name: nothing is made");
});

test("Create sends the entities to the chosen group with a Test — name", { skip }, async () => {
  const p = await mount();
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  const picker = pane.querySelector(".groupbar select");
  picker.value = "Other"; fire(picker, "change");
  [...pane.querySelectorAll(".row button")][1].click();
  pane.querySelector("input[type=text]").value = "Hall";
  pane.querySelector(".form button").click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["virtual", "create_device", {
    group_name: "Other", device_name: "Test — Hall",
    entities: [{ platform: "binary_sensor", class: "motion", name: "Test — Hall motion" },
               { platform: "sensor", class: "temperature", name: "Test — Hall temperature" }] }]);
  assert.equal(pane.querySelector("input[type=text]").value, "", "name cleared after it worked");
});

test("only a kind that receives messages asks push or text, and the choice reaches the notifier", { skip }, async () => {
  const p = await mount();
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  const alert = pane.querySelector(".opt");
  const rows = [...pane.querySelectorAll(".row button")];
  assert.equal(alert.hidden, true, "nothing picked");
  rows[0].click();
  assert.equal(alert.hidden, true, "a switch never asks");
  rows[2].click();
  assert.equal(alert.hidden, false, "a phone does");
  [...alert.querySelectorAll(".seg button")].find((b) => b.textContent === "Text").click();
  pane.querySelector("input[type=text]").value = "Mum";
  pane.querySelector(".form button").click(); await tick();
  const sent = p.calls.at(-1)[2];
  assert.equal(sent.entities.find((e) => e.platform === "notify").class, "sms");
  assert.equal(sent.entities.find((e) => e.platform === "device_tracker").name, "Test — Mum device tracker");
});

test("Create: a stopped group cannot be chosen, and with none running nothing can be added", { skip }, async () => {
  const some = await mount({ groups: [{ name: "Broken", state: "setup_retry" }, { name: "Bench", state: "loaded" }] });
  await some.tab("create");
  const picker = some.$('[data-pane="create"] .groupbar select');
  assert.equal([...picker.options][0].disabled, true);
  assert.equal(picker.value, "Bench");
  const none = await mount({ groups: [{ name: "Broken", state: "setup_retry" }] });
  await none.tab("create");
  assert.match(none.$('[data-pane="create"]').textContent, /No group is running/);
  assert.equal(none.$$('[data-pane="create"] .row').length, 0);
});

// ---------------------------------------------------------------- Clone a device tab

test("Clone lists real devices, offers push or text only when asked, and sends what was chosen", { skip }, async () => {
  const p = await mount();
  await p.tab("clone");
  const pane = p.$('[data-pane="clone"]');
  const rows = () => [...pane.querySelectorAll(".row")];
  assert.deepEqual(rows().map((r) => r.querySelector(".what").firstChild.textContent), ["Hall Thermostat", "Porch Light", "Jeremy's phone"]);
  assert.equal(pane.querySelectorAll(".row select").length, 0, "no push/text menu on any row");
  assert.match(rows()[0].querySelector("small").textContent, /2 entities/);

  const picker = pane.querySelector(".groupbar select");
  picker.value = "Other"; fire(picker, "change");
  rows()[1].querySelector("button").click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["virtual", "clone_device", { group_name: "Other", device_id: "r2" }], "as is");

  const option = pane.querySelector("input[type=checkbox]");
  const seg = pane.querySelector(".opt .seg");
  assert.equal(seg.hidden, true);
  option.checked = true; fire(option, "change");
  assert.equal(seg.hidden, false);
  rows()[2].querySelector("button").click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["virtual", "clone_device", { group_name: "Other", device_id: "r3", notify_as: "app", add_notifier: true }]);
  [...seg.querySelectorAll("button")].find((b) => b.textContent === "Text").click();
  rows()[2].querySelector("button").click(); await tick();
  assert.deepEqual(p.calls.at(-1)[2], { group_name: "Other", device_id: "r3", notify_as: "sms", add_notifier: true });
});

test("Clone: chips group the real devices, search narrows them, a refusal is shown", { skip }, async () => {
  const p = await mount({ failWith: "Validation error: already has a device" });
  await p.tab("clone");
  const pane = p.$('[data-pane="clone"]');
  assert.deepEqual([...pane.querySelectorAll(".chips .chip")].map((c) => c.textContent),
    ["All", "Climate and home", "Lights and switches", "Phones and alerts"]);
  [...pane.querySelectorAll(".chips .chip")].find((c) => c.textContent === "Lights and switches").click();
  assert.equal(pane.querySelectorAll(".row").length, 1);
  [...pane.querySelectorAll(".chips .chip")][0].click();
  const s = pane.querySelector("input[type=search]"); s.value = "thermo"; fire(s, "input");
  assert.equal(pane.querySelectorAll(".row").length, 1);
  const button = pane.querySelector(".row button");
  button.click(); await tick();
  assert.match(p.$(".status").textContent, /already has a device/);
  assert.ok(p.$(".status").classList.contains("error"));
  assert.equal(button.disabled, false);
});

// ----------------------------------------------------------- Clone everything tab

test("Export sends only what was filled in, and reports what it wrote and what it left out", { skip }, async () => {
  const p = await mount({ exportReply: { file: "/config/x.yaml", devices: 4, entities: 7,
    skipped: [{ entity_id: "sensor.cpu", reason: "integration hassio excluded" }, { domain: "update", count: 6, reason: "domain not reproducible" }] } });
  await p.tab("all");
  const pane = p.$('[data-pane="all"]');
  const inputs = [...pane.querySelectorAll(".opt input[type=text]")];
  inputs[0].value = "x.yaml";
  inputs[3].value = "sensor.*_power, light.hall";
  pane.querySelector("button.primary").click(); await tick();
  assert.deepEqual(p.calls.at(-1), ["virtual", "export_devices",
    { file: "x.yaml", exclude_entities: ["sensor.*_power", "light.hall"] }, true],
    "empty fields are left out, so the add-on's own defaults apply");
  const out = pane.querySelector(".status");
  assert.match(out.textContent, /Wrote \/config\/x\.yaml: 7 entities in 4 devices\. 2 left out/);
  assert.match(out.textContent, /sensor\.cpu: integration hassio excluded/);
  assert.match(out.textContent, /6 x update\.\*: domain not reproducible/);
});

test("Export: keep-state is sent when ticked, and a failure is shown", { skip }, async () => {
  const p = await mount({ exportFails: "not exporting: that is a group's own devices file" });
  await p.tab("all");
  const pane = p.$('[data-pane="all"]');
  pane.querySelector("input[type=checkbox]").checked = true;
  pane.querySelector("button.primary").click(); await tick();
  assert.equal(p.calls.at(-1)[2].persistent, true);
  assert.match(pane.querySelector(".status").textContent, /group's own devices file/);
  assert.ok(pane.querySelector(".status").classList.contains("error"));
  assert.equal(pane.querySelector("button.primary").disabled, false);
});

test("Clone everything says plainly that bringing devices in is not built yet", { skip }, async () => {
  const p = await mount();
  await p.tab("all");
  assert.match(p.$('[data-pane="all"]').textContent, /Coming next/);
});

// --- found by the review agents ------------------------------------------------------

test("a refused choice on a select that still has focus is put back, not left showing", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Vac", key: "v", entities: [ent("vacuum.t_vac", "Test — Vac")] }];
  const p = await mount({ devices, states: { "vacuum.t_vac": { state: "idle", attributes: {} } } });
  const sel = p.tile("Test — Vac").querySelector("select");
  sel.focus();
  assert.equal(p.root.activeElement, sel, "the select has focus, as it does after a choice");
  sel.value = "docked"; fire(sel, "change"); await tick();
  assert.match(p.$(".status").textContent, /cannot be set to "docked"/);
  assert.equal(sel.value, "idle", "back to the real state although focused");
});

test("the group chosen on one tab is the one shown, and used, on the others", { skip }, async () => {
  const p = await mount();
  await p.tab("create");
  const create = p.$('[data-pane="create"] .groupbar select');
  create.value = "Other"; fire(create, "change");
  await p.tab("clone");
  const clone = p.$('[data-pane="clone"] .groupbar select');
  assert.equal(clone.value, "Other", "the Clone picker follows");
  p.$('[data-pane="clone"] .row button').click(); await tick();
  assert.equal(p.calls.at(-1)[2].group_name, "Other");
});

test("each category heading appears once, however the kinds are ordered", { skip }, async () => {
  const templates = [
    { name: "A", category: "Sensors", entities: [{ platform: "sensor" }] },
    { name: "B", category: "Switches", entities: [{ platform: "switch" }] },
    { name: "C", category: "Sensors", entities: [{ platform: "sensor" }] }];
  const p = await mount({ templates });
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  assert.deepEqual([...pane.querySelectorAll(".cat")].map((c) => c.textContent), ["Sensors", "Switches"]);
  assert.deepEqual([...pane.querySelectorAll(".row .what")].map((c) => c.textContent), ["A", "C", "B"]);
  [...pane.querySelectorAll(".row button")][2].click();   // the third row is B
  pane.querySelector("input[type=text]").value = "Plug";
  pane.querySelector(".form button").click(); await tick();
  assert.equal(p.calls.at(-1)[2].entities[0].platform, "switch", "the row picked is the kind made");
});

test("pressing Enter twice on the name makes one device, not two", { skip }, async () => {
  let release;
  const p = await mount({ slowCreate: new Promise((r) => { release = r; }) });
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  [...pane.querySelectorAll(".row button")][0].click();
  const name = pane.querySelector("input[type=text]");
  name.value = "Plug";
  fire(name, "keydown");   // not Enter: nothing
  const enter = () => name.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  enter(); enter(); enter();
  await tick();
  assert.equal(p.calls.filter((c) => c[1] === "create_device").length, 1);
  release();
});

test("a choice-list value that merely starts with 'on' does not light the tile", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Pick", key: "p", entities: [ent("select.t_pick", "Test — Pick")] }];
  const p = await mount({ devices, states: { "select.t_pick": { state: "one", attributes: { options: ["one", "two"] } } } });
  assert.equal(p.tile("Test — Pick").dataset.on, "0");
});

// --- the review of the tests: things that were right but not proved ------------------

test("the group you chose is still the chosen one after Refresh", { skip }, async () => {
  const p = await mount();
  await p.tab("create");
  const pick = p.$('[data-pane="create"] .groupbar select');
  pick.value = "Other"; fire(pick, "change");
  p.$("button.refresh").click(); await tick();
  assert.equal(p.$('[data-pane="create"] .groupbar select').value, "Other");
  await p.tab("clone");
  p.$('[data-pane="clone"] .row button').click(); await tick();
  assert.equal(p.calls.at(-1)[2].group_name, "Other");
});

test("forgetting one lock's code leaves every other lock's codes alone", { skip }, async () => {
  const devices = [
    { group: "B", name: "Test — Front", key: "f", entities: [ent("lock.t_front", "Test — Front")] },
    { group: "B", name: "Test — Back", key: "b", entities: [ent("lock.t_back", "Test — Back")] }];
  const states = { "lock.t_front": { state: "locked", attributes: {} }, "lock.t_back": { state: "locked", attributes: {} } };
  const p = await mount({ devices, states });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({
    "lock.t_front": [{ n: "Dana", c: "1111" }], "lock.t_back": [{ n: "Guest", c: "2222" }] }));
  p.el._shown = ""; p.el._renderStructure();
  const front = p.tile("Test — Front").querySelector("details.codes");
  [...front.querySelectorAll("button")].find((b) => b.textContent === "Forget").click();
  assert.equal(front.querySelector("summary").textContent, "Codes (0)");
  assert.equal(p.tile("Test — Back").querySelector("details.codes summary").textContent, "Codes (1)");
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")),
    { "lock.t_front": [], "lock.t_back": [{ n: "Guest", c: "2222" }] });
});

test("a code with no name or no code is not saved", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const codes = p.tile("Test — Door").querySelector("details.codes");
  const [name, code] = codes.querySelectorAll(".code input");
  const save = () => [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
  name.value = "Dana"; code.value = ""; save();
  name.value = ""; code.value = "4821"; save();
  assert.equal(codes.querySelector("summary").textContent, "Codes (0)");
  assert.equal(dom.window.localStorage.getItem("virtual-panel:codes"), null, "nothing was stored");
});

test("a pinned part can be unpinned again, and only that pin goes", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Freezer", key: "fz", entities: BIG }];
  const states = Object.fromEntries(BIG.map((e, i) => [e.entity_id, { state: String(i), attributes: {} }]));
  const p = await mount({ devices, states });
  const pinFolded = (n) => p.tile("Test — Freezer").querySelectorAll("details.more .pin")[n].click();
  pinFolded(0); await tick();
  pinFolded(0); await tick();                       // the second folded part is now first
  let tile = p.tile("Test — Freezer");
  assert.equal(tile.querySelectorAll(".parts > .part").length, 8, "both pinned, nothing folded");
  const stars = [...tile.querySelectorAll(".parts > .part .pin.on")];
  assert.equal(stars.length, 2, "a pinned part in the main list shows a lit star");
  stars[0].click(); await tick();
  tile = p.tile("Test — Freezer");
  assert.equal(tile.querySelectorAll(".parts > .part").length, 7, "one part went back");
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:pins")), { fz: ["sensor.t_big_7"] });
});

test("Clone: no push or text choice on any row, and unticking the option hides it again", { skip }, async () => {
  const p = await mount();
  await p.tab("clone");
  const pane = p.$('[data-pane="clone"]');
  assert.equal(pane.querySelectorAll(".row .seg, .row select").length, 0, "nothing per row, of any kind");
  const option = pane.querySelector("input[type=checkbox]");
  const seg = pane.querySelector(".opt .seg");
  option.checked = true; fire(option, "change");
  assert.equal(seg.hidden, false);
  assert.equal(pane.querySelectorAll(".row .seg, .row select").length, 0, "still nothing per row");
  option.checked = false; fire(option, "change");
  assert.equal(seg.hidden, true, "unticked: hidden again");
  p.$('[data-pane="clone"] .row button').click(); await tick();
  assert.equal("notify_as" in p.calls.at(-1)[2], false, "unticked means nothing is sent about push or text");
});

test("a plain message target keeps its own kind even though the choice says push", { skip }, async () => {
  const p = await mount();
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  const rows = [...pane.querySelectorAll(".row button")];
  assert.equal(pane.querySelectorAll(".row .what").length, 4);
  rows[2].click();                                                   // the phone: leaves its choice on Push
  rows[3].click();                                                   // then a target that is a text target
  assert.equal(pane.querySelector(".opt").hidden, true, "a target is not a phone: no choice");
  pane.querySelector("input[type=text]").value = "Alerts";
  pane.querySelector(".form button").click(); await tick();
  assert.equal(p.calls.at(-1)[2].entities[0].class, "sms", "it stayed a text target");
});

test("after a create finishes, the next kind can be picked and created", { skip }, async () => {
  const p = await mount();
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  const go = pane.querySelector(".form button");
  const name = pane.querySelector("input[type=text]");
  [...pane.querySelectorAll(".row button")][0].click();
  name.value = "One"; go.click(); await tick();
  assert.equal(go.disabled, false, "free again once the create is done");
  [...pane.querySelectorAll(".row button")][1].click();
  assert.equal(go.disabled, false, "and picking another kind does not leave it disabled");
  name.value = "Two"; go.click(); await tick();
  assert.equal(p.calls.filter((c) => c[1] === "create_device").length, 2);
});

test("after a refused change, a later live update still leaves that field alone while it is typed in", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Vac", key: "v", entities: [ent("vacuum.t_vac", "Test — Vac")] }];
  const p = await mount({ devices, states: { "vacuum.t_vac": { state: "idle", attributes: {} } } });
  const sel = p.tile("Test — Vac").querySelector("select");
  sel.focus(); sel.value = "docked"; fire(sel, "change"); await tick();   // refused, put back
  assert.equal(sel.value, "idle");
  sel.value = "paused";                                                    // the person goes on choosing
  p.update({ "vacuum.t_vac": { state: "idle", attributes: {} } });
  assert.equal(sel.value, "paused", "the put-back mode did not stay switched on");
});

test("the search also matches a device's group name", { skip }, async () => {
  const p = await mount();
  const s = p.$("input.search"); s.value = "other"; fire(s, "input");
  assert.deepEqual(p.tiles().filter((t) => !t.hidden).map((t) => t.querySelector(".dname").textContent), ["Test — Mode"]);
});

// --- typing a code and sending it, with nothing saved first ---------------------------

const quickOf = (p, tile = "Test — Door") => {
  const t = p.tile(tile);
  const q = t.querySelector(".quick");
  const press = (word) => [...q.querySelectorAll("button")].find((b) => b.textContent === word).click();
  return { t, q, box: q.querySelector("input"), pick: q.querySelector("select"), press,
    offer: t.querySelector(".offer") };
};

test("type a code and press Unlock or Lock: it is sent at once, with nothing saved first", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "unlock", { entity_id: "lock.t_door", code: "4821" }]);
  k.press("Lock"); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "lock", { entity_id: "lock.t_door", code: "4821" }]);
  assert.equal(p.calls.length, 2, "the same code twice is two sends");
  assert.equal(dom.window.localStorage.getItem("virtual-panel:codes"), null, "nothing was saved");
});

test("pressing Enter in the code box unlocks with it", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "1234";
  k.box.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "unlock", { entity_id: "lock.t_door", code: "1234" }]);
});

test("an empty code box sends nothing", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "   "; k.press("Unlock"); k.press("Lock"); await tick();
  assert.equal(p.calls.length, 0);
  assert.equal(k.offer.hidden, true);
});

test("after a new code goes through, a line offers to save it; the name is optional", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  assert.equal(k.offer.hidden, true, "no offer before anything is sent");
  assert.equal(k.pick.hidden, true, "no saved-codes menu while none are saved");
  k.box.value = "4821"; k.press("Unlock"); await tick();
  assert.equal(k.offer.hidden, false);
  assert.match(k.offer.textContent, /Save 4821\?/);
  [...k.offer.querySelectorAll("button")].find((b) => b.textContent === "Save").click();   // no name given
  assert.equal(k.offer.hidden, true);
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")), { "lock.t_door": [{ n: "4821", c: "4821" }] },
    "saved under the number when no name was typed");
  assert.match(k.t.querySelector("details.codes summary").textContent, /Codes \(1\)/);
  assert.equal(p.calls.length, 1, "saving sends nothing more");
});

test("the offer takes a name, and 'No thanks' saves nothing", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  k.offer.querySelector("input").value = "Dana";
  [...k.offer.querySelectorAll("button")].find((b) => b.textContent === "Save").click();
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")), { "lock.t_door": [{ n: "Dana", c: "4821" }] });
  k.box.value = "9999"; k.press("Lock"); await tick();
  assert.equal(k.offer.hidden, false);
  [...k.offer.querySelectorAll("button")].find((b) => b.textContent === "No thanks").click();
  assert.equal(k.offer.hidden, true);
  assert.equal(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes"))["lock.t_door"].length, 1, "9999 was not saved");
});

test("a code that is already saved is not offered again", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_door": [{ n: "Dana", c: "4821" }] }));
  redraw(p);
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  assert.equal(k.offer.hidden, true);
});

test("no offer when Home Assistant refuses the code", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates(), failWith: "Invalid code" });
  const k = quickOf(p);
  k.box.value = "0000"; k.press("Unlock"); await tick();
  assert.equal(k.offer.hidden, true, "a refused code is not offered for saving");
  assert.match(p.$(".status").textContent, /Invalid code/, "the reason is shown");
});

test("typing in the code box takes the offer away", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  assert.equal(k.offer.hidden, false);
  k.box.value = "48"; fire(k.box, "input");
  assert.equal(k.offer.hidden, true);
});

test("choosing a saved code fills the box and sends nothing", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_door": [
    { n: "Dana", c: "4821" }, { n: "Guest", c: "1111" }] }));
  redraw(p);
  const k = quickOf(p);
  assert.equal(k.pick.hidden, false);
  assert.deepEqual([...k.pick.options].map((o) => o.textContent), ["Saved codes…", "Dana — 4821", "Guest — 1111"]);
  k.pick.value = "1"; fire(k.pick, "change");
  assert.equal(k.box.value, "1111");
  assert.equal(k.pick.value, "", "the menu goes back to its heading");
  assert.equal(p.calls.length, 0, "choosing sends nothing; one more press does");
  k.press("Unlock"); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "unlock", { entity_id: "lock.t_door", code: "1111" }]);
});

test("if the box is changed while Home Assistant is still answering, no offer names the old code", { skip }, async () => {
  let release;
  const p = await mount({ devices: LOCK, states: lockStates(), slowUnlock: new Promise((r) => { release = r; }) });
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  k.box.value = "9999"; fire(k.box, "input");
  release(); await tick();
  assert.equal(k.offer.hidden, true, "the box no longer holds the code that was sent");
});

test("Save in the offer twice (or after the same entry was saved another way) adds it once", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  k.offer.querySelector("input").value = "Dana";
  const save = [...k.offer.querySelectorAll("button")].find((b) => b.textContent === "Save");
  save.click(); save.click();
  const codes = p.tile("Test — Door").querySelector("details.codes");
  const [name, code] = codes.querySelectorAll(".code input");
  name.value = "Dana"; code.value = "4821";
  [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")), { "lock.t_door": [{ n: "Dana", c: "4821" }] });
  assert.equal(k.pick.options.length, 2, "heading plus one code in the menu");
});

test("Enter that only finishes an input-method composition sends nothing", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "4821";
  k.box.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", isComposing: true, bubbles: true })); await tick();
  assert.equal(p.calls.length, 0);
});

test("choosing the menu's heading does not pick the first saved code", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_door": [{ n: "Dana", c: "4821" }] }));
  redraw(p);
  const k = quickOf(p);
  k.pick.value = ""; fire(k.pick, "change");
  assert.equal(k.box.value, "", "the heading is not a code");
});

test("the offer's controls say which lock and code they are for", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  for (const el of k.offer.querySelectorAll("input, button")) {
    assert.match(el.getAttribute("aria-label"), /Test — Door: .*4821/, "labelled with the lock and the code");
  }
});

test("a code typed with spaces around it is sent without them, and still gets its offer", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "  4821  "; k.press("Unlock"); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "unlock", { entity_id: "lock.t_door", code: "4821" }]);
  assert.equal(k.offer.hidden, false);
  assert.match(k.offer.textContent, /Save 4821\?/);
});

test("picking a saved code by its text puts exactly that code in the box", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_door": [
    { n: "Dana", c: "4821" }, { n: "Guest", c: "1111" }, { n: "Spare", c: "2222" }] }));
  redraw(p);
  const k = quickOf(p);
  for (const [text, code] of [["Dana — 4821", "4821"], ["Guest — 1111", "1111"], ["Spare — 2222", "2222"]]) {
    k.pick.value = [...k.pick.options].find((o) => o.textContent === text).value; fire(k.pick, "change");
    assert.equal(k.box.value, code, text);
  }
});

test("forgetting one of several saved codes removes only that one", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_door": [
    { n: "Dana", c: "4821" }, { n: "Spare", c: "4821" }, { n: "Dana", c: "2222" }, { n: "Guest", c: "1111" }] }));
  redraw(p);
  const codes = p.tile("Test — Door").querySelector("details.codes");
  [...codes.querySelectorAll("button")].filter((b) => b.textContent === "Forget")[0].click();
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")), { "lock.t_door": [
    { n: "Spare", c: "4821" }, { n: "Dana", c: "2222" }, { n: "Guest", c: "1111" }] },
    "same code under another name, same name with another code, and others all stay");
  assert.match(codes.querySelector("summary").textContent, /Codes \(3\)/);
  assert.equal(quickOf(p).pick.options.length, 4, "the menu follows: heading plus three");
});

test("a code saved on another lock does not stop the offer on this one", { skip }, async () => {
  const devices = [
    { group: "B", name: "Test — Front", key: "f", entities: [ent("lock.t_front", "Test — Front")] },
    { group: "B", name: "Test — Back", key: "b", entities: [ent("lock.t_back", "Test — Back")] }];
  const states = { "lock.t_front": { state: "locked", attributes: {} }, "lock.t_back": { state: "locked", attributes: {} } };
  const p = await mount({ devices, states });
  dom.window.localStorage.setItem("virtual-panel:codes", JSON.stringify({ "lock.t_back": [{ n: "Dana", c: "4821" }] }));
  redraw(p);
  const front = quickOf(p, "Test — Front");
  front.box.value = "4821"; front.press("Unlock"); await tick();
  assert.equal(front.offer.hidden, false, "saved on the back door, not the front");
});

test("the same code can be kept under two names (only an identical entry is refused)", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const codes = p.tile("Test — Door").querySelector("details.codes");
  const [name, code] = codes.querySelectorAll(".code input");
  const save = () => [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
  name.value = "Dana"; code.value = "4821"; save();
  name.value = "Spare"; code.value = "4821"; save();
  name.value = "Dana"; code.value = "2222"; save();       // and one name can hold two codes
  assert.match(codes.querySelector("summary").textContent, /Codes \(3\)/);
});

test("the manual save form trims what was typed and empties itself", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const codes = p.tile("Test — Door").querySelector("details.codes");
  const [name, code] = codes.querySelectorAll(".code input");
  name.value = "  Dana "; code.value = " 4821  ";
  [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")), { "lock.t_door": [{ n: "Dana", c: "4821" }] });
  assert.equal(name.value, ""); assert.equal(code.value, "", "ready for the next one");
});

test("a name typed with spaces in the offer is saved trimmed", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const k = quickOf(p);
  k.box.value = "4821"; k.press("Unlock"); await tick();
  k.offer.querySelector("input").value = "  Dana  ";
  [...k.offer.querySelectorAll("button")].find((b) => b.textContent === "Save").click();
  assert.deepEqual(JSON.parse(dom.window.localStorage.getItem("virtual-panel:codes")), { "lock.t_door": [{ n: "Dana", c: "4821" }] });
});

test("two locks keep their own typed codes and saved codes apart", { skip }, async () => {
  const devices = [
    { group: "B", name: "Test — Front", key: "f", entities: [ent("lock.t_front", "Test — Front")] },
    { group: "B", name: "Test — Back", key: "b", entities: [ent("lock.t_back", "Test — Back")] }];
  const states = { "lock.t_front": { state: "locked", attributes: {} }, "lock.t_back": { state: "locked", attributes: {} } };
  const p = await mount({ devices, states });
  const front = quickOf(p, "Test — Front"), back = quickOf(p, "Test — Back");
  front.box.value = "1111"; front.press("Unlock"); await tick();
  assert.deepEqual(p.calls.at(-1), ["lock", "unlock", { entity_id: "lock.t_front", code: "1111" }]);
  assert.equal(back.box.value, "");
  assert.equal(back.offer.hidden, true, "the other lock got no offer");
  [...front.offer.querySelectorAll("button")].find((b) => b.textContent === "Save").click();
  assert.equal(back.pick.hidden, true, "the other lock has no saved codes");
});

// KEEP THIS LAST: it makes the browser refuse to store anything, and the panel remembers
// which keys it could not store for the rest of the file.
test("when the browser will not store anything, saved codes still work for this visit", { skip }, async () => {
  const p = await mount({ devices: LOCK, states: lockStates() });
  const original = dom.window.Storage.prototype.setItem;
  dom.window.Storage.prototype.setItem = () => { throw new Error("storage is not available"); };
  try {
    const codes = p.tile("Test — Door").querySelector("details.codes");
    const [name, code] = codes.querySelectorAll(".code input");
    name.value = "Dana"; code.value = "4821";
    [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
    assert.equal(codes.querySelector("summary").textContent, "Codes (1)", "the code was kept");
    [...codes.querySelectorAll(".code button")].find((b) => b.textContent === "Unlock with it").click(); await tick();
    assert.deepEqual(p.calls.at(-1), ["lock", "unlock", { entity_id: "lock.t_door", code: "4821" }]);
  } finally { dom.window.Storage.prototype.setItem = original; }
});

// --- found by the second code review of the fixes ------------------------------------

test("a refused change puts back that entity only, not a value being typed elsewhere", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Pair", key: "pair", entities: [
    ent("number.t_a", "Test — Pair a"), ent("select.t_b", "Test — Pair b")] }];
  const p = await mount({ devices, failWith: "Validation error: refused", states: {
    "number.t_a": { state: "5", attributes: {} }, "select.t_b": { state: "x", attributes: { options: ["x", "y"] } } } });
  const a = p.tile("Test — Pair").querySelector("input[type=number]");
  const b = p.tile("Test — Pair").querySelector("select");
  a.focus(); a.value = "21";                       // half typed, not yet sent
  b.value = "y"; fire(b, "change"); await tick();  // a different control is refused
  assert.equal(b.value, "x", "the refused control went back");
  assert.equal(a.value, "21", "what was being typed elsewhere was left alone");
});

test("a literal null or broken text in the browser's storage does not break the list", { skip }, async () => {
  const devices = [{ group: "B", name: "Test — Freezer", key: "fz", entities: BIG }];
  const states = Object.fromEntries(BIG.map((e, i) => [e.entity_id, { state: String(i), attributes: {} }]));
  const p = await mount({ devices, states });
  dom.window.localStorage.setItem("virtual-panel:pins", "null");
  dom.window.localStorage.setItem("virtual-panel:codes", "{not json");
  p.el._shown = ""; p.el._renderStructure();
  assert.equal(p.tiles().length, 1, "the list still draws");
});

test("choosing another kind while a create is in flight does not allow a second create", { skip }, async () => {
  let release;
  const p = await mount({ slowCreate: new Promise((r) => { release = r; }) });
  await p.tab("create");
  const pane = p.$('[data-pane="create"]');
  [...pane.querySelectorAll(".row button")][0].click();
  const name = pane.querySelector("input[type=text]");
  name.value = "Plug";
  const enter = () => name.dispatchEvent(new dom.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  enter(); await tick();
  [...pane.querySelectorAll(".row button")][1].click();      // pick another kind meanwhile
  enter(); await tick();
  assert.equal(p.calls.filter((c) => c[1] === "create_device").length, 1);
  release();
});

// KEEP THIS LAST (and the one before it near the end): they make the browser refuse to store,
// and the panel remembers which keys it could not store for the rest of the file.
test("a second code saved after the browser started refusing still appears", { skip }, async () => {
  // Its own lock, so what the test before it left in the page's memory does not matter.
  const devices = [{ group: "Bench", name: "Test — Gate", key: "gate", entities: [ent("lock.t_gate", "Test — Gate")] }];
  const p = await mount({ devices, states: { "lock.t_gate": { state: "locked", attributes: {} } } });
  const codes = p.tile("Test — Gate").querySelector("details.codes");
  const save = (n, c) => {
    const [name, code] = codes.querySelectorAll(".code input");
    name.value = n; code.value = c;
    [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
  };
  save("Dana", "4821");                                       // stored normally
  assert.equal(codes.querySelector("summary").textContent, "Codes (1)");
  const original = dom.window.Storage.prototype.setItem;
  dom.window.Storage.prototype.setItem = () => { throw new Error("quota exceeded"); };
  try {
    save("Guest", "1111");                                    // the browser now refuses
    assert.equal(codes.querySelector("summary").textContent, "Codes (2)", "the new code shows, not the stale list");
  } finally { dom.window.Storage.prototype.setItem = original; }
});

// KEEP THIS ONE LAST: a browser that throws on every read AND write (a private window).
test("when the browser throws on every read and write, the panel still loads and codes still work", { skip }, async () => {
  const proto = dom.window.Storage.prototype;
  const [getItem, setItem] = [proto.getItem, proto.setItem];
  proto.getItem = () => { throw new Error("storage blocked"); };
  proto.setItem = () => { throw new Error("storage blocked"); };
  try {
    const devices = [{ group: "Bench", name: "Test — Private", key: "pv", entities: [ent("lock.t_priv", "Test — Private")] }];
    const p = await mount({ devices, states: { "lock.t_priv": { state: "locked", attributes: {} } } });
    const codes = p.tile("Test — Private").querySelector("details.codes");
    assert.equal(codes.querySelector("summary").textContent, "Codes (0)", "it drew without storage");
    const [name, code] = codes.querySelectorAll(".code input");
    name.value = "Dana"; code.value = "4821";
    [...codes.querySelectorAll("button")].find((b) => b.textContent === "Save a code").click();
    assert.equal(codes.querySelector("summary").textContent, "Codes (1)");
  } finally { proto.getItem = getItem; proto.setItem = setItem; }
});
