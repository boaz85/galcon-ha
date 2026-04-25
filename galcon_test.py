#!/usr/bin/env python3
"""
Galcon 11000BT BLE test tool.
Usage:
  python3 galcon_test.py <device_address_or_uuid> [on|off|status]

Examples:
  python3 galcon_test.py AA:BB:CC:DD:EE:FF status
  python3 galcon_test.py AA:BB:CC:DD:EE:FF on
  python3 galcon_test.py AA:BB:CC:DD:EE:FF off
"""
import asyncio
import sys
from bleak import BleakClient
from bleak.exc import BleakError

AUTH_UUID    = "e8680201-9c4b-11e4-b5f7-0002a5d5c51b"
STATUS_UUID  = "e8680102-9c4b-11e4-b5f7-0002a5d5c51b"
CONTROL_UUID = "e8680103-9c4b-11e4-b5f7-0002a5d5c51b"

CMD_OPEN  = bytes([0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00])
CMD_CLOSE = bytes([0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])


def parse_status(data: bytearray) -> dict:
    return {
        "valve_open":    bool(data[0] & 0x01),
        "manual_mode":   bool(data[1]),
        "remaining_h":   data[2],
        "remaining_m":   data[3],
        "remaining_s":   data[4],
        "raw":           data.hex(),
    }


def print_status(s: dict):
    state = "OPEN" if s["valve_open"] else "CLOSED"
    mode  = "manual" if s["manual_mode"] else "auto"
    remaining = f"{s['remaining_h']:02d}:{s['remaining_m']:02d}:{s['remaining_s']:02d}"
    print(f"  Valve:     {state}")
    print(f"  Mode:      {mode}")
    print(f"  Remaining: {remaining}")
    print(f"  Raw bytes: {s['raw']}")


async def authenticate(client: BleakClient):
    print("  Authenticating...")
    await client.write_gatt_char(AUTH_UUID, bytes([0x01, 0x02]))


async def run(address: str, command: str):
    print(f"Connecting to {address}...")
    async with BleakClient(address, timeout=15.0) as client:
        print(f"Connected. MTU: {client.mtu_size}")

        # List services on first run so we can verify UUIDs
        if command == "services":
            print("\n=== Services & Characteristics ===")
            for service in client.services:
                print(f"\nService: {service.uuid}")
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    print(f"  Char: {char.uuid}  [{props}]")
            return

        await authenticate(client)

        if command == "status":
            print("  Reading status...")
            data = await client.read_gatt_char(STATUS_UUID)
            s = parse_status(bytearray(data))
            print("\n=== Status ===")
            print_status(s)

        elif command == "on":
            print("  Sending OPEN command...")
            await client.write_gatt_char(CONTROL_UUID, CMD_OPEN)
            await asyncio.sleep(1)
            data = await client.read_gatt_char(STATUS_UUID)
            s = parse_status(bytearray(data))
            print("\n=== Status after OPEN ===")
            print_status(s)

        elif command == "off":
            print("  Sending CLOSE command...")
            await client.write_gatt_char(CONTROL_UUID, CMD_CLOSE)
            await asyncio.sleep(1)
            data = await client.read_gatt_char(STATUS_UUID)
            s = parse_status(bytearray(data))
            print("\n=== Status after CLOSE ===")
            print_status(s)

        else:
            print(f"Unknown command: {command}")
            print("Use: status | on | off | services")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    address = sys.argv[1]
    command = sys.argv[2] if len(sys.argv) > 2 else "status"

    try:
        asyncio.run(run(address, command))
    except BleakError as e:
        print(f"BLE Error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nAborted.")


if __name__ == "__main__":
    main()
