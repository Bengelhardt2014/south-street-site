"""
Adjust the geocoded positions of the three Abbots Square / South Street frontage
parcels to anchor at the building's corner addresses (rather than midpoints).

Display addresses are already correct in the CSV and GeoJSON from a prior fix;
this script only updates the GeoJSON coordinates.

Targets:
    parcel 179 (Laff House,        display '201-235 SOUTH ST')  -> '201 SOUTH ST'  (2nd & South corner)
    parcel 178 (Rita's,            display '239 SOUTH ST')      -> '239 SOUTH ST'  (unchanged)
    parcel 177 (other vacant,      display '249-289 SOUTH ST')  -> '289 SOUTH ST'  (3rd & South corner)

OPA first, Census fallback (as before — OPA has no record for odd-numbered
South Street addresses in this block because Abbots Square's storefronts share
a master parcel).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
GJ_BACKUP = ROOT / "public" / "data" / "parcels.geojson.corners.bak"

CARTO_URL = "https://phl.carto.com/api/v2/sql"
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# parcel_id -> new geocoding target
TARGETS = {
    177: "289 SOUTH ST",
    178: "239 SOUTH ST",
    179: "201 SOUTH ST",
}


def opa_geocode(addr: str):
    sql = (
        "SELECT parcel_number, ST_Y(the_geom) AS lat, ST_X(the_geom) AS lng "
        "FROM opa_properties_public "
        f"WHERE location = '{addr}'"
    )
    r = requests.post(CARTO_URL, data={"q": sql}, timeout=30)
    r.raise_for_status()
    rows = [
        x for x in r.json().get("rows", [])
        if x.get("lat") is not None and x.get("lng") is not None
    ]
    if not rows:
        return None
    first = rows[0]
    return float(first["lat"]), float(first["lng"]), first["parcel_number"]


def census_geocode(addr: str):
    r = requests.get(
        CENSUS_URL,
        params={
            "address": f"{addr}, Philadelphia, PA",
            "benchmark": "Public_AR_Current",
            "format": "json",
        },
        timeout=30,
    )
    r.raise_for_status()
    matches = r.json().get("result", {}).get("addressMatches", [])
    if not matches:
        return None
    c = matches[0]["coordinates"]
    return float(c["y"]), float(c["x"])


shutil.copy2(GJ_PATH, GJ_BACKUP)
print(f"Backup: {GJ_BACKUP.name}")

gj = json.load(open(GJ_PATH, encoding="utf-8"))
features_by_id = {f["properties"]["id"]: f for f in gj["features"]}

results = {}
for pid, target in TARGETS.items():
    print(f"\nparcel {pid}  target={target!r}")
    hit = opa_geocode(target)
    if hit:
        lat, lng, opa_pn = hit
        source = "Manual_OPA"
        print(f"  OPA match: ({lat:.5f}, {lng:.5f})  opa_parcel_number={opa_pn!r}")
    else:
        print(f"  OPA had no record; trying Census")
        c = census_geocode(target)
        if c is None:
            print(f"  !! Census also missed; skipping")
            continue
        lat, lng = c
        source = "Manual_Census"
        print(f"  Census match: ({lat:.5f}, {lng:.5f})")

    feat = features_by_id[pid]
    old_lng, old_lat = feat["geometry"]["coordinates"]
    feat["geometry"]["coordinates"] = [lng, lat]
    feat["properties"]["geocode_match_type"] = source
    results[pid] = {
        "lat": lat, "lng": lng, "source": source, "target": target,
        "display": feat["properties"]["address"],
        "old_lat": old_lat, "old_lng": old_lng,
    }

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))

print()
print("=" * 60)
print("FINAL")
print("=" * 60)
for pid in sorted(results.keys()):
    r = results[pid]
    print(f"  parcel {pid}  display={r['display']!r}  target={r['target']!r}")
    print(f"            old  ({r['old_lat']:.5f}, {r['old_lng']:.5f})")
    print(f"            new  ({r['lat']:.5f}, {r['lng']:.5f})  source={r['source']}")
    # rough distance moved (meters): lat 1deg = 111km, lng at lat 39.94 ~ 85.3km
    dlat_m = (r['lat'] - r['old_lat']) * 111000
    dlng_m = (r['lng'] - r['old_lng']) * 85300
    dist_m = (dlat_m**2 + dlng_m**2) ** 0.5
    print(f"            moved {dist_m:.1f} m")

print()
print("Spatial ordering (east -> west):")
for pid in sorted(results.keys(), key=lambda p: results[p]["lng"], reverse=True):
    r = results[pid]
    print(f"  parcel {pid}  lng={r['lng']:.5f}  {r['display']}")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
