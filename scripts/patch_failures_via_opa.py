"""
Recover Census geocoding failures by looking up coordinates through Philadelphia's
public OPA properties dataset (Carto-hosted, authoritative city cadastre).

Reads:  source-files/geocoding_failures.csv
        source-files/building_level_data.csv
        src/data/parcels.geojson
Writes: src/data/parcels.geojson           (patched in place; backup written first)
        source-files/geocoding_failures.csv (rewritten with only true residual fails)

Run:  python scripts/patch_failures_via_opa.py
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
FAILURES = ROOT / "source-files" / "geocoding_failures.csv"
BLD_CSV = ROOT / "source-files" / "building_level_data.csv"
GEOJSON = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = GEOJSON.with_suffix(".geojson.bak")

CARTO_URL = "https://phl.carto.com/api/v2/sql"

# Bounding boxes for sanity check (per user spec)
SOUTH_LAT = (39.92, 39.94)
SOUTH_LNG = (-75.18, -75.14)


def derive_vacancy_state(vacant, vacancy_type, operator_type):
    if vacancy_type == "Under Renovation": return "under_renovation"
    if vacancy_type == "Short-Term / Turnover": return "short_term"
    if vacancy_type == "Long-Term Vacancy": return "long_term"
    if vacancy_type == "Seasonal Closure": return "seasonal_closure"
    if vacant == "No" and not operator_type: return "non_commercial"
    if vacant == "No": return "active"
    return "long_term"


def sale_year(v):
    if not v: return None
    try: return int(str(v)[:4])
    except (ValueError, TypeError): return None


def coerce(v):
    """Lift empty strings to None; pass through everything else."""
    if v is None: return None
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return v


# ---------- 1. Load failures and source data ----------

fails = list(csv.DictReader(open(FAILURES, encoding="utf-8")))
bld_rows = list(csv.DictReader(open(BLD_CSV, encoding="utf-8")))
geojson = json.load(open(GEOJSON, encoding="utf-8"))

print(f"Loaded {len(fails)} failures, {len(bld_rows)} parcel rows, "
      f"{len(geojson['features'])} existing features")

# parcel_id -> (opa_id, full bld row)
fail_records = []
for f in fails:
    pid = int(f["parcel_id"])
    bld = bld_rows[pid - 1]
    opa = bld.get("OPA Account ID") or ""
    fail_records.append({"parcel_id": pid, "opa_id": opa, "bld": bld, "fail": f})

opa_ids = [r["opa_id"] for r in fail_records if r["opa_id"]]
print(f"OPA IDs to query: {len(opa_ids)}")


# ---------- 2. Query Carto SQL ----------

# parcel_number is text in opa_properties_public; quote each id
sql = (
    "SELECT parcel_number, ST_Y(the_geom) AS lat, ST_X(the_geom) AS lng "
    "FROM opa_properties_public "
    f"WHERE parcel_number IN ({','.join(repr(x) for x in opa_ids)})"
)
print(f"POST {CARTO_URL}")
resp = requests.post(CARTO_URL, data={"q": sql}, timeout=60)
resp.raise_for_status()
payload = resp.json()
print(f"Carto returned {len(payload.get('rows', []))} rows")

# parcel_number -> (lat, lng); skip any null geometries
opa_coords = {}
opa_no_geom = []
for row in payload.get("rows", []):
    pn = row.get("parcel_number")
    lat = row.get("lat")
    lng = row.get("lng")
    if pn and lat is not None and lng is not None:
        opa_coords[pn] = (float(lat), float(lng))
    elif pn:
        opa_no_geom.append(pn)


# ---------- 3. Patch GeoJSON ----------

shutil.copy2(GEOJSON, BACKUP)
print(f"Backup written: {BACKUP.relative_to(ROOT)}")

recovered = []
residual_failures = []  # (parcel_id, opa_id, address, corridor, reason)
sanity_warnings = []

for rec in fail_records:
    pid = rec["parcel_id"]
    opa = rec["opa_id"]
    bld = rec["bld"]
    addr = bld.get("Parcel Address") or ""
    corridor = bld.get("Corridor") or ""

    if not opa:
        residual_failures.append((pid, opa, addr, corridor, "no_opa_id"))
        continue
    if opa not in opa_coords:
        reason = "opa_no_geom" if opa in opa_no_geom else "opa_not_found"
        residual_failures.append((pid, opa, addr, corridor, reason))
        continue

    lat, lng = opa_coords[opa]

    # Sanity check
    in_box = (SOUTH_LAT[0] <= lat <= SOUTH_LAT[1] and
              SOUTH_LNG[0] <= lng <= SOUTH_LNG[1])
    if not in_box:
        sanity_warnings.append((pid, addr, lat, lng))

    # Build feature
    vacancy_state = derive_vacancy_state(
        coerce(bld.get("Vacant")),
        coerce(bld.get("Vacancy Type")),
        coerce(bld.get("Operator Type")),
    )
    props = {
        "id": pid,
        "address": addr,
        "corridor": corridor,
        "vacancy_state": vacancy_state,
        "vacant": coerce(bld.get("Vacant")),
        "vacancy_type": coerce(bld.get("Vacancy Type")),
        "business_category": coerce(bld.get("Business Category")),
        "business_segment": coerce(bld.get("Business Segment")),
        "operator_type": coerce(bld.get("Operator Type")),
        "outdoor_footprint": coerce(bld.get("Outdoor Footprint")),
        "cultural_tenant": coerce(bld.get("Cultural Tenant")),
        "cultural_status": coerce(bld.get("Cultural Status")),
        "year_built": coerce(bld.get("Year Built")),
        "zone_type": coerce(bld.get("Zone Type")),
        "last_sale_year": sale_year(bld.get("Last Sale Date")),
        "last_sale_price": coerce(bld.get("Last Sale Price")),
        "owner": coerce(bld.get("Owner")),
        "opa_property_use": coerce(bld.get("OPA Property Use")),
        "out_of_area_owner": coerce(bld.get("Out-of-Area Owner")),
        "corporate_owner": coerce(bld.get("Corporate Owner")),
        "geocode_match_type": "OPA",
    }
    geojson["features"].append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": props,
    })
    recovered.append((pid, addr, lat, lng))

# Sort features by id so neighbors stay together (nice for debugging)
geojson["features"].sort(key=lambda f: f["properties"]["id"])

with GEOJSON.open("w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, separators=(",", ":"))


# ---------- 4. Rewrite failures CSV with only true residual fails ----------

with FAILURES.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["parcel_id", "xlsx_row", "parcel_address", "geocode_street",
                "corridor", "reason"])
    for pid, opa, addr, corridor, reason in residual_failures:
        bld = bld_rows[pid - 1]
        xlsx_row = pid + 2  # data row 1 == xlsx row 3
        w.writerow([pid, xlsx_row, addr, "", corridor, reason])


# ---------- 5. Report ----------

state_counts = Counter(f["properties"]["vacancy_state"] for f in geojson["features"])
size_bytes = GEOJSON.stat().st_size

print()
print("=" * 60)
print("PATCH REPORT")
print("=" * 60)
print(f"Failures input:          {len(fail_records)}")
print(f"Recovered via OPA:       {len(recovered)}")
print(f"Residual failures:       {len(residual_failures)}")
print(f"Sanity-bbox warnings:    {len(sanity_warnings)}")
print()
print(f"GeoJSON features (final): {len(geojson['features'])}")
print(f"GeoJSON file size:        {size_bytes:,} bytes ({size_bytes/1024:.1f} KB)")
print()
print("Vacancy state breakdown (final):")
for state in ["active", "non_commercial", "short_term", "long_term", "under_renovation"]:
    print(f"  {state:<18} {state_counts.get(state, 0):>4}")
print()

if recovered:
    lats = [r[2] for r in recovered]
    lngs = [r[3] for r in recovered]
    print("Recovered coordinate range:")
    print(f"  lat: {min(lats):.4f} - {max(lats):.4f}")
    print(f"  lng: {min(lngs):.4f} - {max(lngs):.4f}")
    print(f"Bounding-box target: lat [39.92, 39.94], lng [-75.18, -75.14]")
    print()
    print("First 5 recovered:")
    for pid, addr, lat, lng in recovered[:5]:
        print(f"  parcel {pid:>3}  {addr:<22}  lat={lat:.5f}  lng={lng:.5f}")

if sanity_warnings:
    print()
    print("!! Sanity warnings (outside SS bbox):")
    for pid, addr, lat, lng in sanity_warnings:
        print(f"  parcel {pid}  {addr}  lat={lat:.5f}  lng={lng:.5f}")

if residual_failures:
    print()
    print("Residual failures still needing attention:")
    for pid, opa, addr, corridor, reason in residual_failures:
        print(f"  parcel {pid}  OPA={opa!r}  {addr!r}  reason={reason}")

print("=" * 60)
