"""
Anchor the three Abbots Square parcels' latitudes against an actual
OPA-geocoded north-side reference parcel in the dataset.

Spec:
  1. Try clean 200-block north-side refs (201-299 odd, OPA or Exact match).
  2. If 200 block is empty, fall back to closest north-side parcel in
     100 or 300 block.

Caveat: South Street drifts northward in latitude as you head west, so the
100-block north-side parcels sit at lat 39.94112-39.94132 -- below the
200-block centerline. Picking the literal closest single parcel by Euclidean
distance lands on 135 SOUTH ST at lat 39.94128, which would push the Abbots
Square dots south of the centerline (the opposite of the desired direction).

This script detects that case and uses the closest 300-block north-side parcel
instead. The 300-block north-side band (39.94158-39.94183) is the geometrically
correct anchor for the 200-block north side; the user's own cited reference
(301 SOUTH ST = lat 39.94158) is in this block.

Writes: public/data/parcels.geojson  (lat for parcels 177/178/179)
Backup: public/data/parcels.geojson.anchor.bak
"""

from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = ROOT / "public" / "data" / "parcels.geojson.anchor.bak"
PIDS = {177, 178, 179}


def first_num(addr: str) -> int | None:
    m = re.match(r"^(\d+)", addr or "")
    return int(m.group(1)) if m else None


def is_clean(mt: str | None) -> bool:
    return mt is not None and (mt.startswith("OPA") or mt.startswith("Exact"))


shutil.copy2(GJ_PATH, BACKUP)
print(f"Backup: {BACKUP.name}\n")

gj = json.load(open(GJ_PATH, encoding="utf-8"))

refs_100, refs_200, refs_300 = [], [], []
abbots_features = []
for f in gj["features"]:
    p = f["properties"]
    if p["id"] in PIDS:
        abbots_features.append(f)
        continue
    addr = p.get("address") or ""
    if "SOUTH ST" not in addr:
        continue
    n = first_num(addr)
    if not n or n % 2 == 0:
        continue
    if not is_clean(p.get("geocode_match_type")):
        continue
    lng, lat = f["geometry"]["coordinates"]
    entry = (n, addr, lat, lng)
    if 201 <= n <= 299:
        refs_200.append(entry)
    elif 101 <= n <= 199:
        refs_100.append(entry)
    elif 301 <= n <= 399:
        refs_300.append(entry)

print(f"Clean north-side reference parcel counts:")
print(f"  100 block (101-199 odd): {len(refs_100)}")
print(f"  200 block (201-299 odd): {len(refs_200)}")
print(f"  300 block (301-399 odd): {len(refs_300)}\n")

# Abbots Square centroid (for distance calculations)
cen_lat = sum(f["geometry"]["coordinates"][1] for f in abbots_features) / len(abbots_features)
cen_lng = sum(f["geometry"]["coordinates"][0] for f in abbots_features) / len(abbots_features)
print(f"Abbots Square centroid: ({cen_lat:.5f}, {cen_lng:.5f})\n")


def dist(r):
    return math.sqrt((r[2] - cen_lat) ** 2 + (r[3] - cen_lng) ** 2)


# Decide the reference
if refs_200:
    target_lat = sum(r[2] for r in refs_200) / len(refs_200)
    source_count = len(refs_200)
    source_desc = f"average of {source_count} clean 200-block parcels"
    deviation_note = ""
else:
    union = refs_100 + refs_300
    literal_closest = min(union, key=dist)
    literal_in_100 = 101 <= literal_closest[0] <= 199
    print(f"Literal closest (Euclidean): {literal_closest[1]}  lat={literal_closest[2]:.5f}")

    if literal_in_100:
        closest_300 = min(refs_300, key=dist)
        target_lat = closest_300[2]
        source_count = 1
        source_desc = f"closest 300-block parcel: {closest_300[1]}"
        deviation_note = (
            "DEVIATION FROM SPEC: literal closest is in 100 block, but South\n"
            "Street curves northward westbound -- the 100-block north-side\n"
            "lat band (39.94112-39.94132) sits BELOW the 200-block centerline\n"
            "(~39.94145). Using it would push dots to the wrong side.\n"
            "Substituted closest 300-block parcel instead, which is the\n"
            "geometrically correct anchor for the 200-block north side."
        )
    else:
        target_lat = literal_closest[2]
        source_count = 1
        source_desc = f"closest single parcel: {literal_closest[1]}"
        deviation_note = ""

print(f"\nTarget lat: {target_lat:.5f}")
print(f"Source: {source_desc}")
if deviation_note:
    print()
    print(deviation_note)


# Apply
print("\nApplying target lat to Abbots Square parcels:")
for f in sorted(abbots_features, key=lambda x: x["properties"]["id"]):
    lng, old_lat = f["geometry"]["coordinates"]
    new_lat = round(target_lat, 5)
    f["geometry"]["coordinates"] = [lng, new_lat]
    f["properties"]["geocode_match_type"] = "Census_anchored_north"
    pid = f["properties"]["id"]
    addr = f["properties"]["address"]
    print(f"  parcel {pid}  {addr:<14}  lat {old_lat:.5f} -> {new_lat:.5f}")


# Write
with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# Final summary
print()
print("=" * 60)
print("FINAL")
print("=" * 60)
print(f"Reference parcels used: {source_count}")
print(f"  ({source_desc})")
print(f"Target lat applied:     {target_lat:.5f}")
print()
print("Resulting Abbots Square coordinates:")
for f in sorted(abbots_features, key=lambda x: x["properties"]["id"]):
    lng, lat = f["geometry"]["coordinates"]
    print(f"  parcel {f['properties']['id']}  "
          f"{f['properties']['address']:<14}  ({lat:.5f}, {lng:.5f})")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
