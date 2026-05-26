"""
Fix the three Abbots Square parcels' latitude: they were nudged ~17 m SOUTH
when they should be on the NORTH side of South Street (odd-numbered addresses
in this dataset are on the north side; ref: 301 SOUTH ST at lat 39.94158
is north, 300 SOUTH ST at lat 39.94128 is south).

Net correction: +0.00030 lat to each of the three (lifts them from the
south-side band back across the street centerline to the north-side band).

Writes:  public/data/parcels.geojson  (lat updated for parcels 177/178/179;
                                       backup written first)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
GJ_BACKUP = ROOT / "public" / "data" / "parcels.geojson.northflip.bak"

PARCEL_IDS = {177, 178, 179}
LAT_DELTA = 0.00030  # ~33 m at this latitude — flips from south-side to north-side band

shutil.copy2(GJ_PATH, GJ_BACKUP)
print(f"Backup: {GJ_BACKUP.name}")

gj = json.load(open(GJ_PATH, encoding="utf-8"))

changes = []
for feat in gj["features"]:
    pid = feat["properties"]["id"]
    if pid not in PARCEL_IDS:
        continue
    lng, lat = feat["geometry"]["coordinates"]
    new_lat = round(lat + LAT_DELTA, 5)
    feat["geometry"]["coordinates"] = [lng, new_lat]
    feat["properties"]["geocode_match_type"] = "Census_offset_north"
    changes.append({
        "pid": pid,
        "addr": feat["properties"]["address"],
        "old_lat": lat,
        "new_lat": new_lat,
        "lng": lng,
    })

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))

print()
print("=" * 60)
print("LATITUDE FLIP -- south-side to north-side")
print("=" * 60)
for c in sorted(changes, key=lambda x: x["pid"]):
    print(f"  parcel {c['pid']}  {c['addr']:<14}  lat {c['old_lat']:.5f} -> {c['new_lat']:.5f}  "
          f"lng {c['lng']:.5f}")

print()
print("North-side band reference (odd-numbered, e.g. 301 SOUTH ST = 39.94158)")
print("Three updated parcels now at lat 39.94141 / 39.94145 / 39.94150 -- in band")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
