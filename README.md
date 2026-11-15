# Virtual Test Devices for Home Assistant

**Try your automations on fake devices first.** Make a pretend lock, thermostat, water
heater or motion sensor, flip it from a panel in your sidebar, and watch your automation
react, without touching anything real. You can also **copy your real devices** so the test
copy reports the same abilities, or **bring in a friend's devices** from a file they send you,
so you can see what they see.

It works on its own. There is nothing else to install and nothing leaves your Home Assistant.

> [!IMPORTANT]
> **This adds a "Test Devices" entry to your sidebar by itself**, for administrators only, as
> soon as you add your first group. Don't want it? Put this in `configuration.yaml` and restart:
>
> ```yaml
> virtual:
>   panel: false
> ```
>
> Everything else keeps working without the sidebar entry. (You can also just hide the entry in
> your own sidebar settings, but that only hides it for you.)

> [!NOTE]
> This is a fork of [twrecked/hass-virtual](https://github.com/twrecked/hass-virtual) and uses
> the same `virtual` domain, so install this **or** hass-virtual, not both.

## What you can do with it

- **Test an automation before it meets real hardware.** Trigger it from a fake door lock,
  motion sensor or leak sensor as often as you like.
- **Try the awkward cases.** Make a device go unavailable, report a strange state, or be
  used twice in a row.
- **Test devices you don't own.** Create a vacuum, a lawn mower or a water heater and see what
  your automation does with one.
- **Copy a real device** so the test copy has the same modes, limits and abilities.
- **Reproduce someone else's problem.** Bring their exported devices in (all, some, or a mix
  from several people) and try things against them.
- **Send yourself a notification that goes nowhere** and see exactly what would have been sent.

## What it can't do

It's a test bench, not a replacement for the real thing. Please know these before you start:

- **It copies a device's shape, not its behaviour.** A copy has the same modes, limits and
  abilities as the original, but not the quirks of the integration behind it. A bug in how some
  bridge mangles a value on the way through can't be reproduced.
- **It can't control real hardware.** Test devices are only pretend. They never talk to
  anything outside Home Assistant.
- **It never copies lock or alarm codes, or passwords.** Not in a clone, not in an export.
- **A camera is a short clip, not a live feed.** It hands over a real picture for snapshots and a
  22-second clip for live view and recording. Live view plays the clip once and stops.
- **A remote's commands go nowhere.** Send, learn and delete are recorded so you can see they
  arrived, but nothing is sent to a TV.
- **Some device kinds aren't covered yet:** weather, calendars, date and time, update, to-do
  lists, scenes, and the voice side of Assist (satellites, speech to text, text to speech).
- **A device with no unique id can't be cloned.** Some demo and YAML-defined entities have none.
- **Exports contain real names.** You can review and change every name before the file is
  written, but names hidden inside a device's own settings are not shown, so read the file before
  you send it.
- **Only administrators can use it.**

## Quick start

Needs **Home Assistant 2026.7 or newer.** Tested on 2026.10.4 and 2026.11.0.

1. **Install,** then restart Home Assistant.
   - **Home Assistant 2026.11 or newer** has HACS built in, as the **Marketplace**. Open
     **Settings → Marketplace**, choose **Add from link** (the button's wording may differ
     slightly), enter `jercoates/ha-virtual-test-devices`, and install it. Adding a custom repository needs a
     GitHub connection: Home Assistant shows a code to enter on GitHub, and never sees your
     GitHub password.
   - **Home Assistant 2026.7 to 2026.10:** install [HACS](https://hacs.xyz), add this repository
     as a custom repository (type: Integration), and install it.
2. **Add a group.** Settings → Devices & services → Add integration → **Virtual Test Devices**.
   A group is one file of test devices. The defaults are fine.
3. **Open "Test Devices"** in the sidebar. Use **Create** to make a device from a list, or
   **Clone a device** to copy one of yours.

The panel appears once you have at least one group (or `virtual:` is in `configuration.yaml`).

Everything the panel does is also an ordinary Home Assistant action, so
**Developer tools → Actions** works too (see [Actions](#actions)).

### Try it without risking your home

You don't have to put this on your real Home Assistant to look at it. This starts a throwaway
one in Docker, with Home Assistant's own demo devices to clone:

```bash
mkdir ha-try && cd ha-try
mkdir -p config/custom_components
cp -r /path/to/custom_components/virtual config/custom_components/virtual
printf 'default_config:\ndemo:\n' > config/configuration.yaml
docker run -d --name ha-try -p 8123:8123 -v "$PWD/config:/config" \
  ghcr.io/home-assistant/home-assistant:stable
```

Open `http://localhost:8123`, create the account, then follow the Quick start from step 2.
Remove it with `docker rm -f ha-try`. (Adjust the folder path for your system.)

## The Test Devices panel

Four tabs.

**Devices.** Every test device you have, as a tile under its group. Each part shows **its state
right now** in words and has a control that says what it does: a lock reads *Locked | Unlocked*, a
motion sensor *Clear | Detected*. A tile whose device is doing something has a coloured edge. The
state comes from Home Assistant itself, so a change made anywhere (an automation, a dashboard)
shows up without refreshing. You can search, filter by kind, fold groups away, and remove a
device (two clicks).

- **A lot of parts?** A device with many parts (a freezer reporting 30-odd values) shows its main
  six, with the rest one click away. Star any part to pin it to the main list. Pins are kept in
  your browser.
- **Locks and codes.** Type a code on a lock's tile and press **Lock** or **Unlock**. See
  [Locks and codes](#locks-and-codes).

**Create.** Pick a kind from the list, give it a name (it always starts with "Test —"), and it is
made. The kinds are plain data in `templates.json`, which you can edit. The **Phone** kind asks
whether it receives **push or text**.

**Clone a device.** A searchable list of your real devices. *Clone* makes a test copy with the same
abilities. One switch, **Also give the copy a way to receive a push or a text** (off by default),
is for cloning a phone or anything an automation sends a message to.

**Clone everything.** Export your whole Home Assistant to one file, or bring devices in from a
file someone sent you. See [Sharing devices](#sharing-devices-and-bringing-them-in).

## What kinds of device it makes

26 kinds. Here is what you can do with a test one:

| Kind | What you can do |
|---|---|
| Light, switch, fan, siren | Turn on and off |
| Lock | Lock and unlock, with a code |
| Cover, valve | Open and close |
| Binary sensor (motion, door, leak, smoke ...) | Flip between clear and detected |
| Sensor, number, text, select | Set the value |
| Thermostat (climate) | Set the mode, the target and the current temperature |
| Humidifier | Turn on and off, set the target |
| **Water heater** | Set the mode, the target, away mode, and the current temperature |
| Vacuum | Start, stop, pause, send home |
| **Lawn mower** | Start, pause, dock, stop, or put it in any state, including `error` |
| Alarm panel | Arm, disarm, trigger |
| Media player | Play, pause, stop, volume |
| Camera | Take a snapshot; short video clip |
| Button, scene remote (event) | Press, or fire a press type |
| **Air quality sensor** | Set each reading it carries |
| **Universal remote** | Turn on and off, pick an activity; its commands are recorded |
| Notifier | Records every message sent to it |
| Device tracker | Move it to a place |

**Bold** kinds are new in 0.17.0.

A few notes:

- **Air quality** can't be commanded in Home Assistant, so you set its readings from the panel or
  with `virtual.set_air_quality`. A copy only carries the readings the original reported.
- **Water heater** uses Home Assistant's own actions. Set its current temperature with
  `virtual.set_current_temperature`.
- **Lawn mower:** no action leads to `error` or `returning`, so `virtual.set_lawn_mower_activity`
  puts it in any state.
- **Remote:** each send, learn and delete is recorded (`last_action`, `last_command`,
  `last_device`, and a `sequence` that counts every call), so an automation watching the remote
  runs every time.
- **Notifier:** the message, title and a running count appear on the entity, and a
  `virtual_notify_sent` event fires. The count shows an automation firing twice when it should
  have fired once.
- **Camera:** Home Assistant's own snapshot action writes a real file. The panel's **Take
  snapshot** button saves it into `/media`, one file per camera, replaced each time (a camera
  `camera.test_front` writes `/media/test_front.jpg`). On a plain Core install, `/media` may not
  be allowed, and the button shows Home Assistant's refusal.
- **Vacuum:** a test vacuum can't be sent to "docked", because nothing it can do ends there, and
  the panel says so.

## Copying a real device

`virtual.clone_device`, or the panel's **Clone a device** tab. The copy reports the same abilities:
mode lists, limits and feature flags. What gets copied comes from Home Assistant's own definition
of capabilities, so it keeps up as Home Assistant adds them.

A real notifier doesn't say whether it stands for a push or a text, so choose **Receives
notifications as** when you clone, and an automation that sends a push or a text will find it. A
phone running the companion app gets a push notifier automatically.

`virtual.describe_device` returns the same specification as data, so you can paste "here is what my
device looks like" into a bug report. It contains your **real device and entity names**, so read it
before posting it publicly.

## Sharing devices, and bringing them in

`virtual.export_devices`, or the panel's **Clone everything** tab, writes one file describing your
devices. Load it on a test Home Assistant and every device appears with the **same entity id** and
its real state as the starting state, so an automation you copy across runs unchanged.

**To export**, on the Home Assistant whose devices you want to copy:

1. Optionally add `virtual: {export_only: true}` to `configuration.yaml` and restart. In this
   mode nothing can be added, so it is safe on a real home.
2. Open **Clone everything** and press **Review the names, then export**.
3. It writes `virtual_export.yaml` in your configuration folder. It only reads, and it only
   replaces a file an earlier export wrote.

**Before you send an export, look at the names.** The file holds your real device and entity names
and ids, and a name can have a person in it (a phone called *Jane Smith's iPhone*). Nothing can
tell for certain which names are people, so nothing is changed for you. The review screen:

- warns that the file will contain real names;
- lists first the things that **may** carry a person's name (people, trackers, a phone's notifier),
  then every other device, with a search box;
- gives each a box for its name and one for its entity id. Change what you don't want shared.

**Names inside a device's own settings are not shown and can't be changed here**, so read the file
before you send it. The list of what was left out is written as counts only, never by name.

**To bring devices in,** open **Clone everything**, choose the file under *Bring devices in*, tick
the ones you want (or *Tick all*), and press **Bring in**. You can add them to a group you already
have or a new one.

- You can change names on the way in, the same way as on export.
- **A device identical to one you already have is not added again.** Identical means the same name,
  ids and abilities. Whether a lamp is on or off doesn't count.
- **A device that only shares a name gets a number:** *Kitchen Light (2)*. A taken entity id
  becomes `light.kitchen_2`. Nothing is ever replaced.
- Bring in several files to mix devices from several people.
- The file is read in your browser, held in memory for half an hour and **never saved**.

## Privacy and safety

- **No network.** This add-on makes no network requests at all: no telemetry, no analytics, no
  calls home. A clone or export is a file in your own configuration folder.
- **Codes and passwords are never copied.** Bridged locks and alarm panels can expose code tables,
  sometimes with names and PINs. The clone only copies Home Assistant's capability attributes,
  which keeps all of that out, and a test guards it.
- **Administrators only.** Every command behind the panel needs an administrator, and so do the
  actions that change a group's file (see [Actions](#actions)). The panel's own script is an
  ordinary file served without a login, and it contains nothing private.
- **Your devices file is protected.** A change is refused rather than overwriting a file it
  couldn't read, a bad entry is checked before anything is written, and a name already in use is
  never silently replaced. See [Your devices file is looked after](#your-devices-file-is-looked-after).

## Locks and codes

A test lock records the code it was last sent as the attribute **`last_code`** (empty when the
last lock or unlock carried none), and counts every use in **`sequence`**. The count matters:
using the same code on a lock that is already in that state changes nothing else Home Assistant
can see, so an automation waiting for it would never run. With the count, **every use is
announced**, even the same code twice.

Send a code with Home Assistant's own `lock.lock` or `lock.unlock` and its `code` field. The panel
does this for you: type the code, press Lock or Unlock. Saved codes are kept **in your browser
only**, never in the add-on.

**Use made-up test codes, never a real one.** The code is not hidden: it appears in the lock's
`last_code`, in every state change, in automation traces, and in the recorder's history until it
is purged (10 days by default). A clone or an export never copies a real lock's codes.

Two things to know: a plain "this lock changed" trigger with no `to:` also runs when the lock is
used again in the state it is already in, which a real lock would not announce, so use `to:`. And
if a default code is set in Home Assistant's entity options for the lock, Home Assistant supplies
it on actions that carry none, so `last_code` shows it. In a YAML file, quote a code (`"0042"`):
unquoted, YAML reads it as a number.

## Actions

Everything is a normal Home Assistant action, so it all works from
**Developer tools → Actions**:

| action | what it does |
|---|---|
| `virtual.clone_device` | make a test copy of a real device, abilities included |
| `virtual.describe_device` | return that copy's specification without creating it |
| `virtual.create_device` | create a device from a list of entities |
| `virtual.remove_device` | remove one |
| `virtual.export_devices` | write a file describing your devices |
| `virtual.set` | set a sensor's value |
| `virtual.set_available` | mark a device available or unavailable (the field is `value: true/false`, **not** `available:`) |
| `virtual.set_current_temperature` | set the current temperature a thermostat or water heater reports |
| `virtual.set_air_quality` | set the readings of an air quality sensor |
| `virtual.set_lawn_mower_activity` | put a lawn mower in any state |
| `virtual.fire_event` | fire a button or scene event |
| `virtual.turn_on` / `turn_off` / `toggle` / `move` | drive a device directly |

`create_device`, `remove_device`, `clone_device`, `describe_device` and `export_devices` need an
**administrator** when a person calls them, because they rewrite a group's file (or, for
`describe_device`, return a real device's whole specification). Automations aren't affected: they
run without a user.

## Settings

In `configuration.yaml`, all optional:

```yaml
virtual:
  panel: false        # no sidebar entry; the actions and devices still work
  export_only: true   # only the export action; nothing can be added (for a real home)
```

Per-platform options are in **[UPSTREAM_README.md](UPSTREAM_README.md)**, upstream's documentation,
kept because it is still accurate for everything it covers.

A device in the devices file can also be written as
`Name: {name, manufacturer, model, sw_version, area, entities: [...]}`, so its device page reads like
the real one, and an entity can carry an `entity_id` of its own and keeps exactly that id.

## Your devices file is looked after

A group's devices live in one file, and several bugs once destroyed it without a word. All were
found and fixed here, each with a test that fails if the fix is undone:

- **Concurrent creates lost devices.** Six created at once produced one and reported success. They
  are now queued, with a burst collapsing into a single reload.
- **A failed save destroyed the file.** One value that couldn't be saved wiped every device. Now the
  file is prepared first, written via a temporary file, and replaced in one step.
- **A change could overwrite a file it couldn't read**, and **a missing or damaged file could delete
  a group's devices.** Now the change is refused and the group waits with a plain message.
- **`lock.open` never worked.** It called a stub that always raised.

<details>
<summary><b>Upgrading from an earlier version?</b></summary>

- **A change is refused instead of overwriting a file it could not read.**
- **A group with a missing or damaged file no longer deletes its devices.**
- **A bad entry is refused before anything is written.**
- **A name already in use is never silently replaced.** `create_device` with a taken name is an
  error; cloning the same device again takes the next free `Name (2)`.
- **Export only replaces its own files.** Never `configuration.yaml` or a group's devices file.
- **The actions are administrator-only** when a person calls them.
- **Locks record the code they were sent** (`last_code`) and count every action (`sequence`).
- **Needs Home Assistant 2026.7 or newer.** Home Assistant replaced the unit names the gas and
  particle sensors used and renamed the thermostat's temperature unit. The add-on uses the new
  names, so the warnings in the log are gone. Nothing a device does has changed.
- **0.16.0:** *Bring devices in*, the export name review, and the sidebar panel's import screen.
- **0.17.0:** air quality, water heater, lawn mower and remote devices, and two more Home Assistant
  2026.11 deprecation warnings fixed.

</details>

## What would make this more useful?

If something is missing, confusing or broken, or you have a device kind you wish it could make,
**please [open an issue](https://github.com/jercoates/ha-virtual-test-devices/issues)**. It helps
to know what people actually use it for. Report problems with this fork here rather than upstream.

## Tests

`tests/` guards all of the above. See [tests/README.md](tests/README.md): the Python tests run
inside a Home Assistant container, and the panel has its own tests that run with Node.

## Credit and licence

A fork of [twrecked/hass-virtual](https://github.com/twrecked/hass-virtual) by **@twrecked**, whose
work this is built on. GPL-3.0, unchanged, see [LICENSE](LICENSE). Upstream copyright headers are
intact.

The idea of **exporting a real Home Assistant as stand-ins**, and several of the problems that come
with it (entities keeping their real ids, devices carrying their maker, model and area, the `select`
and `text` platforms, an export-only mode, and removing one entity without removing its device),
came from [DevLn](https://github.com/DevLn)'s fork of this project, on the
[`ha-test-sim` branch](https://github.com/DevLn/ha-virtual-test-devices/tree/ha-test-sim). The code
in this repository was written separately, but that fork found the traps first, and this work would
have been slower and riskier without it. Thank you.
