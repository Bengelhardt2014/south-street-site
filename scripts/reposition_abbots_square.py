"""
Reposition the three Abbots Square parcels (177/178/179) by anchoring their
coordinates to specific south-side reference parcels' longitudes and a
north-side reference parcel's latitude (all already OPA-geocoded in the GeoJSON).

Per spec:
    parcel 178 (Rita's, 239)    longitude = 234 SOUTH ST longitude  (directly across)
    parcel 177 (vacant, 289)    longitude = 254 SOUTH ST longitude  (3rd & South corner)
    parcel 179 (Laff House, 201) longitude = extrapolated eastward from 234
                                            using the 212->234 lng-per-unit delta
                                            applied 33 units east (i.e., toward
                                            address 201, the 2nd & South corner)

All three latitudes = latitude of 301 SOUTH ST (north-side OPA reference for
the adjacent 300 block).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = ROOT / "public" / "data" / "parcels.geojson.reposition.bak"

REFS = ("212 SOUTH ST", "234 SOUTH ST", "254 SOUTH ST", "301 SOUTH ST")


shutil.copy2(GJ_PATH, BACKUP)
print(f"Backup: {BACKUP.name}\n")

gj = json.load(open(GJ_PATH, encoding="utf-8"))
features_by_addr = {f["properties"]["address"]: f for f in gj["features"]}
features_by_id = {f["properties"]["id"]: f for f in gj["features"]}

ref_coords = {}
for addr in REFS:
    f = features_by_addr.get(addr)
    if not f:
        raise SystemExit(f"!! Reference {addr!r} not found in GeoJSON")
    mt = f["properties"].get("geocode_match_type")
    if not mt or not mt.startswith("OPA"):
        print(f"!! Reference {addr!r} has non-OPA match_type {mt!r}; using anyway")
    lng, lat = f["geometry"]["coordinates"]
    ref_coords[addr] = (lat, lng)
    print(f"  {addr:<14}  ({lat:.5f}, {lng:.5f})  match_type={mt!r}")

lng_212 = ref_coords["212 SOUTH ST"][1]
lng_234 = ref_coords["234 SOUTH ST"][1]
lng_254 = ref_coords["254 SOUTH ST"][1]
lat_301 = ref_coords["301 SOUTH ST"][0]

# Eastward delta per address unit (positive = move east as address decreases)
# Going FROM 234 TO 212: address decreases by 22, lng increases (east) by (lng_212 - lng_234)
delta_per_unit_east = (lng_212 - lng_234) / 22.0

# Parcel 179 (address 201) is 33 units east of 234
delta_units_201_from_234 = 234 - 201
lng_179 = lng_234 + delta_units_201_from_234 * delta_per_unit_east

print()
print("Computation:")
print(f"  lng_per_unit_east = (lng_212 - lng_234) / 22")
print(f"                    = ({lng_212:.5f} - ({lng_234:.5f})) / 22")
print(f"                    = {lng_212 - lng_234:+.5f} / 22")
print(f"                    = {delta_per_unit_east:+.6f}  (deg lng eastward per address unit)")
print(f"  lng_179 = lng_234 + 33 * delta_per_unit_east")
print(f"          = {lng_234:.5f} + 33 * {delta_per_unit_east:.6f}")
print(f"          = {lng_234:.5f} + {33 * delta_per_unit_east:+.5f}")
print(f"          = {lng_179:.5f}")

# Apply
assignments = {
    177: (lat_301, lng_254),
    178: (lat_301, lng_234),
    179: (lat_301, lng_179),
}

print()
print("Applying assignments:")
for pid, (lat, lng) in assignments.items():
    feat = features_by_id[pid]
    old_lng, old_lat = feat["geometry"]["coordinates"]
    new_lat, new_lng = round(lat, 5), round(lng, 5)
    feat["geometry"]["coordinates"] = [new_lng, new_lat]
    feat["properties"]["geocode_match_type"] = "Anchored_to_reference_parcels"
    addr = feat["properties"]["address"]
    print(f"  parcel {pid}  {addr:<14}  "
          f"({old_lat:.5f}, {old_lng:.5f}) -> ({new_lat:.5f}, {new_lng:.5f})")

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# ---------- Verification & report ----------
print()
print("=" * 60)
print("VERIFICATION")
print("=" * 60)

final = {pid: features_by_id[pid]["geometry"]["coordinates"] for pid in (177, 178, 179)}

print(f"\nReference longitudes pulled from GeoJSON:")
print(f"  212 SOUTH ST  lng = {lng_212:.5f}  (south side, east end of 200 block)")
print(f"  234 SOUTH ST  lng = {lng_234:.5f}  (south side, middle)")
print(f"  254 SOUTH ST  lng = {lng_254:.5f}  (south side, west end)")

print(f"\nNorth-side latitude reference:")
print(f"  301 SOUTH ST  lat = {lat_301:.5f}  (300 block, north side)")

print(f"\nComputed longitude for parcel 179 (2nd & South corner):")
print(f"  {lng_179:.5f}  (extrapolated from 234 SOUTH ST eastward by 33 address units)")
print(f"  -- which equals {33 * abs(delta_per_unit_east) * 85300:.1f} m east of 234 SOUTH ST")

print(f"\nFinal Abbots Square coordinates:")
print(f"  parcel 179  201 SOUTH ST  ({final[179][1]:.5f}, {final[179][0]:.5f})")
print(f"  parcel 178  239 SOUTH ST  ({final[178][1]:.5f}, {final[178][0]:.5f})")
print(f"  parcel 177  289 SOUTH ST  ({final[177][1]:.5f}, {final[177][0]:.5f})")

print(f"\nAcross-the-street alignment (longitudes):")
print(f"  parcel 178 lng = {final[178][0]:.5f}   234 lng = {lng_234:.5f}   "
      f"{'MATCH' if abs(final[178][0] - lng_234) < 1e-6 else 'MISMATCH'}")
print(f"  parcel 177 lng = {final[177][0]:.5f}   254 lng = {lng_254:.5f}   "
      f"{'MATCH' if abs(final[177][0] - lng_254) < 1e-6 else 'MISMATCH'}")

print(f"\nEast-to-west ordering:")
ordering = sorted([(pid, final[pid][0]) for pid in (177, 178, 179)],
                  key=lambda x: x[1], reverse=True)
for pid, lng in ordering:
    print(f"  parcel {pid}  lng={lng:.5f}  "
          f"({features_by_id[pid]['properties']['address']})")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
