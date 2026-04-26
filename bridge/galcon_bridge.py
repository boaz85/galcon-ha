#!/usr/bin/env python3
"""
Galcon 11000BT → Home Assistant MQTT bridge.

Scans for the Galcon irrigator over BLE, reads valve status,
and exposes it as native HA entities via MQTT Discovery.

Entities created in HA:
  - valve:  Galcon Irrigation  (open / close)
  - sensor: Galcon Remaining   (minutes left, counts down while running)
"""
import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError, BleakDeviceNotFoundError
import paho.mqtt.client as mqtt

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("galcon")

# ── BLE constants ─────────────────────────────────────────────────────────────

AUTH_UUID    = "e8680201-9c4b-11e4-b5f7-0002a5d5c51b"
STATUS_UUID  = "e8680102-9c4b-11e4-b5f7-0002a5d5c51b"
CONTROL_UUID = "e8680103-9c4b-11e4-b5f7-0002a5d5c51b"

CMD_OPEN  = bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_CLOSE = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])


def is_galcon(device, adv) -> bool:
    name = (device.name or "").lower()
    uuids = [str(u).lower() for u in (adv.service_uuids or [])]
    return (
        "galcon" in name
        or "gl11000" in name
        or "e8680100-9c4b-11e4-b5f7-0002a5d5c51b" in uuids
    )


def parse_status(data: bytes) -> tuple[bool, int]:
    """Return (valve_open, remaining_seconds)."""
    valve_open = bool(data[0] & 0x01)
    total_secs = data[2] * 3600 + data[3] * 60 + data[4]
    return valve_open, total_secs


# ── MQTT topics ───────────────────────────────────────────────────────────────

TOPIC_AVAIL  = "galcon/availability"
TOPIC_STATE  = "galcon/valve/state"
TOPIC_CMD    = "galcon/valve/set"
TOPIC_REMAIN = "galcon/remaining/state"

DISCOVERY_VALVE = {
    "name": "Galcon Irrigation",
    "unique_id": "galcon_11000bt_valve",
    "device_class": "water",
    "state_topic": TOPIC_STATE,
    "command_topic": TOPIC_CMD,
    "payload_open": "OPEN",
    "payload_close": "CLOSE",
    "state_open": "OPEN",
    "state_closed": "CLOSED",
    "availability_topic": TOPIC_AVAIL,
    "payload_available": "online",
    "payload_not_available": "offline",
    "optimistic": False,
    "device": {
        "identifiers": ["galcon_11000bt"],
        "name": "Galcon 11000BT",
        "manufacturer": "Galcon",
        "model": "11000BT",
    },
}

DISCOVERY_SENSOR = {
    "name": "Galcon Remaining",
    "unique_id": "galcon_11000bt_remaining",
    "state_topic": TOPIC_REMAIN,
    "unit_of_measurement": "min",
    "device_class": "duration",
    "state_class": "measurement",
    "icon": "mdi:timer-outline",
    "availability_topic": TOPIC_AVAIL,
    "payload_available": "online",
    "payload_not_available": "offline",
    "device": {"identifiers": ["galcon_11000bt"]},
}


# ── Bridge ────────────────────────────────────────────────────────────────────

class GalconBridge:
    def __init__(self, config: dict):
        self._cfg = config
        self._running = True
        self._loop: asyncio.AbstractEventLoop | None = None
        self._cmd_queue: asyncio.Queue[str] = asyncio.Queue()

        self._mq = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="galcon-bridge")
        if config.get("mqtt_user"):
            self._mq.username_pw_set(config["mqtt_user"], config.get("mqtt_password", ""))
        self._mq.will_set(TOPIC_AVAIL, "offline", retain=True)
        self._mq.on_connect = self._on_mqtt_connect
        self._mq.on_message = self._on_mqtt_message
        self._mq.on_disconnect = self._on_mqtt_disconnect

    # ── MQTT callbacks ────────────────────────────────────────────────────────

    def _on_mqtt_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            log.error("MQTT connect failed, rc=%s", reason_code)
            return
        log.info("MQTT connected to %s:%d", self._cfg["mqtt_host"], self._cfg["mqtt_port"])
        client.publish("homeassistant/valve/galcon_irrigation/config",
                       json.dumps(DISCOVERY_VALVE), retain=True)
        client.publish("homeassistant/sensor/galcon_remaining/config",
                       json.dumps(DISCOVERY_SENSOR), retain=True)
        client.subscribe(TOPIC_CMD)
        log.info("HA Discovery published, subscribed to %s", TOPIC_CMD)

    def _on_mqtt_disconnect(self, client, userdata, flags, reason_code, properties):
        log.warning("MQTT disconnected (rc=%s), will reconnect", reason_code)

    def _on_mqtt_message(self, client, userdata, msg):
        payload = msg.payload.decode().strip().upper()
        log.info("MQTT command received: %s", payload)
        if payload in ("OPEN", "CLOSE") and self._loop:
            self._loop.call_soon_threadsafe(self._cmd_queue.put_nowait, payload)

    # ── MQTT publish helpers ──────────────────────────────────────────────────

    def _publish_state(self, valve_open: bool, remaining_secs: int):
        state = "OPEN" if valve_open else "CLOSED"
        remaining_min = round(remaining_secs / 60.0, 1)
        self._mq.publish(TOPIC_STATE, state, retain=True)
        self._mq.publish(TOPIC_REMAIN, str(remaining_min), retain=True)
        self._mq.publish(TOPIC_AVAIL, "online", retain=True)
        log.info("State: %s  remaining=%.1f min", state, remaining_min)

    def _set_offline(self):
        self._mq.publish(TOPIC_AVAIL, "offline", retain=True)

    # ── BLE helpers ───────────────────────────────────────────────────────────

    async def _find_galcon(self):
        poll = self._cfg.get("poll_interval", 30)
        while self._running:
            try:
                log.info("Scanning for Galcon...")
                device = await BleakScanner.find_device_by_filter(
                    is_galcon, timeout=30.0
                )
                if device:
                    log.info("Found: %s  %s", device.name, device.address)
                    return device
                log.warning("Galcon not found in scan, retrying in %ds", poll)
            except Exception as e:
                log.warning("Scan error: %s", e)
            await asyncio.sleep(poll)

    async def _read_status(self, client: BleakClient) -> tuple[bool, int] | None:
        try:
            data = await client.read_gatt_char(STATUS_UUID)
            return parse_status(bytes(data))
        except Exception as e:
            log.warning("Status read error: %s", e)
            return None

    async def _send_command(self, client: BleakClient, cmd: str):
        try:
            await client.write_gatt_char(AUTH_UUID, bytes([0x01, 0x02]))
            payload = CMD_OPEN if cmd == "OPEN" else CMD_CLOSE
            await client.write_gatt_char(CONTROL_UUID, payload)
            log.info("Command sent: %s", cmd)
            await asyncio.sleep(1)
            result = await self._read_status(client)
            if result:
                self._publish_state(*result)
        except Exception as e:
            log.warning("Command error: %s", e)

    # ── Main BLE loop ─────────────────────────────────────────────────────────

    async def _ble_connect_and_work(self):
        """Connect once, handle any queued commands, read state, disconnect."""
        device = await self._find_galcon()
        if not device:
            return False

        got_state = False
        try:
            async with BleakClient(device, timeout=30.0) as client:
                log.info("Connected to Galcon")
                await client.write_gatt_char(AUTH_UUID, bytes([0x01, 0x02]))

                # Drain any queued commands first
                while not self._cmd_queue.empty():
                    cmd = self._cmd_queue.get_nowait()
                    await self._send_command(client, cmd)

                # Read and publish current state
                result = await self._read_status(client)
                if result:
                    self._publish_state(*result)
                    got_state = True

        except (BleakError, BleakDeviceNotFoundError, OSError) as e:
            if not got_state:
                log.warning("BLE error: %s", e)
                return False
            log.debug("BLE disconnect error (state already read): %s", e)
        except Exception as e:
            if not got_state:
                log.error("Unexpected BLE error: %s", e)
                return False
            log.debug("BLE disconnect error (state already read): %s", e)

        log.info("Disconnected from Galcon")
        return True

    async def _ble_loop(self):
        poll = self._cfg.get("poll_interval", 120)
        consecutive_failures = 0

        # Initial connect on startup
        ok = await self._ble_connect_and_work()
        if ok:
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                self._set_offline()

        while self._running:
            # Sleep until poll interval, but wake early if a command arrives
            try:
                cmd = await asyncio.wait_for(self._cmd_queue.get(), timeout=poll)
                self._cmd_queue.put_nowait(cmd)  # put it back so _ble_connect_and_work drains it
            except asyncio.TimeoutError:
                pass  # regular poll

            if not self._running:
                break

            ok = await self._ble_connect_and_work()
            if ok:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    self._set_offline()
                    log.warning("3 consecutive BLE failures — marking offline")

    # ── Entry point ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()

        # MQTT
        self._mq.connect_async(
            self._cfg["mqtt_host"],
            self._cfg.get("mqtt_port", 1883),
            keepalive=60,
        )
        self._mq.loop_start()

        # Graceful shutdown
        for sig in (signal.SIGINT, signal.SIGTERM):
            self._loop.add_signal_handler(sig, self._stop)

        try:
            await self._ble_loop()
        finally:
            self._set_offline()
            self._mq.loop_stop()
            self._mq.disconnect()
            log.info("Bridge stopped")

    def _stop(self):
        log.info("Shutdown signal received")
        self._running = False


# ── Config + main ─────────────────────────────────────────────────────────────

def load_config() -> dict:
    config_path = Path(__file__).parent / "galcon_bridge_config.json"
    if not config_path.exists():
        log.error("Config file not found: %s", config_path)
        log.error("Copy galcon_bridge_config.json.template to galcon_bridge_config.json and fill in your values.")
        sys.exit(1)
    with open(config_path) as f:
        return json.load(f)


if __name__ == "__main__":
    config = load_config()
    logging.getLogger().setLevel(config.get("log_level", "INFO"))
    asyncio.run(GalconBridge(config).run())
