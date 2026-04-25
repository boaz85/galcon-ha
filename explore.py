#!/usr/bin/env python3
"""
Deep protocol exploration of the Galcon BLE device.
Reads all readable characteristics and subscribes to notifications.
"""
import asyncio
import sys
from bleak import BleakClient, BleakScanner

DEVICE_NAME = "Galcon"

ALL_CHARS = {
    "e8680101-9c4b-11e4-b5f7-0002a5d5c51b": "SVC1-CHAR1 (unknown)",
    "e8680102-9c4b-11e4-b5f7-0002a5d5c51b": "STATUS",
    "e8680103-9c4b-11e4-b5f7-0002a5d5c51b": "CONTROL",
    "e8680201-9c4b-11e4-b5f7-0002a5d5c51b": "AUTH",
    "e8680202-9c4b-11e4-b5f7-0002a5d5c51b": "SVC2-CHAR2 (unknown)",
    "e8680203-9c4b-11e4-b5f7-0002a5d5c51b": "TIME",
    "e8680301-9c4b-11e4-b5f7-0002a5d5c51b": "SVC3-CHAR1 (unknown)",
    "e8680302-9c4b-11e4-b5f7-0002a5d5c51b": "SVC3-CHAR2 (unknown)",
    "e8680401-9c4b-11e4-b5f7-0002a5d5c51b": "SETUP/PIN",
    "e8680402-9c4b-11e4-b5f7-0002a5d5c51b": "SVC4-CHAR2 (unknown)",
}

AUTH_UUID    = "e8680201-9c4b-11e4-b5f7-0002a5d5c51b"
STATUS_UUID  = "e8680102-9c4b-11e4-b5f7-0002a5d5c51b"


def decode_status(data: bytes):
    raw = bytes(data).hex()
    valve_open  = bool(data[0] & 0x01)
    manual_mode = bool(data[1])
    h, m, s     = data[2], data[3], data[4]
    # Normalise: device reports seconds=60 at rollover boundaries
    total_seconds = h * 3600 + m * 60 + s
    rh = total_seconds // 3600
    rm = (total_seconds % 3600) // 60
    rs = total_seconds % 60
    return (f"valve={'OPEN' if valve_open else 'CLOSED'}  mode={'manual' if manual_mode else 'auto'}  "
            f"remaining={rh:02d}:{rm:02d}:{rs:02d}  byte0=0x{data[0]:02x}  "
            f"byte5=0x{data[5]:02x}  byte6=0x{data[6]:02x}  raw={raw}")


def notification_handler(char_uuid, label):
    def handler(sender, data):
        raw = bytes(data).hex()
        print(f"  [NOTIFY] {label}: {raw}  ({list(data)})")
        if "STATUS" in label:
            print(f"           {decode_status(data)}")
    return handler


async def explore(device):
    print(f"Connecting to {device.address}...\n")
    async with BleakClient(device, timeout=15.0) as client:
        print("Connected!\n")

        # Authenticate first
        print("--- Authenticating ---")
        await client.write_gatt_char(AUTH_UUID, bytes([0x01, 0x02]))
        print("Auth written.\n")

        # Read all readable characteristics
        print("--- Reading all characteristics ---")
        for service in client.services:
            for char in service.characteristics:
                uuid = char.uuid.lower()
                label = ALL_CHARS.get(uuid, "unknown")
                if "read" in char.properties:
                    try:
                        data = await client.read_gatt_char(uuid)
                        raw = bytes(data).hex()
                        decoded = ""
                        if uuid == "e8680102-9c4b-11e4-b5f7-0002a5d5c51b":
                            decoded = f"\n    => {decode_status(data)}"
                        print(f"  {label:<25} {uuid}  =>  {raw}  {list(data)}{decoded}")
                    except Exception as e:
                        print(f"  {label:<25} {uuid}  =>  READ ERROR: {e}")

        # Subscribe to all notifiable characteristics and watch for 10s
        print("\n--- Subscribing to notifications (10 seconds) ---")
        for service in client.services:
            for char in service.characteristics:
                uuid = char.uuid.lower()
                label = ALL_CHARS.get(uuid, "unknown")
                if "notify" in char.properties:
                    try:
                        await client.start_notify(uuid, notification_handler(uuid, label))
                        print(f"  Subscribed to {label} ({uuid})")
                    except Exception as e:
                        print(f"  Failed to subscribe to {label}: {e}")

        print("\nWaiting 10 seconds for notifications...\n")
        await asyncio.sleep(10)

        print("\n--- Reading STATUS again after wait ---")
        data = await client.read_gatt_char(STATUS_UUID)
        print(f"  {decode_status(data)}")


async def find_galcon(timeout=30.0):
    """Scan until the Galcon advertisement is seen, then return the device object."""
    print(f"Scanning for Galcon (up to {timeout:.0f}s)...")
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: (
            "galcon" in (d.name or "").lower()
            or "gl11000" in (d.name or "").lower()
            or "e8680100-9c4b-11e4-b5f7-0002a5d5c51b" in [str(u).lower() for u in (adv.service_uuids or [])]
        ),
        timeout=timeout,
    )
    return device


async def main():
    # Always scan first so CoreBluetooth has a fresh peripheral reference
    device = await find_galcon()
    if not device:
        print("Device not found. Make sure the Galcon is active (valve running or recently pressed).")
        sys.exit(1)
    print(f"Found: {device.name} at {device.address}\n")
    await explore(device)


if __name__ == "__main__":
    asyncio.run(main())
