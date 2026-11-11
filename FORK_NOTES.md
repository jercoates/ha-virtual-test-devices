# PistonCore Test Devices — fork provenance

This folder is a **fork of [`twrecked/hass-virtual`](https://github.com/twrecked/hass-virtual)**
(GPL-3.0), the base for PistonCore's **test devices** feature. See
`../VIRTUAL_DEVICES_SPEC.md` for the why and the plan.

## Upstream snapshot

- **Source:** https://github.com/twrecked/hass-virtual
- **Forked at commit:** `a056ceaf73d4907e258ae055c3541342a3275400` (2026-03-06)
- **Upstream version:** 0.9.4 — domain `virtual`, `config_flow: true`, `iot_class: local_push`
- **License:** GPL-3.0 (unchanged; matches PistonCore). Upstream copyright headers kept.
- Vendored: `LICENSE`, `README.md`, `info.md`, `hacs.json`, `custom_components/virtual/`.
  (Skipped upstream `images/`, `install/`, `changelog/` — not needed to run.)

## What upstream already gives us (verified from source, 2026-07-21)

- **10 platforms:** binary_sensor, sensor, switch, light, lock, fan, cover, valve,
  number, device_tracker.
- **Grouped multi-entity devices** (a device with several entities under one
  device-registry entry — the shape PistonCore's picker needs).
- **GUI config flow** (`config_flow.py`) — the standalone create/remove surface
  (VIRTUAL_DEVICES_SPEC §5.6: standalone self-sufficiency).
- **Set-state services:** `virtual.turn_on / turn_off / toggle / set / set_available / move`.

## What PistonCore adds on this fork (see VIRTUAL_DEVICES_SPEC §5.2)

- **Missing platforms** the compiler targets: `alarm_control_panel`, `climate`,
  `media_player`, `siren`, `humidifier`, `vacuum`, `button` (camera only if a corpus
  piston needs it).
- **Live create/remove an outside app can trigger** (PistonCore drives it without
  hand-YAML), routed through HA-native config-flow/services so standalone users get it too.
- **`virtual.clone_device` — cloning lives HERE, not in the caller (2026-07-31).**
  New `clone.py`. Reads a real device and creates a test copy reporting the same
  abilities. It belongs in this repo because the platforms validate against CLOSED
  schemas: the capture list and those schemas are one contract, and splitting them
  across two projects guarantees drift. PistonCore now only names a device. The
  service takes a `device` selector, so HA's own Actions screen gives standalone
  users a searchable picker with no frontend to maintain.
- **Entity names within a group must be unique (2026-07-31).** Identity is keyed by
  entity NAME within the group, so two devices with an identically-named entity
  re-register on every restart — one device cloned twice grew the entity registry
  by five entities per boot, forever, silently. `clone.py` therefore names entities
  `<device name> <capability>`.
- **Two data-loss bugs fixed in `cfg.py` (2026-07-31) — these are upstream, and
  they destroyed every test device on the bench before being found.**
  `_async_save_yaml`/`_async_save_json` opened the real file in `'w'` (which
  TRUNCATES IT TO ZERO) and only *then* serialized. Anything yaml couldn't
  represent therefore wiped the file, and the exception was swallowed at DEBUG
  level so nothing reported it. The integration then refused to load at all,
  because the loader called `.get` on the `None` an empty file parses to.
  Now: serialize first, write to a temp file and `os.replace` it into place, log
  failures at ERROR and re-raise; and the loader (`_async_read_user_file`)
  degrades to "no devices" rather than taking the integration down. Worth
  carrying upstream.
- **A change is never written over a file that could not be read.** That
  same degrade-to-"no devices" made `create_device`/`clone_device` hazardous: with
  the file blank, mid-copy or holding a typo, they added one device to nothing and
  saved, replacing every existing device and reporting success. The loader already
  said whether the file was believable; the writer ignored it. It now refuses, with
  the file untouched. The same distrust now covers: a devices file that has gone
  MISSING from a group that already has devices (a mount that did not come up reads
  exactly like a new group, and "lists nothing" removed every row); and a DAMAGED
  identity (meta) file, which used to read as empty, so every entity got a fresh
  unique id, the old rows were removed as orphans and the bad file was overwritten.
  The group now waits (`ConfigEntryNotReady`) with the reason, instead.
  The reload after a burst of changes also happens when ANY call changed the file,
  even if the last one failed or was cancelled; a call cancelled while waiting for
  the lock used to leave the waiting count above zero for good, so the group never
  reloaded again until Home Assistant restarted.
- **Nothing is replaced or loaded blind.** `create_device` and `clone_device` check
  every entry against the platform's own schema BEFORE writing (the platforms
  validate inside their setup loop, so one bad entry used to make every entity of
  its type vanish at the next reload, with the call reporting success). A device
  name already in the file is no longer replaced in silence: a name the caller
  chose is an error, and a default clone name takes the next free `Name (2)`.
  `export_devices` only replaces a file an earlier export wrote (they all start with
  the same first line), never a group's own devices file, and one export runs at a
  time; before, `file:` could point at `configuration.yaml`.
- **Concurrency: `create_device`/`remove_device` were racing.** Both did
  read-modify-write on one yaml file then reloaded the config entry. Fired
  concurrently, every caller loaded before any caller saved, so all but the last
  were silently erased — six concurrent creates produced one device and no error.
  `pistoncore_manage._mutate_and_reload` now serializes the file edit per entry
  and coalesces a burst into a single reload (measured: 8 concurrent creates cost
  the same one reload as 1).
- **Full-fidelity cloning (2026-07-31, VIRTUAL_DEVICES_SPEC §5.7a).** Every
  platform now accepts the abilities a real device advertises — `supported_features`
  verbatim, plus its mode menus and limits — instead of hardcoding one shape per
  domain. Shared helpers live in `entity.py` (`FEATURES_SCHEMA`, `feature_flags`,
  `optional_list`); each platform names its own list/range keys. **Every key is
  optional and falls back to the platform's previous hardcoded default**, so
  upstream behaviour and existing `virtual.yaml` files are unchanged.
  Touches upstream files (light, fan, cover, lock, sensor, number) as well as the
  PistonCore-added ones — keep that in mind on an upstream rebase; the changes are
  confined to the schema block and `__init__`, plus new `async_*` handlers.
  Two upstream bugs fixed in passing: `lock.open` called a sync stub and always
  raised, and cloning any device containing a `number` entity could never succeed
  because that platform requires min/max.

## Device tracker: migrated off `location_name` (2026-08-02)

HA deprecated `TrackerEntity.location_name` (removal 2027.7). Migrated NOW rather
than at the deadline, because the integration had been public for one day and
nobody depended on the old behaviour — waiting would only have meant doing it
when the person who understood it might be gone.

**This is a deliberate behaviour change, not a rename.** `location_name` returned
free text that HA used as the state verbatim, so a virtual tracker could report
`school` with no such zone anywhere. The replacement, `in_zones`, takes zone
entity_ids and HA discards zones that do not exist — so the state can now only be
`home`, `not_home`, or the name of a real zone.

Taken on purpose: a REAL device tracker can only report those things, so a
virtual one inventing states your actual devices can never produce is a worse
bench. A location naming no existing zone now reports `not_home` **and logs a
warning saying so** — silently reporting the wrong thing is what a test bench
must never do.

VERIFIED on 2026.8.0b3: `home` -> `home`, capitalisation handled, unknown zone ->
`not_home` + warning, `not_home` explicit, GPS outside a zone -> `not_home` with
coordinates intact, GPS inside the home zone -> `home`, and the state survives a
restart. Upstream had not migrated this as of 2026-08-02.

## Cloning a device so it can receive a push or a text (2026-10-26, 0.14.0)

A real notifier carries no label saying whether it stands for a push or a text,
so a clone used to come back "generic" and a piston's "send a push" / "send a
text" — which finds its destination by that label — had nothing to land on.

**`virtual.clone_device` takes `notify_as`: `app` (push) or `sms` (text).** It
labels the notifier(s) the source device already has. That is the whole of what
the standalone Actions screen offers.

**Adding a notifier to a device that has none is a UI decision, not an Actions
screen feature.** It is behind `add_notifier: true`, which is accepted by the
schema but deliberately NOT listed in `services.yaml`, so Home Assistant's own
Actions screen never offers it. The reason is bridge-specific: a phone that
arrives through Hubitat looks like a handful of sensors, so no rule inside this
integration can tell it should have a notifier. A UI knows more (PistonCore's Test
Devices page shows a "Notifies as" choice and passes both settings; a future UI
for this add-on would decide when to offer it the same way). This is a
convenience, not a lock: anyone with a Home Assistant token can pass the setting.
`describe_device` accepts the same two, so a preview matches its clone.

**One automatic case, kept on purpose:** a device owned by the `mobile_app`
integration (the companion app) always gets a push notifier, because its push is
a notify SERVICE rather than an entity, so there is nothing to copy. That is
decided by which integration owns the device — a fact, not a guess — and
`notify_as: sms` overrides it.

- An ordinary device with no choice gets nothing, and a device with no notifier
  that is given `notify_as` alone also gets nothing (logged), so the label can
  never silently create entities. Both are tested as controls.
- The added notifier's name goes through the same de-duplicator as every other
  entity, so a source entity already called "Notification" is not duplicated.
- `notify_as` labels EVERY notifier the source has; a device with several real
  notifiers gets them all the same label. Choosing "push" says the device
  notifies as push, so this follows from the choice.
- An unknown or missing device is a plain `ServiceValidationError` (a polite
  refusal) rather than a server error.
- Not done: the legacy `notify.mobile_app_<phone>` SERVICE is not recreated. A
  piston that calls that service directly still cannot reach a clone; the push /
  text path through notify entities (what PistonCore's vocab sends) does.

## Standing in for another Home Assistant (2026-10-26, 0.14.0)

THE IDEA AND ITS HARD PROBLEMS CAME FROM `DevLn/ha-virtual-test-devices` (branch
`ha-test-sim`), a fork of this repo. Nothing was copied: this was written fresh
around this fork's own rules, but its notes are the reason several traps below were
known in advance. It is worth reading beside this.

**The use case (Jeremy):** clone the real, main Home Assistant out, so a test bench
holds stand-ins for exactly what it WILL run, add things by hand to the test side to
delete later, and see how the devices come up as if the main Home Assistant were the
controlling hub. Bridges (a Hubitat hub, say) behave differently from native
integrations, so the bench needs the real shapes without adopting anything native.

**`virtual.export_devices`** (`export.py`) writes a devices file from the live
registries: every reproducible entity under its REAL entity id, with its real name,
its capture from `clone.entity_spec` (the SAME routine `clone_device` uses, so the
two cannot disagree about what a copy carries), its entity category, and its state
as the starting state (unavailable becomes `initial_availability: false`; unknown
gives nothing; button, camera, event and notify give nothing; a light also keeps
brightness, colour and effect, but not colour temperature, which the light platform
reads as kelvin but validates as a byte). Devices carry name, maker, model, version
and area. Every entry is validated against the target platform's OWN closed schema
before it is written; a rejected entry goes to the report, never the file, so the
file always loads. Skips are accounted for: each individual decision, and one line
per non-reproducible domain (a real Home Assistant has hundreds of automations).
Defaults leave out hassio, backup, sun, hacs and virtual, because a test Home
Assistant has its own and exporting them only makes `_2` copies (ASSUMED reasoning,
not measured on every setup). It writes atomically, to the config folder or an
`allowlist_external_dirs` path only: Home Assistant's own `is_allowed_path` does not
cover the config folder itself, so checking it alone refuses the default file.

**Real names and ids are kept on purpose, with no warnings or switches in this
integration** (Jeremy: PistonCore builds its own reports and owns data safety; this
is the standalone side). It makes no network requests. Lock and alarm codes and
text-field passwords are never copied, and that is tested. PistonCore does NOT call
this action and is not linked to it: nothing in `shim/` references it. The add-on
cannot enforce that against a caller with a Home Assistant token, so it is a
convention kept by PistonCore, not a lock.

**`virtual: {export_only: true}`** in `configuration.yaml` stops the integration
creating or importing anything of its own: no YAML import, no new group (the config
flow aborts). On a Home Assistant with no groups that leaves the export action as the
ONLY thing it provides. A group that is ALREADY set up keeps running: an earlier
version made existing groups fail with a setup error, which punished the very home
that had one. The action is registered in `async_setup`, not per group, because a
Home Assistant that only exports has no group to hang it on.
Its platform schemas are loaded in the executor only when an export is run: importing
the platform modules at startup woke Home Assistant's own camera code on the event
loop (found on a real run, as "blocking call" warnings).

**What the loader gained, which is the risky half:**
- An entry may name its own `entity_id` and then keeps exactly that. Its `unique_id`
  is DERIVED from the id (`<entity_id>.virtual`), never random, so a regenerated
  file maps onto the same registry rows. Such entries need no meta row. A wrong
  domain or a repeated id is logged at ERROR and skipped, the first keeps a contested
  id, capitals are lowered with a warning. If Home Assistant gives a stand-in a
  different id, that is logged as a WARNING (something already has the id, or it
  was renamed in the UI), but only for entities whose id came from the file: an
  ordinary entity renamed in the UI must not be reported on every restart.
- A device may be a mapping with `name`, `manufacturer`, `model`, `sw_version`,
  `area` and `entities`. The shorthand list still works. `area` only applies when
  the device is first created (Home Assistant's rule for a suggested area). MAC
  address and configuration URL are deliberately NOT exported: a shared MAC can merge
  a stand-in into a real device, and a URL can be a local address.
- `entity_category` on every platform, so a stand-in sits in the same section.
- The entity passes ONLY `identifiers` to the device registry now. It used to repeat
  maker and model, which would write the constants back over the file's values.
- **Orphan removal was rewritten.** It used to delete the orphan's whole DEVICE,
  taking its surviving entities with it and recreating the device under a new id.
  Now the file is the source of truth: an entity row whose unique id the file no
  longer lists is removed one at a time, and a device goes only when the file no
  longer lists it. This also clears a stand-in dropped from a re-exported file.
  **It only acts on a file it can believe.** A file that is blank, does not parse or
  is not a mapping reads as "lists nothing", and a copy still being written looks
  exactly like that; and a regenerated file with a typo has an entry rejected. Acting
  on either would delete real registry rows (history, area) for entities that were
  never meant to go, so cleanup is skipped, with a warning, until the file is fixed
  (`BlendedCfg.trusted`). A file that says `devices: {}` IS believed, so removing the
  last device still cleans up. Verified live: a blanked file kept all rows and they
  came back under the same ids; a typo kept its row until fixed.
- `__version__` is read from `manifest.json` (it had drifted to 0.9.4), so there is
  one place to change the version.

**`select` and `text` platforms** (`select.py`, `text.py`). HA's TextEntity raises
when its value breaks its own limits, so a starting or restored value that does not
fit becomes "no value" with a warning; a select value off its menu falls back to the
first option; a `password` text keeps no value at all.

**Hand-made devices go in a DIFFERENT group** from an imported file, so a re-import
only replaces the imported group.

**Measured (2026-10-26, Home Assistant 2026.10.4, two throwaway instances):** the
demo integration's 123 entities exported as 82 entities in 78 devices (the rest are domains
that cannot be reproduced, plus the default exclusions) and all 82 loaded on a second
Home Assistant with the same ids and names. States matched except where the source
moved on after the export (the demo's energy sensors), a password text (by design) and
cameras (the virtual camera is idle where the demo's is streaming). Three restarts
changed nothing (82 rows, none unavailable). A re-imported file that dropped a device
and an entity, renamed one, and added broken entries removed exactly what was
dropped, kept a dropped entity's siblings and device, skipped the broken entries with
a clear message each, and left a separate hand-made group alone.

**Known fidelity limits found while doing this (existing platform behaviour, not new,
and not fixed here):** a valve always advertises open, close, stop and set-position
whatever the original did; a media player deliberately masks browse and search; a
virtual camera's "stream" is a 22 s clip (see below), not a live feed.

**Camera video (2026-11-02, verified in a throwaway HA 2026.10.4):** the camera
advertises STREAM only while `video/camera_clip.mp4` exists, and `stream_source()` hands
HA that file. Checked live: HA serves HLS segments for it and `camera.record` writes a
22 s, 277 KB file. HA's stream worker has no real-time pacing for a *file* source, so it
is consumed at full speed: live view plays the clip once and the stream then ends (HLS
returns 404 about a minute in; a new request restarts it). **Tried and rejected:** a
playlist repeating the clip 200 times to make a long feed — it read cleanly (65,800
packets, no timestamp jumps) but made a 10 s `camera.record` write 46 MB, so a real
loop needs a paced source (an ffmpeg process feeding a local stream), which is not built.
The clip is the FBI Honolulu security-camera recording of the 2009 Pago Pago parking-lot
tsunami (public domain, Wikimedia Commons), re-encoded to H.264 MP4, no audio.

## The sidebar panel (`panel.py`, `frontend/virtual-panel.js`, `templates.json`)

A standalone UI, so the add-on is usable with no PistonCore at all. Design:

- **Registered once per Home Assistant, from `async_setup`**, before the
  `export_only` return (an exporting home is where its export screen is wanted).
  Never per group: a second registration of the same panel path or static path
  raises. Registered only when Home Assistant calls `async_setup`, which for a
  config-flow integration means at least one group exists or `virtual:` is in
  `configuration.yaml`. A brand-new install with neither has no panel. VERIFIED.
- **Admin-only commands**, no raw configs: `virtual/groups`, `virtual/devices`,
  `virtual/templates`, `virtual/clonable`. They return names, states and
  structure only; a group's entity configs can hold lock and alarm codes and text
  defaults and are never returned. A non-admin gets `unauthorized` and does not see
  the panel (VERIFIED, 2026.10.4 and 2026.8.0b3). The script itself is a static
  file and is served without a login (VERIFIED) — it holds nothing private.
- **State is Home Assistant's, not ours.** The panel reads `hass.states`, so
  nothing is polled and a change from anywhere shows. Structure (which devices)
  comes from `virtual/devices`, refreshed on registry events.
- **Every control calls an ordinary action** (`light.turn_on`, `number.set_value`,
  ...). `controlsFor`/`callFor` in the JS are the whole mapping and are exported so
  they can be tested without a browser. A control is hidden when the entity's own
  `supported_features` says it cannot do it (a thermostat with no target
  temperature, a speaker with no volume).
- **`templates.json` is data**, the catalog of device kinds to create. It is checked
  against every platform's own schema by `tests/test_panel.py`, and must offer every
  platform. PistonCore's page has its own copy of a similar catalog until it reads
  this one.
- **The actions are admin-only too.** `create_device`, `remove_device`,
  `clone_device`, `describe_device` and `export_devices` are registered with
  Home Assistant's admin-service helper. They rewrite a group's file, or (describe)
  return a real device's whole capability spec, and before this a non-admin user
  could call any of them over the websocket. VERIFIED live: a non-admin is refused
  with "Unauthorized" and nothing changes; the admin still can; PistonCore (an
  admin's token) and automations (no user; VERIFIED live: an automation started by a non-admin's action still ran the service) are unaffected, while a script a non-admin runs acts as that person. This is a behaviour
  change for anyone who let a non-admin call them.
- **A panel failure never stops the test devices loading.** Registration is wrapped
  in `async_setup`; a failure is logged and the integration carries on.
- **The list is only redrawn when it changed**, so a half-typed value, a "Remove
  it?" waiting for its second click and a status message survive the registry events
  Home Assistant sends for changes that are not ours.
- **A lock records the code it was sent (`last_code`) and counts every action
  (`sequence`).** So an automation that reacts to a code being used can be tested
  without a keypad, for locks that report a code on lock, on unlock, or both. The
  count matters: using the same code on a lock already in that state changes nothing
  else Home Assistant can see, so an automation waiting for it would never run.
  VERIFIED live with three real automations (a state trigger on "unlocked", one on
  `last_code` changing, one on `sequence`): a first use ran all three; the same code
  again ran only the `sequence` one; a lock with no code ran the code-changed and
  sequence ones; a different code ran all three. The code is whatever the caller sends
  and sits in `last_code`, so it is also in every `state_changed` event, in the trace of
  any automation the lock triggers, in states any logged-in user can read, and in the
  recorder until purged (10 days by default); each use is its own history row because
  `sequence` changes. It must be a made-up test code. Trade-off: a bare state trigger
  (no `to:`, no `attribute:`) now also fires on a repeat use a real lock would not
  announce. A default code set in Home Assistant's entity options is supplied by Home
  Assistant on code-less actions and so shows as `last_code`. (Found by a review agent.) A real lock's codes are still never copied by a clone or export (`last_code` is
  not in the capture list; `test_capability_capture.py` pins that). The page keeps the
  saved names and codes in the browser, never in the add-on. **Sending (2026-11-04):** the
  tile has a code box with Lock/Unlock that sends at once (Jeremy: saving first meant extra
  clicks he did not want); after a successful send of an unsaved code a one-line, optional
  "Save this?" appears (name optional, defaults to the number); a menu of saved codes
  fills the box without sending. The earlier "name + code + Save a code" form is still in
  the collapsed *Codes* section for managing saved ones.
- **Known gap:** nothing a test vacuum can do ends in "docked" (`return_to_base`
  stops at "returning"), so it can be created docked but not driven to it. The panel
  refuses with a message. A decision is needed on whether the vacuum should dock
  itself after returning.
- **Known, older, not fixed:** the camera platform scans its `images` folder on the
  event loop (Home Assistant logs a "blocking call to scandir" warning at start-up).
- **Known future break found while testing:** `number.py`/`sensor.py` import
  `CONCENTRATION_*` constants Home Assistant deprecated; they are removed in HA Core
  2027.8 (Home Assistant logs a warning at every start).

VERIFIED against a running Home Assistant 2026.10.4 with its demo devices, driven
the way the panel drives them: 29 of 29 templates created, 49 of 49 demo devices
cloned (every reproducible kind), all 84 resulting entities showing live state,
and every control's action changing the state it should. Also 2026.8.0b3 for
registration, admin-only and restart. Also live: removing a device that was renamed
in Home Assistant (the panel shows the new name, removes by the file key, and
removing by the display name is refused); cloning with a push and with a text
notifier (each clone got a notifier); and the admin-only refusals above.
The page's behaviour is exercised in a simulated browser (`panel_page.test.mjs`,
needs `jsdom`). NOT verified: how it looks and behaves in a REAL browser (layout,
theme colours, narrow screens, the sidebar button, the real `hass` object and its
registry-event subscription).

## Tests (added 2026-08-01)

`tests/` guards the three silent-data-loss bugs fixed in this fork — the mutation
race, the truncate-before-serialize save, and a clone dropping abilities. Run them
inside an HA container (`tests/README.md`); 37 pass, no `pytest-asyncio` needed.

**Tamper-verified**, and that mattered: the first version of the suite passed
every deliberate break, because `docker exec` silently discards stdin without
`-i`, so the tampering never ran. A suite nobody has watched fail is not evidence.

**Backward compatibility is covered by design, not by luck**: every cloning key is
optional and falls back to the platform's original hardcoded default. VERIFIED
2026-08-01 against a hand-written upstream-style `virtual.yaml` — 8/8 devices
behaved identically, including the light and fan paths this fork rewrote most
(`support_color: true` still gives hs mode; `speed: true` still gives 3 speeds).

## Deprecations cleared (2026-11-06, HA 2026.11.0)

The first run on 2026.11.0 (released 2026-11-04) logged four warnings from this add-on.
All four are fixed; `tests/test_ha_deprecations.py` keeps them fixed.

- **`CONCENTRATION_PARTS_PER_MILLION` / `CONCENTRATION_MICROGRAMS_PER_CUBIC_METER`**
  (sensor.py, number.py) → `UnitOfRatio.PARTS_PER_MILLION` / `UnitOfDensity.MICROGRAMS_PER_CUBIC_METER`.
  VERIFIED on 2026.11.0 that each new member equals the old constant. The enums arrived with
  2026.7 (per the HA developer blog, 2026-06-30, "new unit enumerators"; not itself checked
  against HA's source). DECISION (Claude, 2026-11-06, awaiting Jeremy's confirmation): the
  minimum is raised to 2026.7.0 in `hacs.json` rather than carrying an import fallback.
  The old constants are removed in HA 2027.8.
- **Thermostat `_attr_temperature_unit` and `temperature_unit`** (climate.py) →
  `_attr_native_temperature_unit` / `native_temperature_unit`. The old names are removed in
  HA 2027.11 (and an ERROR for a custom integration from then). VERIFIED the new name does
  NOT exist on HA 2026.10.4 (it arrived with 2026.11: 3 thermostat tests failed there before
  this was handled), so the thermostat picks the name by asking the installed HA
  (`_UNIT_ATTR`). Nothing else in the add-on needs 2026.11.
- **Camera listing its images folder on the event loop** (camera.py) → listed once in an
  executor job at setup and handed to each camera. A camera built without the list (the
  tests, the old yaml path) still lists the folder itself.

## Bringing devices in, and the name review (2026-11-07, 0.16.0)

`bring_in.py` (new) reads an export file back and adds chosen devices to a group; the panel's
Clone everything tab drives it. Design, as Jeremy ruled it:

- **Identical devices are offered once.** Identical = same name, same entity ids, same
  abilities (`fingerprint`); the starting state, unique id and persistence flag do not count,
  and neither do firmware version or room. A device that is only the same by name gets
  `Name (2)`; a taken entity id gets `_2`. Nothing is replaced.
- **The comparison covers every group.** Found on a live Home Assistant 2026.11.0: bringing
  the same entity id into a second group left it with only one entity, because ids (and
  device keys) belong to the whole instance. `Index` is built from every group's file; an
  unreadable group file stops the import (its ids are unknown).
- **Names are not stripped automatically (DECISION, Jeremy 2026-11-06).** A program cannot tell
  a person's name from a two-word room name, and an entity id carries the name too. Instead the
  export lists every name (with a hint on person/tracker/phone-notifier rows, `looks_personal`)
  as editable boxes, and the same boxes appear on import. `apply_renames` is the one function
  both ends use. Names inside an entity's attribute text are not covered, and the warning says so.
- **Transport.** The file is POSTed to `/api/virtual/import_upload` (an administrator-only
  view; websocket messages are capped near 4 MB, an HTTP request at 16 MB) and held in memory
  for 30 minutes (at most 8 files), never written to disk. The summary sent back to the browser
  has names, kinds and ids but no states (a tracker's starting state is a place).
- **Group creation** uses the integration's own config flow (`_create_group`); the entries are
  checked against the platforms' schemas BEFORE the group is made, so a bad file leaves no
  empty group behind.
- **Panel gotcha:** `_loadChoices` used to redraw the whole Clone everything tab, which now
  would wipe a file being looked through. The tab is built once; only the group menu follows.
- Added to `export_devices`: `renames`, and a header line saying the file holds real names.
  New websocket commands: `virtual/import_preview`, `virtual/import_apply`,
  `virtual/import_forget`, `virtual/export_review`.
- **Found by the review agents, fixed:** a small yaml file can stand for a gigantic structure
  (aliases); `parse_export` counts what it expands to and stops (`EXPANDED_LIMIT`), and does NOT
  refuse aliases, because Home Assistant's own writer emits them when a list is used twice. Two
  imports into different groups at once could leave one entity id in both, because the other
  groups were read before the per-group lock: one import at a time now, for the whole instance.
  The export's `# Skipped:` comment used to name every device and entity the person had left
  out, which defeated leaving them out: counts only now. A lone entity is filed under its
  entity id, which survived a rename as the device key: it follows the rename now. A refused
  import into a NEW group left an empty group behind: it is checked before the group is made.
  `export_only` now refuses import. Ids from a file are lower-cased (the loader does).
- **Known, not fixed:** the preview does not reflect names typed after it was made (the result
  says what really happened); `create_device` and cloning do not compare ids with other groups
  at all (long-standing); what Home Assistant does when an imported id matches an entity of
  another integration is not verified.
- PistonCore was removed from the README, `info.md` and the image credits (Jeremy,
  2026-11-06); this file keeps the fork's history.

## Rules

- **Standalone self-sufficiency is REQUIRED** (§5.6): everything works from HA's own
  UI/services with no PistonCore. PistonCore's `/test-devices` panel is a convenience
  layer, never the only control surface.
- Keep it rebase-friendly: prefer ADDING files (new platform modules) over rewriting
  upstream ones, so pulling upstream fixes stays easy.
- **Split to its own repo at release** (§5.5); in-repo folder is for iteration now.

## The panel was rebuilt as tiles and tabs (2026-11-01)

Four tabs (Devices, Create, Clone a device, Clone everything), flat tiles with a coloured edge
on a device that is doing something, a live state on every part, switches labelled in words
(Locked | Unlocked, Clear | Detected), big devices folded with search and pins, lock codes kept
in the BROWSER and sent in Home Assistant's own `code` field, a Phone kind that asks push or
text (no other kind does), one optional push/text switch on Clone, and an Export form.
`virtual: {panel: false}` leaves the sidebar entry out. Bringing devices in from an export file
is NOT built yet (the tab says so). Checked by review agents (code and tests): they found, and
it now fixes, a refused choice on a focused select not being put back, the group picker not
following across tabs, saved codes lost when the browser refuses storage, repeated category
headings, a double Enter creating twice, and "one" lighting a tile as "on". Verified live:
the README's own throwaway-Home-Assistant recipe, with Home Assistant's demo devices, ends with
the panel registered, 30 templates in categories, 49 clonable devices, and a Phone made as a
text phone getting an `sms` notifier. On Windows the recipe's folder must be a real Windows
path (a shell path silently mounts an empty folder and Home Assistant starts without the add-on).
