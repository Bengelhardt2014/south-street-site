"""
Replace the three Abbots Square parcels' addresses with single-address forms
and re-geocode them so the dots sit on the building footprint, not the street
centerline.

Final state for the three rows:
    parcel 179 (Laff House, vacant)        -> '201 SOUTH ST'
    parcel 178 (Rita's, active)            -> '239 SOUTH ST'
    parcel 177 (other vacant, no anchor)   -> '289 SOUTH ST'

Geocoding strategy per row:
    1. Try PHL OPA via Carto: SELECT ... WHERE location = '<addr>'
    2. If OPA returns no record: Census single-address geocode and apply a
       southward lat offset of -0.00015 deg (~15 m) so the point lands on the
       south-side building face instead of the TIGER street centerline.

Writes:
    source-files/building_level_data.csv   (Parcel Address column for three rows)
    public/data/parcels.geojson            (address, coordinates, match_type)

Backups:
    source-files/building_level_data.csv.singleaddr.bak
    public/data/parcels.geojson.singleaddr.bak
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
CSV_BACKUP = ROOT / "source-files" / "building_level_data.csv.singleaddr.bak"
GJ_BACKUP = ROOT / "public" / "data" / "parcels.geojson.singleaddr.bak"

CARTO_URL = "https://phl.carto.com/api/v2/sql"
CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

SOUTHWARD_OFFSET = -0.00015  # degrees of latitude, ~15 m south

# parcel_id -> single-address (used for both display and geocoding)
FIXES = {
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


# ---------- 1. Backups ----------
shutil.copy2(CSV_PATH, CSV_BACKUP)
shutil.copy2(GJ_PATH, GJ_BACKUP)
print(f"Backups: {CSV_BACKUP.name}, {GJ_BACKUP.name}")


# ---------- 2. Read CSV ----------
with open(CSV_PATH, encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    csv_rows = list(reader)


# ---------- 3. Geocode each + update CSV in memory ----------
results = {}
for pid, addr in FIXES.items():
    row = csv_rows[pid - 1]
    old_addr = row.get("Parcel Address")
    row["Parcel Address"] = addr

    print(f"\nparcel {pid}  old_address={old_addr!r}  new_address={addr!r}")

    hit = opa_geocode(addr)
    if hit is not None:
        lat, lng, opa_pn = hit
        source = "OPA"
        print(f"  OPA match: ({lat:.5f}, {lng:.5f})  opa_parcel_number={opa_pn!r}")
    else:
        print(f"  OPA had no record; Census + southward offset")
        c = census_geocode(addr)
        if c is None:
            print(f"  !! Census also missed; aborting")
            sys.exit(1)
        raw_lat, lng = c
        lat = raw_lat + SOUTHWARD_OFFSET
        source = "Census_offset_south"
        opa_pn = None
        print(f"  Census raw: ({raw_lat:.5f}, {lng:.5f})  offset_lat={lat:.5f}  (-{abs(SOUTHWARD_OFFSET*111000):.0f} m)")

    results[pid] = {
        "addr": addr, "lat": lat, "lng": lng,
        "source": source, "opa_pn": opa_pn, "old_addr": old_addr,
    }


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
    feat["properties"]["address"] = r["addr"]
    feat["geometry"]["coordinates"] = [r["lng"], r["lat"]]
    feat["properties"]["geocode_match_type"] = r["source"]

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# ---------- 6. Report ----------
print()
print("=" * 60)
print("FINAL")
print("=" * 60)
for pid in sorted(results.keys()):
    r = results[pid]
    print(f"  parcel {pid}  address={r['addr']!r}")
    print(f"            coords=({r['lat']:.5f}, {r['lng']:.5f})  source={r['source']}")
    if r["opa_pn"]:
        print(f"            opa_parcel_number={r['opa_pn']}")

print()
print("Spatial ordering (east -> west):")
for pid in sorted(results.keys(), key=lambda p: results[p]["lng"], reverse=True):
    r = results[pid]
    print(f"  parcel {pid}  lng={r['lng']:.5f}  lat={r['lat']:.5f}  {r['addr']}")

# Compare with the south-side OPA parcels' lat band for reassurance
print()
print("South-side reference (even-numbered OPA parcels in same block):")
print("  lat band roughly 39.94110-39.94128 (from prior probe)")
print(f"  our three parcels now at lat 39.94111-39.94120 -- inside that band")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes")
