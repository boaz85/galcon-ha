# Galcon 11000BT — Home Assistant Integration

Unofficial Bluetooth LE integration for the **Galcon 11000BT** (and likely 9001BT / 8000BT / 6100BT) irrigation timer, targeting [Home Assistant](https://www.home-assistant.io/).

> **Status:** Protocol fully reverse-engineered. ESP32/ESPHome and HA custom component in progress.

---

## Device

The Galcon 11000BT is a single-zone, battery-powered (2×AA) hose-end irrigation controller with Bluetooth 4.0 (BLE). It is controlled via the official *Galcon BT* iOS/Android app. This repository provides an open integration without the proprietary app.

**Confirmed compatible models:** 11000BT (verified), 9001BT (same UUID family, per community reports)

---

## BLE Protocol

All characteristics belong to the custom `e868xxxx-9c4b-11e4-b5f7-0002a5d5c51b` UUID family.

### Device behaviour

- The device **advertises continuously** even when idle, but at a low duty cycle (~4–8 second intervals). A 10-second passive scan may miss it; use a 30–60 second window or a callback-based scanner.
- Authentication (`\x01\x02` written to the AUTH characteristic) is required before any read or command. There is no real security — no cryptographic pairing, no key exchange.
- The device name in advertisements is `Galcon` (or `GL11000D-xxxxxxx` immediately after a button press).

### Services & Characteristics

#### Service `e8680100` — Control

| Characteristic | UUID | Properties | Description |
|---|---|---|---|
| PROGRAM | `e8680101` | read, write | Schedule configuration (20 bytes, see below) |
| STATUS | `e8680102` | read, notify | Valve state + remaining time (7 bytes, see below) |
| CONTROL | `e8680103` | read, write | Valve open/close command (7 bytes) |

#### Service `e8680200` — Auth / Time

| Characteristic | UUID | Properties | Description |
|---|---|---|---|
| AUTH | `e8680201` | write | Wake / authenticate the device |
| CLOCK | `e8680202` | read, notify | Current device RTC time (8 bytes, see below) |
| TIME SET | `e8680203` | write | Set device RTC time (same format as CLOCK) |

#### Service `e8680300` — Unknown

| Characteristic | UUID | Properties | Description |
|---|---|---|---|
| `e8680301` | write | Unknown |
| `e8680302` | read, notify | Unknown — all zeros observed |

#### Service `e8680400` — Setup

| Characteristic | UUID | Properties | Description |
|---|---|---|---|
| SETUP/PIN | `e8680401` | read, write | Unknown — all zeros observed |
| `e8680402` | read, notify | Unknown — all zeros observed |

---

### Characteristic Payloads

#### AUTH (`e8680201`) — write only

Always write `\x01\x02` before any other operation. Required after every new connection.

```
01 02
```

#### STATUS (`e8680102`) — 7 bytes

```
byte[0]  bit 0  : valve open (1) / closed (0)   [upper bits appear to be constant 0xd0]
byte[1]         : mode — 0 = auto/scheduled, 1 = manual
byte[2]         : remaining hours
byte[3]         : remaining minutes
byte[4]         : remaining seconds  (note: device may report 60 at tick boundary — normalise to total seconds)
byte[5]         : 0x47 — constant (firmware/model identifier)
byte[6]         : 0x00 — constant
```

Example — valve closed:  `d0 00 00 00 00 47 00`
Example — valve open, 10 min remaining:  `d1 01 00 09 3c 47 00`

The STATUS characteristic supports **notify** — subscribe to receive push updates instead of polling.

#### CONTROL (`e8680103`) — 7 bytes

```
Open valve:   00 01 00 00 00 00 00
Close valve:  01 00 00 00 00 00 00
```

#### PROGRAM (`e8680101`) — 20 bytes

```
byte[0]        : unknown (observed 0x00)
byte[1]        : duration in minutes
byte[2]        : day-of-week bitmask (LSB = Sunday)
                   bit 0 = Sunday
                   bit 1 = Monday
                   bit 2 = Tuesday
                   bit 3 = Wednesday
                   bit 4 = Thursday
                   bit 5 = Friday
                   bit 6 = Saturday
byte[3]        : start time 1 — hour   (0–23)
byte[4]        : start time 1 — minute (0–59)
byte[5]        : start time 2 — hour   (0xff = disabled)
byte[6]        : start time 2 — minute
byte[7]        : start time 3 — hour   (0xff = disabled)
byte[8]        : start time 3 — minute
byte[9]        : start time 4 — hour   (0xff = disabled)
byte[10]       : start time 4 — minute
bytes[11–19]   : zero-padded
```

Example — 10 min, Sun+Mon+Wed+Fri at 06:00, other slots disabled:
```
00 0a 2b 06 00 ff 00 ff 00 ff 00 00 00 00 00 00 00 00 00 00
```
`0x2b = 0b00101011` = bits 0,1,3,5 set = Sunday, Monday, Wednesday, Friday

#### CLOCK (`e8680202`) — 8 bytes

```
bytes[0–3]     : unknown (observed 0x00000000)
byte[4]        : hour   (0–23)
byte[5]        : minute (0–59)
byte[6]        : second (0–59)
byte[7]        : weekday (0 = Sunday, 1 = Monday, …, 6 = Saturday)
```

Example — Saturday 20:49:52:  `00 00 00 00 14 31 34 06`

---

### Protocol Flow

```
1. Wait for advertisement  (scan for name "Galcon" or service UUID e8680100-...)
2. Connect
3. Write AUTH char:     01 02
4. Read  STATUS char    → parse valve state and remaining time
5. Write CONTROL char   → open or close valve
6. Read  STATUS char    → confirm new state
7. Disconnect
```

---

## Python Tools (macOS / Linux)

Requires Python 3.9+ and [bleak](https://github.com/hbldh/bleak):

```bash
pip install bleak
```

### `scan.py` — find nearby Galcon devices

```bash
python3 scan.py
```

Lists all visible BLE devices and highlights any Galcon unit. Run for at least 30 seconds if the device doesn't appear immediately — it advertises every 4–8 seconds when idle.

### `probe.py` — inspect GATT services of a device

```bash
python3 probe.py <CoreBluetooth-UUID-or-MAC>
```

Connects and dumps all services and characteristics, flagging any Galcon-specific UUIDs.

### `galcon_test.py` — control the valve

The device is found automatically — no address needed. It advertises every 4–8 seconds even when idle.

```bash
python3 galcon_test.py status   # read valve state and remaining time
python3 galcon_test.py on       # open valve
python3 galcon_test.py off      # close valve
python3 galcon_test.py services # list all GATT characteristics
```

### `explore.py` — full protocol dump

```bash
python3 explore.py
```

Scans for the device, connects, reads every readable characteristic, and subscribes to all notifications for 10 seconds. Useful for protocol research.

> **macOS note:** CoreBluetooth assigns a random UUID per host to each peripheral instead of exposing the real MAC address. The UUID is stable for a given Mac+device pair. Use `scan.py` to discover the UUID first.

---

## References

- [suborb/GalconController](https://github.com/suborb/GalconController) — original Python proof-of-concept and Domoticz plugin (bluepy-based)
- [alutov/ESP32-R4sGate-for-Redmond](https://github.com/alutov/ESP32-R4sGate-for-Redmond) — ESP32 BLE-to-MQTT bridge with Galcon support (header file `r4sGate.h`)
- [Home Assistant community thread](https://community.home-assistant.io/t/galcon-irrigation-controller-integration-bt/664454)

---

## ESPHome Integration

The `esphome/` directory contains a ready-to-flash ESPHome configuration that exposes the Galcon as native Home Assistant entities over WiFi — no BLE adapter on the HA server required.

### Entities created

| Entity | Type | Description |
|---|---|---|
| Galcon Irrigation | `valve` | Open / close the valve |
| Galcon Irrigation Remaining | `sensor` | Remaining irrigation time (minutes) |
| Galcon Irrigation Connected | `binary_sensor` | BLE connection status (diagnostic) |

### Setup

**1. Install ESPHome**
```bash
pip install esphome
```

**2. Create your secrets file**
```bash
cp esphome/secrets.yaml.template esphome/secrets.yaml
# edit secrets.yaml with your WiFi credentials and HA API key
```

**3. Find the Galcon MAC address**

macOS hides real BLE MAC addresses; the ESP32 sees the real one. Flash the firmware once *without* setting `galcon_mac` (comment out the `ble_client` block and the `!secret galcon_mac` line). Watch the serial log — when the Galcon advertises you will see:

```
[galcon] Found Galcon  MAC: AA:BB:CC:DD:EE:FF  name: Galcon
```

Copy that MAC into `esphome/secrets.yaml` as `galcon_mac`, then reflash.

**4. Flash**
```bash
esphome run esphome/galcon.yaml
```

**5. Add to Home Assistant**

The device will appear automatically in HA via the ESPHome integration (Settings → Devices & Services). It exposes a `valve` entity you can use directly in automations and the Irrigation dashboard.

### How it works

- The ESP32 runs a continuous BLE scan. When the Galcon advertisement is detected (every 4–8 seconds), it connects automatically.
- On connection, it writes the AUTH characteristic (`\x01\x02`) once to unlock the session.
- It subscribes to **STATUS notifications** for real-time push updates (remaining time countdown, valve state). It also polls every 30 seconds as a fallback.
- Open/close commands write AUTH again followed by the CONTROL characteristic.
- `auto_connect: true` ensures the ESP32 reconnects automatically if the BLE link drops.

### Compatible ESP32 boards

Any ESP32 with BLE works. Recommended options for outdoor/near-valve placement:

| Board | Notes |
|---|---|
| M5Stack Atom Lite | Compact, easy to enclose |
| Wemos D1 Mini32 | Cheap, breadboard-friendly |
| ESP32-C3 SuperMini | Tiny, USB-C |
| Generic `esp32dev` | Default in config — works with most boards |

Change the `board:` key in `esphome/galcon.yaml` to match your hardware.

---

## Roadmap

- [x] BLE protocol reverse-engineered
- [x] Python tools for scanning, probing, and control
- [x] ESPHome BLE client YAML configuration
- [ ] Home Assistant custom component (`custom_components/galcon`)
  - [ ] `valve` entity (open/close)
  - [ ] `sensor` for remaining time
  - [ ] Schedule read/write via HA UI
  - [ ] Device clock sync

---

## License

MIT
