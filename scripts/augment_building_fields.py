"""
Add three building-detail fields to parcels.geojson without re-geocoding:
  building_footprint, building_height, open_violations.

Reads:  source-files/building_level_data.csv
        public/data/parcels.geojson
Writes: public/data/parcels.geojson  (overwritten in place; coords unchanged)

Run:  python scripts/augment_building_fields.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "source-files" / "building_level_data.csv"
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"


def to_int(v) -> int | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


csv_rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
gj = json.load(open(GJ_PATH, encoding="utf-8"))

by_pid = {i: r for i, r in enumerate(csv_rows, start=1)}

updated = 0
for feat in gj["features"]:
    pid = feat["properties"]["id"]
    r = by_pid.get(pid)
    if not r:
        continue
    feat["properties"]["building_footprint"] = to_int(r.get("Building Footprint"))
    feat["properties"]["building_height"] = to_int(r.get("Building Height"))
    feat["properties"]["open_violations"] = to_int(r.get("Open Violation Count"))
    updated += 1

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))

# Distribution + spot checks
fp = [f["properties"]["building_footprint"] for f in gj["features"]]
ht = [f["properties"]["building_height"] for f in gj["features"]]
ov = [f["properties"]["open_violations"] for f in gj["features"]]

print(f"Augmented {updated} features")
print()
print("Distribution:")
print(f"  building_footprint  > 0:  {sum(1 for x in fp if x and x>0):>3}   blank/zero:  "
      f"{sum(1 for x in fp if not x):>3}   max: "
      f"{max((x for x in fp if x is not None), default=0):,}")
print(f"  building_height     > 0:  {sum(1 for x in ht if x and x>0):>3}   blank/zero:  "
      f"{sum(1 for x in ht if not x):>3}   max: "
      f"{max((x for x in ht if x is not None), default=0):,}")
print(f"  open_violations     > 0:  {sum(1 for x in ov if x and x>0):>3}   blank/zero:  "
      f"{sum(1 for x in ov if not x):>3}   max: "
      f"{max((x for x in ov if x is not None), default=0):,}")

# Spot checks
print()
print("Spot checks:")
spot_addrs = {
    "200-210 LOMBARD",
    "530 SOUTH ST",
    "100 SOUTH ST",
    "1020-1024 SOUTH ST",
    "604-06 SOUTH ST",
}
for f in gj["features"]:
    a = f["properties"].get("address") or ""
    if a in spot_addrs:
        p = f["properties"]
        print(f"  id={p['id']:>3}  {a:<22}  fp={p['building_footprint']!s:<6}  "
              f"ht={p['building_height']!s:<4}  ov={p['open_violations']!s}")

# Top open-violations parcels (worth eyeballing)
print()
print("Top 5 parcels by open_violations:")
top = sorted(
    [f for f in gj["features"] if f["properties"].get("open_violations")],
    key=lambda f: f["properties"]["open_violations"],
    reverse=True,
)[:5]
for f in top:
    p = f["properties"]
    print(f"  id={p['id']:>3}  {p['address']:<22}  open_violations={p['open_violations']}")

size = GJ_PATH.stat().st_size
print(f"\nFinal file size: {size:,} bytes ({size/1024:.1f} KB)")
