"""
Fix the three Abbots Square / South Street frontage parcels (id 177/178/179)
that incorrectly carry the "200-210 LOMBARD" range address in the source data.

Each row is a distinct commercial storefront on the South Street frontage:
    177  -> "249-289 SOUTH ST"   geocode target  "269 SOUTH ST"
    178  -> "239 SOUTH ST"       geocode target  "239 SOUTH ST"  (Rita's)
    179  -> "201-235 SOUTH ST"   geocode target  "221 SOUTH ST"  (former Laff House)

Strategy: try PHL OPA Carto first by `location =`; fall back to the Census
single-address geocoder when OPA has no record (Abbots Square's storefronts
share a master parcel; OPA only has the even-numbered south-side parcels in
this block, so the odd-numbered north-side targets fall through to Census).

Reads / writes:
    source-files/building_level_data.csv  (Parcel Address column updated for
                                           the three rows; backup written first)
    public/data/parcels.geojson           (address, coordinates, match_type
                                           updated for the three features)
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "source-files" / "building_level_data.csv"
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
CSV_BACKUP = ROOT / "source-files" / "building_level_data.csv.lombard.bak"
GJ_BACKUP = ROOT / "public" / "data" / "parcels.geojson.lombard.bak"

CARTO_URL = "https://phl.carto.com/api/v2/sql"
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

# parcel_id -> (display_address, geocode_target)
FIXES = {
    177: ("249-289 SOUTH ST", "269 SOUTH ST"),
    178: ("239 SOUTH ST", "239 SOUTH ST"),
    179: ("201-235 SOUTH ST", "221 SOUTH ST"),
}


def opa_geocode(addr: str) -> tuple[float, float, str] | None:
    """Returns (lat, lng, opa_parcel_number) or None."""
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


def census_geocode(addr: str) -> tuple[float, float] | None:
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
    return float(c["y"]), float(c["x"])  # y = lat, x = lng


# ---------- 1. Backup ----------
shutil.copy2(CSV_PATH, CSV_BACKUP)
shutil.copy2(GJ_PATH, GJ_BACKUP)
print(f"Backups: {CSV_BACKUP.name}, {GJ_BACKUP.name}")


# ---------- 2. Read CSV ----------
with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    csv_rows = list(reader)


# ---------- 3. Geocode each target and update CSV in memory ----------
results = {}  # pid -> dict with lat,lng,source,opa_pn,display,target

for pid, (display, target) in FIXES.items():
    row = csv_rows[pid - 1]
    old = row.get("Parcel Address")
    if old != "200-210 LOMBARD":
        print(f"!! parcel {pid}: expected 'Parcel Address' == '200-210 LOMBARD', got {old!r}; aborting")
        sys.exit(1)

    print(f"\nGeocoding parcel {pid}  target={target!r}  display={display!r}")
    hit = opa_geocode(target)
    if hit is not None:
        lat, lng, opa_pn = hit
        source = "Manual_OPA"
        print(f"  OPA match: ({lat:.5f}, {lng:.5f})  opa_parcel_number={opa_pn!r}")
    else:
        print(f"  OPA had no record for {target!r}; trying Census")
        c = census_geocode(target)
        if c is None:
            print(f"  !! Census also missed; aborting")
            sys.exit(1)
        lat, lng = c
        opa_pn = None
        source = "Manual_Census"
        print(f"  Census match: ({lat:.5f}, {lng:.5f})")

    results[pid] = {
        "lat": lat,
        "lng": lng,
        "source": source,
        "opa_pn": opa_pn,
        "display": display,
        "target": target,
    }
    row["Parcel Address"] = display


# ---------- 4. Write CSV ----------
with CSV_PATH.open("w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    for r in csv_rows:
        w.writerow(r)
print(f"\nCSV updated: {CSV_PATH.relative_to(ROOT)}")


# ---------- 5. Update GeoJSON ----------
gj = json.load(open(GJ_PATH, encoding="utf-8"))
features_by_id = {f["properties"]["id"]: f for f in gj["features"]}

for pid, r in results.items():
    feat = features_by_id[pid]
    feat["properties"]["address"] = r["display"]
    feat["geometry"]["coordinates"] = [r["lng"], r["lat"]]
    feat["properties"]["geocode_match_type"] = r["source"]

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# ---------- 6. Report ----------
print()
print("=" * 60)
print("FINAL — three parcels rewired")
print("=" * 60)
for pid, r in results.items():
    print(f"  parcel {pid}  display={r['display']!r}  target={r['target']!r}")
    print(f"             coords=({r['lat']:.5f}, {r['lng']:.5f})  source={r['source']}")
    if r["opa_pn"]:
        print(f"             opa_parcel_number={r['opa_pn']}")

# Confirm spatial ordering (east -> west since smaller addr numbers are east)
print()
print("Spatial ordering (east -> west):")
for pid in sorted(results.keys(), key=lambda p: results[p]["lng"], reverse=True):
    r = results[pid]
    print(f"  parcel {pid}  lng={r['lng']:.5f}  {r['display']}")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes ({size/1024:.1f} KB)")
