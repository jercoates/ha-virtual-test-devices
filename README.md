# HA Virtual Test Devices

A simple custom integration that creates 12 realistic virtual devices for testing automations in Home Assistant — especially useful with **PistonCore**.

One click gives you motion, smoke, water leak, CO, door, lock, light, and more — all properly registered as real devices.

### Features
- Creates 12 individual virtual devices in a **"Test"** area
- Uses correct device classes (proper icons and behavior)
- Easy to trigger states for testing complex automations
- Clean removal — disable the integration and everything disappears
- Includes a ready-to-use **Virtual Test Lab** dashboard

### Installation

1. Copy the `custom_components/ha_virtual_test_devices` folder into your Home Assistant `/homeassistant/custom_components/` (or `/config/custom_components/`) folder.
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** → Search for **"HA Virtual Test Devices"** and add it.

### After Installation

1. Go to the **Test** area (it should appear automatically).
2. **Import the Test Dashboard** (recommended):
   - Go to **Settings → Dashboards**
   - Click the three dots in the top right → **Import dashboard**
   - Paste the content from `test_dashboard.yaml` (included in this repo)
   - Save

You now have big, easy-to-use buttons to trigger smoke, water leak, motion, etc.

### Included Virtual Devices
- Virtual Motion Sensor
- Virtual Door Sensor
- Virtual Smoke Detector
- Virtual Water Leak Sensor
- Virtual CO Detector
- Virtual Lock
- Virtual Temperature Sensor
- Virtual Humidity Sensor
- Virtual Lux Sensor
- Virtual Switch
- Virtual Dimmable Light
- Virtual Media Player

### Purpose
Perfect for testing automations safely before buying hardware, especially tricky ones involving smoke, water, or CO detectors.

---

Made for easy testing with PistonCore and standard Home Assistant automations.
