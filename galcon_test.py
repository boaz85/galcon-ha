#!/usr/bin/env python3
"""
Galcon 11000BT BLE test tool.
Usage:
  python3 galcon_test.py [on|off|status|services]

The device is found automatically by scanning. The valve advertises
every 4-8 seconds even when idle, so no button press is needed.
"""
import asyncio
import sys
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError

AUTH_UUID    = "e8680201-9c4b-11e4-b5f7-0002a5d5c51b"
STATUS_UUID  = "e8680102-9c4b-11e4-b5f7-0002a5d5c51b"
CONTROL_UUID = "e8680103-9c4b-11e4-b5f7-0002a5d5c51b"

CMD_OPEN  = bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_CLOSE = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])


def is_galcon(device, adv):
    return (
        "galcon" in (device.name or "").lower()
        or "gl11000" in (device.name or "").lower()
        or "e8680100-9c4b-11e4-b5f7-0002a5d5c51b" in [str(u).lower() for u in (adv.service_uuids or [])]
    )


def parse_status(data: bytearray) -> dict:
    total_s = data[2] * 3600 + data[3] * 60 + data[4]
    return {
        "valve_open":  bool(data[0] & 0x01),
        "manual_mode": bool(data[1]),
        "remaining_h": total_s // 3600,
        "remaining_m": (total_s % 3600) // 60,
        "remaining_s": total_s % 60,
        "raw":         bytes(data).hex(),
    }


def print_status(s: dict):
    state = "OPEN" if s["valve_open"] else "CLOSED"
    mode  = "manual" if s["manual_mode"] else "auto"
    remaining = f"{s['remaining_h']:02d}:{s['remaining_m']:02d}:{s['remaining_s']:02d}"
    print(f"  Valve:     {state}")
    print(f"  Mode:      {mode}")
    print(f"  Remaining: {remaining}")
    print(f"  Raw bytes: {s['raw']}")


async def find_galcon(timeout=30.0):
    print(f"Scanning for Galcon (up to {timeout:.0f}s)...")
    device = await BleakScanner.find_device_by_filter(is_galcon, timeout=timeout)
    if not device:
        print("Device not found.")
        sys.exit(1)
    print(f"Found: {device.name} at {device.address}")
    return device


async def run(command: str):
    device = await find_galcon()
    print("Connecting...")
    async with BleakClient(device, timeout=15.0) as client:
        if command == "services":
            print("\n=== Services & Characteristics ===")
            for service in client.services:
                print(f"\nService: {service.uuid}")
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    print(f"  Char: {char.uuid}  [{props}]")
            return

        await client.write_gatt_char(AUTH_UUID, bytes([0x01, 0x02]))

        if command == "status":
            data = await client.read_gatt_char(STATUS_UUID)
            print("\n=== Status ===")
            print_status(parse_status(bytearray(data)))

        elif command == "on":
            print("  Sending OPEN command...")
            await client.write_gatt_char(CONTROL_UUID, CMD_OPEN)
            await asyncio.sleep(1)
            data = await client.read_gatt_char(STATUS_UUID)
            print("\n=== Status after OPEN ===")
            print_status(parse_status(bytearray(data)))

        elif command == "off":
            print("  Sending CLOSE command...")
            await client.write_gatt_char(CONTROL_UUID, CMD_CLOSE)
            await asyncio.sleep(1)
            data = await client.read_gatt_char(STATUS_UUID)
            print("\n=== Status after CLOSE ===")
            print_status(parse_status(bytearray(data)))

        else:
            print(f"Unknown command: {command}")
            print("Use: status | on | off | services")


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    try:
        asyncio.run(run(command))
    except BleakError as e:
        print(f"BLE Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")


if __name__ == "__main__":
    main()
