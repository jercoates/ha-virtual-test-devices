# HA Virtual Test Devices

A simple, one-click custom integration for Home Assistant that instantly creates a full set of realistic virtual test devices.

Perfect for safely testing complex automations — especially those involving hard-to-test sensors like smoke, water leaks, and CO detectors.

## Features

- **One-click setup** — Install via HACS or manually and add the integration.
- Automatically creates **12 individual virtual devices** in a new **"Test"** area.
- Each device registers properly in the Home Assistant **Device Registry** with correct device classes, icons, and behavior.
- Fully controllable from the UI — easily "fire" smoke, water, motion, door, etc., to trigger your automations.
- Works natively with **PistonCore**, standard automations, dashboards, and scripts.
- Clean removal — disable or remove the integration and everything disappears with **no residue**.

### Included Virtual Devices
- Virtual Motion Sensor
- Virtual Door/Contact Sensor
- Virtual Smoke Detector
- Virtual Water/Leak Sensor
- Virtual CO Detector
- Virtual Lock
- Virtual Temperature Sensor
- Virtual Humidity Sensor
- Virtual Lux Sensor
- Virtual Switch
- Virtual Dimmable Light
- Virtual Media Player

## Why This Exists

Testing automations that rely on smoke detectors, water sensors, or CO alarms is annoying and sometimes unsafe with real hardware.  
This integration gives you a clean sandbox so you can instantly see if your logic works — without waiting for hardware or creating messy workarounds.

## Installation

### Option 1: Via HACS (Recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed in your Home Assistant.
2. Go to **HACS → Integrations → Explore & Download Repositories**.
3. Search for **"HA Virtual Test Devices"**.
4. Click **Download** and restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration**.
6. Search for **"HA Virtual Test Devices"** and add it.

### Option 2: Manual Installation

1. Download or clone this repository.
2. Copy the `custom_components/ha_virtual_test_devices` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration** → Search for **"HA Virtual Test Devices"** and add it.

After adding the integration, you will immediately see the 12 devices in the **Test** area.

## Usage

- Open the **Test** area in your dashboard (Home Assistant usually auto-creates cards).
- Tap any entity to change its state (e.g., turn the **Virtual Smoke Detector** on to trigger your smoke alarm automation).
- Use the normal `turn_on` / `turn_off` / `toggle` services in Developer Tools or automations.
- All devices start in a safe default state (sensors off, light off, lock locked, etc.).

## Removing the Devices

Simply disable or delete the integration in **Settings → Devices & Services**.  
All devices and entities will be removed cleanly with no leftovers.

## Compatibility

- Works with Home Assistant 2025.1 and newer.
- Designed to work seamlessly with **PistonCore**.
- Does not interfere with any of your existing devices or integrations.

## Future Plans (V2+)

- User-selectable device types
- Multiple test areas
- Custom virtual device creation
- State mirroring (virtual device shadows a real one)

## Support & Feedback

Found a bug or have a feature request?  
Open an issue on GitHub: [Issues](https://github.com/YOURUSERNAME/ha-virtual-test-devices/issues)

---

**Made for the Home Assistant community** — especially for those building and testing advanced automations with PistonCore.

Enjoy testing without the hassle!
