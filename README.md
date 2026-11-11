# Virtual Test Devices for Home Assistant

Make fake devices to try your Home Assistant automations against, and **clone your real
devices** so the stand-in reports the same abilities. A **Test Devices panel** in the
sidebar shows every test device with its live state and lets you drive it: flip a switch,
set a temperature, use a lock code, press a remote's button, and watch your automation
react.

It works entirely on its own, with nothing else to install. It can also **bring in other
people's devices**: someone sends you an export of their Home Assistant, you tick the
devices you want (all, some, or a mix from several people), and you have stand-ins to
reproduce what they see.

> [!IMPORTANT]
> This is a fork of [twrecked/hass-virtual](https://github.com/twrecked/hass-virtual)
> and **uses the same `virtual` domain**, so it installs to the same folder.
> Install this **or** hass-virtual, not both.

---

## Quick start

Needs **Home Assistant 2026.7 or newer.** Tested on 2026.10.4 and 2026.11.0.

1. **Install.** Add this repository to HACS as a custom repository (type: Integration),
   install it, and restart Home Assistant.
2. **Add a group.** Settings → Devices & services → Add integration → **Virtual Test
   Devices**. A group is one file of test devices; the defaults are fine.
3. **Open "Test Devices"** in the sidebar (administrators only). Use **Create** to make a
   device from a list of kinds, or **Clone a device** to copy one of yours.

> [!NOTE]
> **This adds a "Test Devices" entry to your sidebar by itself**, for administrators, as
> soon as you add a group. If you would rather not have it, either put this in
> `configuration.yaml` and restart (the add-on then adds no sidebar entry at all):
>
> ```yaml
> virtual:
>   panel: false
> ```
>
> or leave it and hide the entry in your profile's sidebar settings (that is per person,
> and does not remove the panel).

Everything the panel does is also an ordinary Home Assistant action, so
**Developer tools → Actions** works too (see [Actions](#actions)).

## The Test Devices panel

Four tabs.

**Devices.** Every test device you have, and only those, as a tile under its group.
Each part of a device shows **its state right now** in words and has a control that says
what it does: a lock reads *Locked | Unlocked*, a motion sensor *Clear | Detected*, a
cover *Closed | Open*. Tiles whose device is doing something have a coloured edge. The
state comes from Home Assistant itself, so a change made anywhere (an automation, a
dashboard, another panel) shows up without refreshing. You can search, filter by kind, fold
groups away, and remove a device (two clicks).

- **A lot of parts?** A device with many parts (a freezer reporting 30-odd values) shows
  its main six, with the rest one click away under *Show N more*, searchable. Click the
  star on any to pin it to the main list; pins are remembered in your browser.
- **Locks and codes.** Type a code on a lock's tile and press **Lock** or **Unlock** (or
  Enter): it is sent with Home Assistant's own `code` field and the lock records it, so an
  automation that reacts to a code being used can be tried. Nothing needs saving first.
  After a code that isn't already saved goes through, a line offers to save it (the name
  is optional); saved codes show in a menu next to the box and are kept **in your browser
  only**, never in the add-on. See [Locks and codes](#locks-and-codes).
- **Remotes and buttons.** A scene remote shows one button per press type (Press, Double
  press, Hold ...), and a button just presses.

**Create.** Pick a kind from a list grouped by category, give it a name (it always starts
with "Test —"), and it is made. The kinds are plain data in `templates.json`, which you can
edit. The **Phone** kind (a tracker plus a notifier) asks whether it receives **push or
text**; no other kind does.

**Clone a device.** A searchable list of your real devices, grouped by kind. *Clone* makes a
test copy that reports the same abilities. One switch, **Also give the copy a way to
receive a push or a text** (off by default), is for cloning a phone or anything an
automation sends a message to.

**Clone everything.** Export your whole Home Assistant to one file, so a test Home
Assistant can have a stand-in for every device. Run it on the real one; it only reads, and
writes one file in the configuration folder. Before it writes anything it **shows you every
name** that will be in the file and lets you change any of them (see
[Sharing an export](#sharing-an-export-and-bringing-one-in)).

The second half of the tab is **Bring devices in**: choose an export file, tick the devices
you want, and add them to a group. Do it again with another file to mix several.

**Good to know**

- The panel appears once the integration has at least one group (or `virtual:` is in
  `configuration.yaml`). A Home Assistant with neither has no panel yet.
- **Turn it off:** `virtual: {panel: false}` in `configuration.yaml` leaves the sidebar entry
  out. Everything else still works. You can also just hide the entry in Home Assistant's
  sidebar settings.
- Every command behind the panel needs an **administrator**, and so do the actions it
  uses ([see below](#what-changed-for-you)).
- The panel's script is an ordinary file served without a login. It contains nothing private.
- A test **vacuum cannot be sent to "docked"**: nothing it can do ends there, so the panel
  says so instead of doing the wrong thing.

## Try it without risking your home

You do not have to put this on your real Home Assistant to look at it. This starts a
throwaway Home Assistant in Docker, with Home Assistant's own **demo devices** to clone:

```bash
mkdir ha-try && cd ha-try
mkdir -p config/custom_components
cp -r /path/to/custom_components/virtual config/custom_components/virtual
printf 'default_config:\ndemo:\n' > config/configuration.yaml
docker run -d --name ha-try -p 8123:8123 -v "$PWD/config:/config" \
  ghcr.io/home-assistant/home-assistant:stable
```

Open `http://localhost:8123`, create the account, then follow the Quick start from step 2.
Stop and remove it with `docker rm -f ha-try`. (Adjust the folder path for your system.)

## What changed for you

Upgrading from an earlier version? These are the behaviour changes, all of them to stop
**silent** damage:

- **A change is refused instead of overwriting a file it could not read.** If a group's
  devices file is blank, has a typo, or is half-copied, adding or cloning a device now says
  so and leaves the file alone. Before, it added one device on top of "nothing" and replaced
  everything in it, then reported success. The same goes for a file that has gone missing
  from a group that already has devices.
- **A group with a missing or damaged file no longer deletes its devices.** A missing
  devices file (a mount that did not come up) is no longer read as "this group has none, so
  remove them all". A damaged identity file makes the group wait with a plain message
  instead of giving every entity a new identity.
- **A bad entry is refused before anything is written.** Before, one entry its platform
  would reject made every entity of that type in the group vanish at the next reload, while
  the action said it worked.
- **A name already in use is never silently replaced.** `create_device` with a taken name is
  an error; cloning the same device again takes the next free `Name (2)`.
- **Export only replaces its own files.** It will not overwrite `configuration.yaml`, a
  group's devices file, or anything it did not write.
- **The actions are administrator-only** when a person calls them (see [Actions](#actions)).
  Automations are not affected (they run without a user), nor are administrators; a script or
  button a non-admin runs acts as that person.
- **Locks record the code they were sent** (`last_code`) and count every action (`sequence`).
- **Needs Home Assistant 2026.7 or newer.** Home Assistant replaced the unit names the gas
  and particle sensors used (ppm, µg/m³) and renamed the thermostat's temperature unit,
  with removal dates in 2027. The add-on now uses the new names, so the warnings in the
  log are gone. The sensor names need 2026.7; the thermostat works with the old name or the
  new one, whichever your Home Assistant has. Nothing a device does has changed.
- **Export now shows you the names first.** The panel's export lists every device and entity
  name that will go in the file, marks the ones that may carry a person's name, and lets you
  change any of them before anything is written. Nothing is changed for you.
- **New:** *Bring devices in* on the Clone everything tab: choose an export file, tick all,
  some or none, and add them to a group. Several files can be mixed. Identical devices are
  not added twice; a clash gets a number.
- **New:** the Test Devices panel, the `virtual: {panel: false}` option, the `select` and
  `text` platforms, and the export tools.

---

## Actions

Everything is a normal Home Assistant action, so it all works from
**Developer tools → Actions** with no other software:

| action | what it does |
|---|---|
| `virtual.clone_device` | make a test copy of a real device, abilities included |
| `virtual.describe_device` | return that copy's specification without creating it |
| `virtual.create_device` | create a device from an explicit list of entities |
| `virtual.remove_device` | remove one |
| `virtual.export_devices` | write a file describing your devices, to load as stand-ins elsewhere |
| `virtual.set` | set a sensor's value |
| `virtual.set_available` | mark a device available or unavailable — the field is `value: true/false`, **not** `available:` |
| `virtual.fire_event` | fire a button / scene event |
| `virtual.turn_on` / `turn_off` / `toggle` / `move` | drive a device directly |

`create_device`, `remove_device`, `clone_device`, `describe_device` and `export_devices`
need an **administrator** when a person calls them (automations are not affected: they run without a user), because they rewrite a group's file (or,
for `describe_device`, return a real device's whole specification). If you need them open to
everyone, it is a one-line change; raise it as an issue.

## Settings

In `configuration.yaml` (all optional):

```yaml
virtual:
  panel: false        # no sidebar entry; the actions and devices still work
  export_only: true   # only the export action; nothing can be added (for a real home)
```

Per-platform options are documented in **[UPSTREAM_README.md](UPSTREAM_README.md)** —
upstream's documentation, kept because it is still accurate for everything it covers.

---

## Locks and codes

A test lock records the code it was last sent, as the attribute **`last_code`** (empty when
the last lock or unlock carried none), and counts every lock, unlock or open in
**`sequence`**. The count matters: using the same code on a lock that is already in that
state changes nothing else Home Assistant can see, so an automation waiting for it would
never run. With the count, **every use is announced**, even the same code twice. It works
for locks that report a code on lock, on unlock, or both. Send a code with Home Assistant's
own `lock.lock` / `lock.unlock` and its `code` field (the panel does this for you: type the
code, press Lock or Unlock). Every press is a send, so pressing twice is two uses, as a
real keypad would be.

**Use made-up test codes, never a real one.** The code is not hidden: it sits in the lock's
`last_code` attribute, so it appears in every `state_changed` event, in the trace of any
automation the lock triggers, in the state any logged-in user can read, and in the recorder's
history until it is purged (10 days by default; `recorder.purge_entities` removes a lock's
rows sooner). Each use is its own history row because `sequence` changes. A clone or an
export **still never copies a real lock's codes**.

Two things to know: a plain "this lock changed" trigger with no `to:` and no `attribute:`
also runs when the lock is used again in the state it is already in, which a real lock would
not announce, so use `to:` for that. And if a default code is set on the lock in Home
Assistant's entity options, Home Assistant supplies it on actions that carry none, so
`last_code` shows it. In a YAML file, quote a code (`"0042"`): unquoted, YAML reads it as a
number.

---

## What it adds over hass-virtual

**More device kinds.** Upstream covers binary_sensor, sensor, switch, light,
lock, fan, cover, valve, number and device_tracker. This fork adds
`alarm_control_panel`, `camera`, `climate`, `media_player`, `notify`,
`siren`, `humidifier`, `vacuum`, `button`, `event`, `select` and `text`.

**Devices that state their real abilities.** Every platform accepts Home
Assistant's `supported_features` plus the mode lists and limits that go with it,
instead of hardcoding one shape per domain. A virtual thermostat can be a
cool-only single-setpoint unit or a full heat/cool-range one with fan and preset
menus, because that is what you told it to be.

**Cloning a real device** (`virtual.clone_device`). Point it at a device you own
and it creates a test copy reporting the same abilities — mode lists, limits,
feature flags. The list of what gets copied comes from Home Assistant's own
definition of capability attributes, not from guesswork, so it keeps up as HA
adds them.

A real notifier does not say whether it stands for a **push** or a **text**, so
a copy would not either. Choose **Receives notifications as** when you clone to
label the copy's notifier one or the other, so an automation that sends a push or
a text finds it. A phone running the Home Assistant companion app gets a push
notifier automatically (its push is a service, not something that can be copied).
A UI built on this integration (such as the Test Devices panel) can also
ask for a notifier to be *added* to a device that has none; that is a setting for
UIs and is not offered on Home Assistant's Actions screen.

**Devices that say what they are.** In the devices file a device can be written
as `Name: {name, manufacturer, model, sw_version, area, entities: [...]}` as well
as the original `Name: [entities]`, so its device page reads like the real one,
and an entity can carry an `entity_id` of its own and keeps exactly that id.

**Describing a device without creating it** (`virtual.describe_device`) returns
that same specification as data — useful for putting "here is what my device
looks like" into a bug report so somebody else can rebuild it.

> [!NOTE]
> `describe_device` returns your **real device and entity names**. Nothing is
> sent anywhere — this integration makes no network requests of any kind, so the
> only way that leaves your system is if you paste it somewhere. Give it a read
> before putting it in a public issue. This integration does not change names for
> you; the export review (see [Standing in for another Home Assistant](#standing-in-for-another-home-assistant))
> lets you.

**A camera that hands over a real picture.** Home Assistant's own snapshot
action does the work — it asks the camera for an image and writes the file — so a
snapshot lands as a real file at a real path, under HA's normal rules about where
it may write. An automation asking for a snapshot somewhere HA won't write fails
here exactly as it would on real hardware. The picture changes every time it is
asked, so two snapshots look different and you can tell an automation fired twice
rather than once. The panel's camera tile has a **Take snapshot** button that saves
the picture into `/media`, one fixed file per camera named after its entity id
(a camera `camera.test_front` writes `/media/test_front.jpg`), replaced each time.
`/media` is where Home Assistant allows writes in a Docker or Home Assistant OS
install; on a plain Core/venv install it allows `<config>/media` instead, and the
button then shows Home Assistant's refusal. An automation can still snapshot anywhere
Home Assistant permits.

**A camera that also has a video.** The camera carries one short clip (22 seconds,
public domain, credited in `images/CREDITS.md`) and offers Home Assistant's live view
and recording. Be aware of what this is: it is a clip, not a live feed. Home Assistant
reads a video file as fast as it can, so `camera.record` produces the clip once
(about 22 seconds, 280 KB) whatever duration you ask for, and live view in the
dashboard plays the clip through and then stops — reload the card to start it again.
That is enough to exercise anything that asks a camera for a stream or a recording;
it does not behave like a camera that never stops. If the clip is removed, live view
is switched off rather than left as a button that fails.

**A notifier that records what was sent.** Home Assistant ships with almost
nowhere to send a notification — a dashboard pop-up, and that is all; everything
else arrives when you install a phone app, an SMS service or email. That makes
notification automations awkward to test. Send to a virtual notifier instead and
the message, the title and a running count appear on the entity, visible in
Developer tools → States or by clicking it on a dashboard. It also fires a
`virtual_notify_sent` event, so notifications can be watched arriving live in
Developer tools → Events. The count is the useful part: it shows an automation
firing twice when it should have fired once, which the message alone cannot.

**A select** (a setting with a fixed menu) and a **text** (a free-text setting) are
reproduced too, since real devices expose a lot of both.

### Standing in for another Home Assistant

`virtual.export_devices` (or the panel's **Clone everything** tab) writes one file describing
your devices and entities. Load that file as a group on a test Home Assistant and every
entity appears there under the **same entity id** with its real state as the starting
state, so an automation you copy across runs unchanged against stand-ins. The two Home
Assistants are connected by nothing but the file.

1. **On the real Home Assistant**, install this integration and add
   ```yaml
   virtual:
     export_only: true
   ```
   to `configuration.yaml`, then restart. In this mode the integration imports
   nothing and refuses to add new groups, so on a Home Assistant with no groups
   the only thing it provides is the export (no entities, nothing that can add test
   devices to your real home). A group that is already set up keeps running.
2. **Export**, from the panel's *Clone everything* tab or **Developer tools → Actions →
   "Export devices as stand-ins"**. It only reads, and writes `virtual_export.yaml` in your
   config folder (it will only replace a file an earlier export wrote, never one of your
   own). You can leave out devices, entities or whole integrations (for example devices a
   network integration names after MAC addresses).
3. **Bring the devices in.** Copy the file to wherever you run the test Home Assistant, open
   the panel's **Clone everything** tab, and under *Bring devices in* choose the file, tick
   what you want (or *Tick all*) and press **Bring in**. You can add them to a group you
   already have or to a new one made for them.
   (The older way still works: add a *Virtual Test Devices* group whose devices file is the
   exported file, and every device in it comes in.)
4. **To refresh**, export again and bring the file in again. Devices that are unchanged are
   not added twice. Devices you add by hand can live in the same group or another.

The file keeps your **real device and entity names and ids**. That is what makes a
stand-in a stand-in, so read it before sharing it anywhere. Lock and alarm codes
and text-field passwords are never copied, and this integration makes no network
requests of any kind. It copies **shape and starting state, not behaviour**: a
device that reaches your real Home Assistant through a bridge keeps the shape the
bridge gives it, and what it would look like if added natively is not something an
export can show.

### Sharing an export, and bringing one in

An export is a text file you can send to someone, for example a developer who wants to see
what your devices look like. They bring it into their own Home Assistant and have stand-ins
for your devices, under your entity ids, to try things against. They can bring in files from
**several people** and use all of it, some of it, or a mix.

**Before you send one: look at the names.** The file holds your real device and entity names
and ids, and a name can have a person in it (a phone called *Jane Smith's iPhone*, a person,
a tracker). Nothing can tell for certain which names are people, so nothing is changed for
you. When you press **Review the names, then export**, the panel:

- warns that the file will contain the real names;
- lists first the things that **may** carry a person's name (people, trackers, and a phone's
  notifier), then every other device under *All devices* with a search box;
- gives each one a box for its name and a box for its entity id, filled in with what is there.
  Change what you don't want shared; leave the rest.

An id carries the name too (`person.jane_smith`), so it has its own box. A different id means
an automation copied across no longer finds that entity, and the panel says so. **Names inside
a device's own settings are not shown and cannot be changed here**, so read the file before you
send it. The list of what was left out is written as counts only, never by name. A device that
is a single thing (a person, say) is filed under its entity id, and that follows the rename. (From Developer tools → Actions, `virtual.export_devices` takes the same changes as
`renames`: `{devices: {<device key>: "New name"}, entities: {<entity id>: {name, entity_id}}}`.)

**When you bring one in:**

- The file is read in your browser and sent to your Home Assistant. It is held in memory for
  half an hour and is **never saved**. Only administrators can do any of this.
- You see the file's devices with the same name and id boxes, so you can change names on the
  way in as well. People's names are marked the same way.
- **A device that is identical to one you already have is not added again**, whatever file it
  came in. Identical means the same name, the same ids and the same abilities; whether a lamp
  is on or off does not count. Such a device shows as *Already here* and cannot be ticked.
- **A device that only shares a name gets a number**: *Kitchen Light (2)*. An entity id that is
  already taken becomes `light.kitchen_2`. Nothing is ever replaced, and the panel tells you
  exactly what was renamed.
- Entity ids belong to the whole Home Assistant, so the comparison covers **every group**, not
  just the one you add to.
- If a group's devices file cannot be read, nothing is brought in until it is fixed, because
  its ids cannot be compared.

### What cloning will and will not do

It reproduces **shape, not behaviour**: what a device *says it can do*, not how
its own integration handles values. A capability or shape bug is reproducible on
a clone. A bug in how some bridge mangles a value on the way through is not, and
no amount of attribute copying will change that.

It also **never copies lock or alarm codes**. Bridged panels and locks expose
user code tables — sometimes plaintext PINs with the names attached — and sticking
to Home Assistant's capability attributes keeps all of it out. That matters if you
share a clone in a bug report, and it is guarded by a test: feeding the capture a
real bridged lock and alarm panel and asserting no code, name or PIN survives.

Nothing this integration produces ever leaves your Home Assistant on its own. It
makes **no network requests at all** — no telemetry, no analytics, no calls home.
Clones are written to a file in your own config folder and nowhere else.

---

## Your devices file is looked after

A group's devices live in one file, and several bugs once destroyed it **without a word**.
All were found and fixed here, each with a test that fails if the fix is undone:

- **Concurrent creates lost devices.** Fired together, every caller read before any caller
  wrote: six concurrent creates produced one device and reported success. Now serialised,
  with a burst collapsing to a single reload that still happens if the last call fails.
- **A failed save destroyed the file.** The savers truncated it first and serialised
  second, swallowing failures at debug level: one unrepresentable value wiped every device
  and left the integration unable to load. Now: serialise first, write via a temp file,
  replace atomically, log loudly.
- **A change could overwrite a file it could not read**, and **a missing or damaged file
  could delete a group's devices** ([see above](#what-changed-for-you)).
- **`lock.open` never worked.** It called a stub that always raised.

## Tests

`tests/` guards all of the above. See [tests/README.md](tests/README.md): the Python tests
run inside a Home Assistant container; the panel has its own tests that run with Node.

## Credit and licence

A fork of [twrecked/hass-virtual](https://github.com/twrecked/hass-virtual) by
**@twrecked**, whose work this is built on. GPL-3.0, unchanged — see
[LICENSE](LICENSE). Upstream copyright headers are intact.

The idea of **exporting a real Home Assistant as stand-ins**, and several of the
problems that come with it (entities keeping their real ids, devices carrying their
maker, model and area, the `select` and `text` platforms, an export-only mode, and
removing one entity without removing its device), came from
[DevLn](https://github.com/DevLn)'s fork of this project, on the
[`ha-test-sim` branch](https://github.com/DevLn/ha-virtual-test-devices/tree/ha-test-sim).
The code in this repository was written separately, but that fork found the traps
first, and this work would have been slower and riskier without it. Thank you.

Please report problems with **this fork** here rather than upstream.
