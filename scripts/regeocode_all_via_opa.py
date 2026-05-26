"""
Re-geocode all 519 parcels using Philadelphia's authoritative OPA cadastre.

Replaces Census-derived block-face-interpolated coordinates with parcel-level
coordinates from PHL's OPA properties dataset (Carto-hosted).

Reads:  source-files/building_level_data.csv     (for OPA Account IDs)
        public/data/parcels.geojson              (for properties to preserve and
                                                  fallback coords for non-OPA hits)
Writes: public/data/parcels.geojson              (overwritten in place)
        public/data/parcels.geojson.census.bak   (backup of pre-refresh data)

Run:  python scripts/regeocode_all_via_opa.py
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "source-files" / "building_level_data.csv"
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = ROOT / "public" / "data" / "parcels.geojson.census.bak"

CARTO_URL = "https://phl.carto.com/api/v2/sql"

# South Philly corridor envelope tolerance (loose — just sanity bounds)
LAT_OK = (39.90, 39.96)
LNG_OK = (-75.20, -75.13)


# ---------- 1. Load source data ----------

csv_rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
gj = json.load(open(GJ_PATH, encoding="utf-8"))

print(f"Loaded {len(csv_rows)} CSV rows, {len(gj['features'])} existing features")

# parcel_id (1-based) -> OPA Account ID
pid_to_opa: dict[int, str] = {}
for i, row in enumerate(csv_rows, start=1):
    opa = (row.get("OPA Account ID") or "").strip()
    if opa:
        pid_to_opa[i] = opa

opa_ids = sorted(set(pid_to_opa.values()))
print(f"Unique OPA IDs to query: {len(opa_ids)} (of {len(pid_to_opa)} parcels with an OPA ID)")


# ---------- 2. Query Carto ----------

sql = (
    "SELECT parcel_number, ST_Y(the_geom) AS lat, ST_X(the_geom) AS lng "
    "FROM opa_properties_public "
    f"WHERE parcel_number IN ({','.join(repr(x) for x in opa_ids)})"
)
print(f"POST {CARTO_URL}  (query length {len(sql):,} chars)")
resp = requests.post(CARTO_URL, data={"q": sql}, timeout=120)
resp.raise_for_status()
payload = resp.json()
rows = payload.get("rows", [])
print(f"Carto returned {len(rows):,} rows")

opa_coords: dict[str, tuple[float, float]] = {}
opa_no_geom: list[str] = []
for r in rows:
    pn = r.get("parcel_number")
    lat = r.get("lat")
    lng = r.get("lng")
    if pn and lat is not None and lng is not None:
        opa_coords[pn] = (float(lat), float(lng))
    elif pn:
        opa_no_geom.append(pn)

print(f"OPA records with geometry:    {len(opa_coords):,}")
print(f"OPA records with NULL geom:   {len(opa_no_geom)}")
print(f"OPA IDs not found in dataset: "
      f"{len(set(opa_ids) - set(opa_coords) - set(opa_no_geom))}")


# ---------- 3. Backup ----------

shutil.copy2(GJ_PATH, BACKUP)
print(f"Backup written: {BACKUP.relative_to(ROOT)}")


# ---------- 4. Update features in place ----------

updated = 0
fallback = []  # list of (parcel_id, opa_id, address, reason)
sanity_oob = []

for feat in gj["features"]:
    props = feat["properties"]
    pid = props["id"]
    addr = props.get("address") or ""
    opa = pid_to_opa.get(pid)

    coords = opa_coords.get(opa) if opa else None
    if coords:
        lat, lng = coords
        if not (LAT_OK[0] <= lat <= LAT_OK[1] and LNG_OK[0] <= lng <= LNG_OK[1]):
            sanity_oob.append((pid, addr, lat, lng))
        feat["geometry"]["coordinates"] = [lng, lat]
        props["geocode_match_type"] = "OPA"
        updated += 1
    else:
        if not opa:
            reason = "no_opa_id_in_source"
        elif opa in opa_no_geom:
            reason = "opa_no_geom"
        else:
            reason = "opa_not_found"
        fallback.append((pid, opa, addr, reason))
        props["geocode_match_type"] = "Census_fallback"


# ---------- 5. Write ----------

with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# ---------- 6. Report and sanity checks ----------

size_bytes = GJ_PATH.stat().st_size
all_lats = [f["geometry"]["coordinates"][1] for f in gj["features"]]
all_lngs = [f["geometry"]["coordinates"][0] for f in gj["features"]]

print()
print("=" * 60)
print("RE-GEOCODE REPORT")
print("=" * 60)
print(f"Total parcels:                 {len(gj['features'])}")
print(f"Successfully refreshed via OPA: {updated}")
print(f"Fell back to prior coords:     {len(fallback)}")
print(f"Out-of-envelope warnings:      {len(sanity_oob)}")
print()
print(f"GeoJSON file size:             {size_bytes:,} bytes ({size_bytes/1024:.1f} KB)")
print()
print("New coordinate envelope:")
print(f"  lat: [{min(all_lats):.5f}, {max(all_lats):.5f}]  "
      f"avg={sum(all_lats)/len(all_lats):.5f}")
print(f"  lng: [{min(all_lngs):.5f}, {max(all_lngs):.5f}]  "
      f"avg={sum(all_lngs)/len(all_lngs):.5f}")

# Spot check 1: 300 block of South Street
by_addr = {f["properties"]["address"]: f for f in gj["features"]}
three_hundred = [f for f in gj["features"]
                 if (f["properties"]["address"] or "").startswith(
                     ("300", "301", "302", "303", "304", "305", "306", "307",
                      "308", "309", "310", "311", "312", "313", "314", "315",
                      "316", "317", "318", "319", "320", "321", "322", "323",
                      "324", "325", "326", "327", "328", "329", "330", "331",
                      "332", "333", "334", "335", "336", "337", "338", "339",
                      "340", "341", "342", "343", "344", "345", "346", "347",
                      "348", "349"))
                 and "SOUTH ST" in (f["properties"]["address"] or "")]
print()
print(f"Spot check 1 — 300 block of South Street: {len(three_hundred)} parcels")
unique_pts_300 = {tuple(f["geometry"]["coordinates"]) for f in three_hundred}
print(f"  distinct (lng,lat) tuples on 300 block: {len(unique_pts_300)}")
if three_hundred:
    lats_300 = [f["geometry"]["coordinates"][1] for f in three_hundred]
    lngs_300 = [f["geometry"]["coordinates"][0] for f in three_hundred]
    print(f"  300 block lat spread: {max(lats_300)-min(lats_300):.5f} "
          f"({(max(lats_300)-min(lats_300))*111000:.0f} m)")
    print(f"  300 block lng spread: {max(lngs_300)-min(lngs_300):.5f} "
          f"({(max(lngs_300)-min(lngs_300))*85000:.0f} m east-west)")
    print(f"  first 5 addrs:")
    for f in sorted(three_hundred, key=lambda x: x["properties"]["address"])[:5]:
        c = f["geometry"]["coordinates"]
        print(f"    {f['properties']['address']:<22} ({c[1]:.5f}, {c[0]:.5f})")

# Spot check 2: Tattooed Mom @ 530 SOUTH ST
print()
print("Spot check 2 — Tattooed Mom (530 SOUTH ST):")
t = by_addr.get("530 SOUTH ST")
if t:
    c = t["geometry"]["coordinates"]
    print(f"  ({c[1]:.5f}, {c[0]:.5f})  match_type={t['properties'].get('geocode_match_type')}")
    print(f"  cultural_tenant={t['properties'].get('cultural_tenant')!r}")
else:
    print("  !! 530 SOUTH ST not in dataset")

# Spot check 3: Magic Gardens (look up by cultural tenant tag since address might be a range)
print()
print("Spot check 3 — Magic Gardens (by cultural_tenant tag):")
mg = [f for f in gj["features"]
      if (f["properties"].get("cultural_tenant") or "") == "Magic Gardens"]
for f in mg:
    c = f["geometry"]["coordinates"]
    print(f"  {f['properties']['address']:<22} ({c[1]:.5f}, {c[0]:.5f})  "
          f"match_type={f['properties'].get('geocode_match_type')}")

if fallback:
    print()
    print("Fallback parcels (preserved prior coords):")
    for pid, opa, addr, reason in fallback:
        print(f"  parcel {pid:>3}  OPA={opa!r}  {addr!r}  reason={reason}")

if sanity_oob:
    print()
    print("!! Out-of-envelope warnings:")
    for pid, addr, lat, lng in sanity_oob:
        print(f"  parcel {pid}  {addr}  lat={lat:.5f}  lng={lng:.5f}")

print("=" * 60)
