#!/usr/bin/env python3
"""Scan for Galcon BLE devices nearby — shows full advertisement details."""
import asyncio
from bleak import BleakScanner

GALCON_SERVICE_UUID = "e8680100-9c4b-11e4-b5f7-0002a5d5c51b"

async def scan():
    print("Scanning for BLE devices for 15 seconds...\n")
    devices = await BleakScanner.discover(timeout=15.0, return_adv=True)

    galcon_found = []
    others = []

    for device, adv in devices.values():
        name = device.name or "(no name)"
        uuids = [str(u).lower() for u in (adv.service_uuids or [])]
        mfr_data = adv.manufacturer_data or {}
        svc_data = adv.service_data or {}
        is_galcon = GALCON_SERVICE_UUID in uuids or "galcon" in name.lower()

        lines = [f"  {name:<30} | {device.address} | RSSI: {adv.rssi} dBm"]
        if uuids:
            lines.append(f"    Service UUIDs:  {', '.join(uuids)}")
        if mfr_data:
            for company_id, data in mfr_data.items():
                lines.append(f"    Manufacturer:   company=0x{company_id:04X}  data={data.hex()}")
        if svc_data:
            for uuid, data in svc_data.items():
                lines.append(f"    Service data:   uuid={uuid}  data={data.hex()}")

        entry = "\n".join(lines)
        if is_galcon:
            galcon_found.append(entry)
        else:
            others.append(entry)

    if galcon_found:
        print("=== GALCON DEVICE(S) FOUND ===")
        for e in galcon_found:
            print(e)
        print()
    else:
        print("No Galcon device identified by service UUID or name.\n")

    print(f"=== All devices ({len(others) + len(galcon_found)}) ===")
    for e in sorted(others):
        print(e)

if __name__ == "__main__":
    asyncio.run(scan())
