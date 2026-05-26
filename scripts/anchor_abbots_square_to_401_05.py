"""
Final positioning of the three Abbots Square parcels using direct anchoring
to specific OPA-geocoded reference parcels (no extrapolation, no offsets).

Per spec:
    All three latitudes = latitude of 401-05 SOUTH ST  (north-side, 400 block)
    parcel 179 (201)    longitude = 212 SOUTH ST lng   (directly across)
    parcel 178 (239)    longitude = 234 SOUTH ST lng   (directly across)
    parcel 177 (289)    longitude = 254 SOUTH ST lng   (directly across)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = ROOT / "public" / "data" / "parcels.geojson.final.bak"

LAT_REF = "401-05 SOUTH ST"
LNG_REFS = {  # parcel_id -> reference address
    177: "254 SOUTH ST",
    178: "234 SOUTH ST",
    179: "212 SOUTH ST",
}

shutil.copy2(GJ_PATH, BACKUP)
print(f"Backup: {BACKUP.name}\n")

gj = json.load(open(GJ_PATH, encoding="utf-8"))
features_by_addr = {f["properties"]["address"]: f for f in gj["features"]}
features_by_id = {f["properties"]["id"]: f for f in gj["features"]}


def coords_of(addr: str) -> tuple[float, float]:
    f = features_by_addr.get(addr)
    if not f:
        raise SystemExit(f"!! Reference {addr!r} not found in GeoJSON")
    lng, lat = f["geometry"]["coordinates"]
    return lat, lng


# Pull refs
lat_target, lng_401 = coords_of(LAT_REF)
print(f"Latitude reference:")
print(f"  {LAT_REF:<18}  lat={lat_target:.5f}  lng={lng_401:.5f}  (north-side, 400 block)\n")

print(f"Longitude references:")
lng_target_by_pid = {}
for pid, addr in LNG_REFS.items():
    _, lng = coords_of(addr)
    lng_target_by_pid[pid] = lng
    print(f"  parcel {pid}  <- {addr:<14}  lng={lng:.5f}")


# Apply
print(f"\nApplying:")
for pid, lng in lng_target_by_pid.items():
    feat = features_by_id[pid]
    old_lng, old_lat = feat["geometry"]["coordinates"]
    new_lat, new_lng = round(lat_target, 5), round(lng, 5)
    feat["geometry"]["coordinates"] = [new_lng, new_lat]
    feat["properties"]["geocode_match_type"] = "Anchored_to_401-05_SOUTH"
    addr = feat["properties"]["address"]
    print(f"  parcel {pid}  {addr:<14}  "
          f"({old_lat:.5f}, {old_lng:.5f}) -> ({new_lat:.5f}, {new_lng:.5f})")

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# Verify
print()
print("=" * 60)
print("VERIFICATION")
print("=" * 60)
final = {pid: features_by_id[pid]["geometry"]["coordinates"] for pid in (177, 178, 179)}

print(f"\nFinal Abbots Square coordinates:")
for pid in (179, 178, 177):  # east-to-west
    lng, lat = final[pid]
    addr = features_by_id[pid]["properties"]["address"]
    print(f"  parcel {pid}  {addr:<14}  ({lat:.5f}, {lng:.5f})")

# All three lats equal?
lats = {final[pid][1] for pid in (177, 178, 179)}
print(f"\nAll three latitudes equal: {'YES' if len(lats) == 1 else 'NO'}  "
      f"(distinct lat values: {sorted(lats)})")

# Across-the-street alignment at 5-decimal precision
print(f"\nAcross-the-street alignment (5-decimal precision):")
for pid, ref in LNG_REFS.items():
    a_lng = round(final[pid][0], 5)
    _, r_lng = coords_of(ref)
    r_lng = round(r_lng, 5)
    print(f"  parcel {pid} lng={a_lng:.5f}   {ref} lng={r_lng:.5f}   "
          f"{'== MATCH' if a_lng == r_lng else 'MISMATCH'}")

# East-to-west ordering
print(f"\nEast-to-west ordering:")
for pid in sorted(final.keys(), key=lambda p: final[p][0], reverse=True):
    addr = features_by_id[pid]["properties"]["address"]
    print(f"  parcel {pid}  lng={final[pid][0]:.5f}  ({addr})")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
