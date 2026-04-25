#!/usr/bin/env python3
"""
Try connecting to a BLE device and check if it's a Galcon.
Usage: python3 probe.py <address>
"""
import asyncio
import sys
from bleak import BleakClient
from bleak.exc import BleakError

GALCON_UUIDS = {
    "e8680201-9c4b-11e4-b5f7-0002a5d5c51b": "AUTH",
    "e8680102-9c4b-11e4-b5f7-0002a5d5c51b": "STATUS",
    "e8680103-9c4b-11e4-b5f7-0002a5d5c51b": "CONTROL",
    "e8680401-9c4b-11e4-b5f7-0002a5d5c51b": "SETUP/PIN",
    "e8680203-9c4b-11e4-b5f7-0002a5d5c51b": "TIME",
}

async def probe(address: str):
    print(f"Connecting to {address}...")
    try:
        async with BleakClient(address, timeout=10.0) as client:
            print("Connected!\n")
            print("=== All GATT Services & Characteristics ===")
            galcon_hits = []
            for service in client.services:
                print(f"\nService: {service.uuid}")
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    label = GALCON_UUIDS.get(char.uuid.lower(), "")
                    tag = f"  <-- GALCON {label}" if label else ""
                    print(f"  Char: {char.uuid}  [{props}]{tag}")
                    if label:
                        galcon_hits.append(label)

            print()
            if galcon_hits:
                print(f"*** THIS IS A GALCON DEVICE! Found: {', '.join(galcon_hits)} ***")
            else:
                print("Not a Galcon device (no matching characteristics).")
    except BleakError as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 probe.py <device-address>")
        sys.exit(1)
    asyncio.run(probe(sys.argv[1]))
