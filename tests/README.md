# Tests

These guard bugs that each caused **silent data loss or silent wrong answers** on a
real bench. None of them raised an error when they happened — that is why they are
tested rather than trusted.

| file | guards |
|---|---|
| `test_mutation_queue.py` | Concurrent `create_device` / `remove_device` losing devices. Six concurrent creates once produced **one** device and reported success. Also checks a burst still collapses to a single config-entry reload, that the reload still happens when the last call of a burst fails or is cancelled, and that a change is never saved over a devices file that could not be read or that has gone missing from a running group. |
| `test_file_safety.py` | A failed save destroying the existing device file. The savers used to open the real file in `'w'` (truncating it) and only then serialize, swallowing failures at debug level — one unserialisable value emptied the file and the integration stopped loading. Also: a damaged identity (meta) file is an error, never "empty". |
| `test_capability_capture.py` | A clone dropping abilities. The capture list is checked **against Home Assistant's own `capability_attributes`**, so a new HA capability shows up as a failure instead of being silently missed. Also checks every capturable key is declared by its platform's schema, and that nothing but primitives reaches the yaml. |
| `test_notifier_clone.py` | A cloned device getting nowhere for a push or a text to land: the push/text label, the UI-only `add_notifier`, the automatic push notifier for a companion-app phone, and the controls (an ordinary device gets nothing). |
| `test_explicit_ids.py` | Stand-ins losing the identity they were given: an entry naming its own `entity_id` keeps it, its unique id is derived (never random), devices carry their own details, and entries that name no id still behave exactly as before. |
| `test_orphans.py` | Removing one entity taking its whole device with it. Entities are removed one row at a time; a device goes only when the file no longer lists it, and nothing is removed at all on a file that could not be read, or one that has gone missing from a group that already has devices. |
| `test_export.py` | The export: lock and alarm codes and text passwords never reach the file, every skip is accounted for, every entry is checked against its platform's own schema, and the written file loads back with the same entity ids. An export only ever replaces a file an earlier export wrote, never `configuration.yaml` or a group's own devices file. |
| `test_failure_reporting.py` | Failures that used to look like success: unload stranding platforms, removing a device that is not there, and (new) an entry a platform would reject, an unknown platform, or a device name already in the file being replaced in silence. Everything is checked BEFORE anything is written. |
| `test_select_text.py` | The `select` and `text` platforms: a value off a menu, or one that breaks the limits Home Assistant itself enforces, must not leave an entity that errors when read. |
| `test_version.py` | The version drifting: there is one, and it is the manifest's. |
| `test_panel.py` | What the sidebar panel may learn: groups, devices and clonable real devices are listed by name and structure only, nothing from inside a group; and every template in `templates.json` is a valid device, with every platform offered. |
| `test_lock_code.py` | A lock records the code it was sent (`last_code`) and counts every lock, unlock and open (`sequence`): cleared when an action carries none, kept as text (a leading zero, even `0`, survives), recorded even when the lock takes time to move, reset on a restart. **Run through a real Home Assistant core**, because "an automation still triggers" is a claim about what Home Assistant announces: three uses of the same code on a lock already unlocked give three state-change events, and take the count away and they give none; a lock with a `code_format` refuses a wrong or missing code before it is counted; a default code set in Home Assistant's options shows as the code. |
| `test_bring_in.py` | Bringing devices in from an export file: a file that is not an export is refused with a reason (and cannot make the reader build objects); a device identical to one already in ANY group (state ignored) is offered once and never added twice; the same name with different abilities gets a number, and an id already taken gets `_2` even when it is in another group; nothing is replaced; names typed over are what is saved and the old ones are not in the file; an entry the platforms would reject, an unreadable group file, an unknown device or nothing ticked changes nothing; held files expire and are capped; the four panel commands (each refuses a non-administrator, passes the typed names through to the file, and is registered) and the upload endpoint (administrators-only, login required, size limit, read off the event loop) and what the panel is told about each device (names, kinds, ids, the person marker, never a state); group creation against a stand-in for the config flow; what lands on disk after a clash; a file that stands for a gigantic structure (yaml aliases) is refused in moments; two imports at the same moment never leave the same id in two groups; no group is made for devices that would not be added; nothing comes in when Home Assistant is set to export only. |
| `test_ha_deprecations.py` | Things Home Assistant has told the add-on to stop doing, kept fixed: the old gas and particle unit constants (loading the sensor and number platforms must log no deprecation, and CO, CO2 and the µg/m³ gases must still read ppm and µg/m³), the thermostat's temperature-unit name (it must use the name the installed Home Assistant understands; a Celsius clone starts at 21, a Fahrenheit clone at 70; loading and building one logs no deprecation), and the camera listing its images folder on the event loop (setup does it once, off the loop, and each camera is handed the list). |
| `panel_controls.test.mjs` | **35 tests. Run with Node, not pytest:** `node --test tests/panel_controls.test.mjs`. What the panel offers for each kind of device and the Home Assistant action each control calls (toggle polarity for lock and cover, a vacuum's states, a thermostat's modes, ...), and the "Test —" naming. Needs nothing installed. |
| `panel_page.test.mjs` | **132 tests. Run with Node and `jsdom`:** `cd tests && npm install --no-save jsdom && node --test panel_page.test.mjs` (skips with a message without jsdom). The panel loaded into a simulated browser page and clicked through: what each click sends to Home Assistant (create, clone with push/text, remove by file key, every kind of control), what a refused action shows, and what survives a refresh (half-typed values, search, "Remove it?"). Also the export name review (what is warned, what is sent, that nothing is renamed for the person) and bringing a file in (what each status says, ticking, group choice, names changed on the way in, that a Refresh does not throw away the file being looked through, that names from a file are shown as text and never as markup). Not a substitute for a real browser. Always run it with `--test-timeout=60000`: a panel that loops would otherwise hang the run with no message. |

## Running them

They need a real Home Assistant, because the behaviour under test lives in the
seam between this integration and HA's own enums and yaml handling. The simplest
way to get one is the HA container:

```bash
docker run -d --name ha-test -p 8124:8123 \
  -v "$PWD/ha-config:/config" ghcr.io/home-assistant/home-assistant:stable

# put the integration and the tests where HA can import them
docker cp custom_components ha-test:/config/custom_components
docker cp tests             ha-test:/config/tests

docker exec ha-test python -m pytest /config/tests -q
```

Expect `409 passed`. There is no `pytest-asyncio` dependency — async cases call
`asyncio.run` directly, so HA and pytest are all you need.

## If you change the capture list

`CLONE_ATTRS` in `clone.py` and the platform schemas are **one contract**: the
platforms validate against closed schemas, so a key a platform does not declare
fails entity creation outright. Change both together, or
`test_every_capturable_key_is_declared_by_its_platform` will tell you.

## Keeping the suite honest

A test that cannot fail is worse than no test. After changing these, break the
thing on purpose and confirm the suite notices — that is how the first version of
this suite was found to be testing nothing at all (the tamper never applied, so
everything "passed"). Known-good result:

| break | failures |
|---|---|
| remove a key from `CLONE_ATTRS` | 4 |
| restore the truncate-before-serialize save | 2 |
| remove the lock in `_mutate_and_reload` | 4 |
