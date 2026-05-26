"""
Hard-coded mathematical positioning for the three Abbots Square parcels.

Reads SOUTH_LAT from 234 SOUTH ST (south-side OPA reference), adds 0.00045 to
get NORTH_LAT, applies NORTH_LAT to parcels 177/178/179, keeps longitudes
unchanged. Verifies NORTH_LAT > every south-side 200-block parcel lat before
writing.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = ROOT / "public" / "data" / "parcels.geojson.hardcoded.bak"

OFFSET = 0.00045
SOUTH_REF = "234 SOUTH ST"
ABBOTS_PIDS = (177, 178, 179)
SOUTH_200_BLOCK = ["212 SOUTH ST", "222 SOUTH ST", "234 SOUTH ST",
                   "240 SOUTH ST", "250 SOUTH ST", "254 SOUTH ST"]

shutil.copy2(GJ_PATH, BACKUP)
print(f"Backup: {BACKUP.name}\n")

gj = json.load(open(GJ_PATH, encoding="utf-8"))
by_addr = {f["properties"]["address"]: f for f in gj["features"]}
by_id = {f["properties"]["id"]: f for f in gj["features"]}


# ---------- Step 1: Read SOUTH_LAT from 234 SOUTH ST ----------
ref = by_addr.get(SOUTH_REF)
if not ref:
    raise SystemExit(f"!! {SOUTH_REF!r} not found")
SOUTH_LAT = ref["geometry"]["coordinates"][1]
print(f"Step 1: SOUTH_LAT = {SOUTH_LAT:.5f}  (from {SOUTH_REF})\n")


# ---------- Step 2: Compute NORTH_LAT ----------
NORTH_LAT = round(SOUTH_LAT + OFFSET, 5)
print(f"Step 2: NORTH_LAT = SOUTH_LAT + {OFFSET}")
print(f"                  = {SOUTH_LAT:.5f} + {OFFSET}")
print(f"                  = {NORTH_LAT:.5f}\n")


# ---------- Step 4: Verify (do this BEFORE applying) ----------
print(f"Step 4: VERIFY NORTH_LAT ({NORTH_LAT:.5f}) > every south-side 200-block parcel lat")
south_lats = []
for addr in SOUTH_200_BLOCK:
    f = by_addr.get(addr)
    if not f:
        print(f"  !! {addr!r} not found in GeoJSON; skipping")
        continue
    lat = f["geometry"]["coordinates"][1]
    south_lats.append((addr, lat))
    cmp_ok = NORTH_LAT > lat
    print(f"  {addr:<14}  lat={lat:.5f}   NORTH_LAT > lat ? {'YES' if cmp_ok else 'NO !!!'}")

all_ok = all(NORTH_LAT > lat for _, lat in south_lats)
if not all_ok:
    print(f"\n!! VERIFICATION FAILED -- aborting, no write")
    raise SystemExit(1)
print(f"  All six checks pass.\n")


# ---------- Step 3: Apply ----------
print(f"Step 3: Apply NORTH_LAT to parcels {ABBOTS_PIDS}:")
for pid in ABBOTS_PIDS:
    feat = by_id[pid]
    old_lng, old_lat = feat["geometry"]["coordinates"]
    feat["geometry"]["coordinates"] = [old_lng, NORTH_LAT]
    feat["properties"]["geocode_match_type"] = "Hard_coded_north_offset"
    addr = feat["properties"]["address"]
    print(f"  parcel {pid}  {addr:<14}  "
          f"({old_lat:.5f}, {old_lng:.5f}) -> ({NORTH_LAT:.5f}, {old_lng:.5f})")


# ---------- Step 5: Write ----------
with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# ---------- Final report ----------
print()
print("=" * 60)
print("FINAL")
print("=" * 60)

print(f"\nSOUTH_LAT (from 234 SOUTH ST):   {SOUTH_LAT:.5f}")
print(f"OFFSET:                           +{OFFSET}")
print(f"NORTH_LAT (applied to all three): {NORTH_LAT:.5f}")

print(f"\nSouth-side 200-block reference latitudes:")
for addr, lat in south_lats:
    delta_m = (NORTH_LAT - lat) * 111000  # rough meters
    print(f"  {addr:<14}  lat={lat:.5f}   NORTH_LAT - lat = +{NORTH_LAT-lat:.5f} (~{delta_m:.0f} m north)")

print(f"\nFinal Abbots Square coordinates (east -> west):")
for pid in (179, 178, 177):
    lng, lat = by_id[pid]["geometry"]["coordinates"]
    addr = by_id[pid]["properties"]["address"]
    mt = by_id[pid]["properties"]["geocode_match_type"]
    print(f"  parcel {pid}  {addr:<14}  ({lat:.5f}, {lng:.5f})  match_type={mt!r}")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
