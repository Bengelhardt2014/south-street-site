"""
Anchor the three Abbots Square parcels' latitudes to a geographically adjacent
north-side reference parcel — the westernmost clean 100-block parcel.

Per spec:
    1. Try 100 block (odd 101-199), pick westernmost (highest address number,
       closest to the 200 block boundary).
    2. If 100 block has none, fall back to 300 block (odd 301-399 except 401-05);
       pick easternmost.

Longitudes from the prior round are kept (already match south-side parcels
across the street).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = ROOT / "public" / "data" / "parcels.geojson.adjacent.bak"

# Reference longitudes from the prior round (unchanged)
LNG_REFS = {
    177: "254 SOUTH ST",
    178: "234 SOUTH ST",
    179: "212 SOUTH ST",
}


def first_num(addr: str) -> int | None:
    m = re.match(r"^(\d+)", addr or "")
    return int(m.group(1)) if m else None


def is_clean(mt: str | None) -> bool:
    return mt is not None and (mt.startswith("OPA") or mt.startswith("Exact"))


shutil.copy2(GJ_PATH, BACKUP)
print(f"Backup: {BACKUP.name}\n")

gj = json.load(open(GJ_PATH, encoding="utf-8"))
features_by_addr = {f["properties"]["address"]: f for f in gj["features"]}
features_by_id = {f["properties"]["id"]: f for f in gj["features"]}


# ---------- Find latitude reference parcel ----------
refs_100, refs_300 = [], []
for f in gj["features"]:
    p = f["properties"]
    a = p.get("address") or ""
    if "SOUTH ST" not in a:
        continue
    n = first_num(a)
    if not n or n % 2 == 0:
        continue
    if not is_clean(p.get("geocode_match_type")):
        continue
    lng, lat = f["geometry"]["coordinates"]
    if 101 <= n <= 199:
        refs_100.append((n, a, lat, lng))
    elif 301 <= n <= 399:
        refs_300.append((n, a, lat, lng))

if refs_100:
    # Westernmost (highest address) = closest to 200 block
    chosen = max(refs_100, key=lambda r: r[0])
    band_label = "100_block_north"
    band_desc = f"100 block (odd 101-199), westernmost = highest addr"
elif refs_300:
    # Easternmost (lowest address) = closest to 200 block
    chosen = min(refs_300, key=lambda r: r[0])
    band_label = "300_block_north"
    band_desc = f"300 block fallback (odd 301-399), easternmost = lowest addr"
else:
    raise SystemExit("!! No clean north-side reference parcels found in 100 or 300 block")

ref_addr = chosen[1]
ref_lat = chosen[2]
ref_lng = chosen[3]
match_type = f"Anchored_to_{band_label}"

print(f"Latitude reference parcel:")
print(f"  {ref_addr:<22}  lat={ref_lat:.5f}  lng={ref_lng:.5f}")
print(f"  ({band_desc})")


# ---------- Pull longitude references ----------
print(f"\nLongitude references (unchanged from prior round):")
lng_target_by_pid = {}
for pid, addr in LNG_REFS.items():
    f = features_by_addr.get(addr)
    if not f:
        raise SystemExit(f"!! Reference {addr!r} not found")
    lng, lat = f["geometry"]["coordinates"]
    lng_target_by_pid[pid] = lng
    print(f"  parcel {pid}  <- {addr:<14}  lng={lng:.5f}")


# ---------- Apply ----------
print(f"\nApplying:")
for pid, lng in lng_target_by_pid.items():
    feat = features_by_id[pid]
    old_lng, old_lat = feat["geometry"]["coordinates"]
    new_lat, new_lng = round(ref_lat, 5), round(lng, 5)
    feat["geometry"]["coordinates"] = [new_lng, new_lat]
    feat["properties"]["geocode_match_type"] = match_type
    addr = feat["properties"]["address"]
    print(f"  parcel {pid}  {addr:<14}  "
          f"({old_lat:.5f}, {old_lng:.5f}) -> ({new_lat:.5f}, {new_lng:.5f})")

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# ---------- Report ----------
print()
print("=" * 60)
print("FINAL")
print("=" * 60)

print(f"\nReference parcel:  {ref_addr}  lat = {ref_lat:.5f}")
print(f"match_type:        {match_type}")

print(f"\nFinal Abbots Square coordinates (east -> west):")
for pid in (179, 178, 177):
    lng, lat = features_by_id[pid]["geometry"]["coordinates"]
    addr = features_by_id[pid]["properties"]["address"]
    print(f"  parcel {pid}  {addr:<14}  ({lat:.5f}, {lng:.5f})")

# Cross-street alignment sanity
print(f"\nLongitude alignment with south-side parcels (5-decimal):")
for pid, ref in LNG_REFS.items():
    a_lng = round(features_by_id[pid]["geometry"]["coordinates"][0], 5)
    f = features_by_addr[ref]
    r_lng = round(f["geometry"]["coordinates"][0], 5)
    print(f"  parcel {pid}  {a_lng:.5f}   {ref}: {r_lng:.5f}   "
          f"{'== MATCH' if a_lng == r_lng else 'MISMATCH'}")

# All three same lat?
lats = {features_by_id[pid]["geometry"]["coordinates"][1] for pid in (177, 178, 179)}
print(f"\nAll three latitudes equal: {'YES' if len(lats) == 1 else 'NO'} ({sorted(lats)})")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
