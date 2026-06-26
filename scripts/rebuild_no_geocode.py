"""
Rebuild parcels.geojson and source-files/building_level_data.csv from
source-files/Corridor_Thesis_Fieldwork_-_Enriched.xlsx WITHOUT calling the
Census geocoder.  Coordinates are reused from the existing parcels.geojson
(looked up by Parcel Address).

Run:  python scripts/rebuild_no_geocode.py

After this, run augment_building_fields.py and augment_missing_fields.py
as the full chain does.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from datetime import date, datetime
from pathlib import Path

import openpyxl

ROOT        = Path(__file__).resolve().parents[1]
XLSX        = ROOT / "source-files" / "Corridor_Thesis_Fieldwork_-_Enriched.xlsx"
SHEET       = "Building Level Data"
HEADER_ROW  = 2   # 1-indexed; row 1 is a blank/title row

CSV_OUT    = ROOT / "source-files" / "building_level_data.csv"
GEOJSON_OUT   = ROOT / "public" / "data" / "parcels.geojson"
BACKUP        = ROOT / "public" / "data" / "parcels.geojson.pre_rebuild.bak"
VACANCY_BAK   = ROOT / "public" / "data" / "parcels.geojson.vacancy.bak"
# Coordinate source: vacancy.bak is the most complete (519 features, pre-any-sync);
# fall back to pre_rebuild.bak, then the current file.
GEOJSON_IN = (
    VACANCY_BAK   if VACANCY_BAK.exists()  else
    (BACKUP       if BACKUP.exists()       else GEOJSON_OUT)
)


# ---------- helpers (mirror build_parcels.py) ----------

def clean_cell(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        s = v.strip()
        return s if s else None
    return v


def sale_year(v) -> int | None:
    if not v:
        return None
    try:
        return int(str(v)[:4])
    except (ValueError, TypeError):
        return None


def derive_vacancy_state(vacant, vacancy_type, operator_type) -> str:
    if vacancy_type == "Under Renovation":
        return "under_renovation"
    if vacancy_type == "Short-Term / Turnover":
        return "short_term"
    if vacancy_type == "Long-Term Vacancy":
        return "long_term"
    if vacancy_type == "Seasonal Closure":
        return "seasonal_closure"
    if vacant == "No" and not operator_type:
        return "non_commercial"
    if vacant == "No":
        return "active"
    return "long_term"


# ---------- 1. Load existing coordinates ----------

print(f"Loading coordinates from {GEOJSON_IN.name} ...")
with GEOJSON_IN.open(encoding="utf-8") as f:
    existing_gj = json.load(f)

# primary key: Parcel Address -> (lng, lat, match_type)
coord_by_addr: dict[str, tuple] = {}
coord_by_id: dict[int, tuple] = {}   # fallback for renamed addresses (Abbots Square)
for feat in existing_gj["features"]:
    addr = feat["properties"].get("address")
    pid = feat["properties"].get("id")
    lng, lat = feat["geometry"]["coordinates"]
    match_type = feat["properties"].get("geocode_match_type", "")
    if addr:
        coord_by_addr[addr] = (lng, lat, match_type, addr)
    if pid:
        coord_by_id[pid] = (lng, lat, match_type, addr)

print(f"  {len(coord_by_addr)} coordinates loaded by address, {len(coord_by_id)} by id")

# ---------- 2. Read xlsx ----------

print(f"\nReading {XLSX.name} ...")
wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)
ws = wb[SHEET]

rows = list(ws.iter_rows(values_only=True))
headers = list(rows[HEADER_ROW - 1])
data_rows = rows[HEADER_ROW:]
data_rows = [r for r in data_rows if any(c not in (None, "") for c in r)]

print(f"  {len(headers)} columns, {len(data_rows)} data rows")

H = {h: i for i, h in enumerate(headers) if h}

def field(row, name):
    idx = H.get(name)
    return clean_cell(row[idx]) if idx is not None else None


# ---------- 3. Build records ----------

records = []
for i, row in enumerate(data_rows, start=1):
    raw_addr = field(row, "Parcel Address")
    rec = {
        "id": i,
        "parcel_address": raw_addr,
        "corridor": field(row, "Corridor"),
        "block_number": field(row, "Block_Number"),
        "year_built": field(row, "Year Built"),
        "last_sale_date": field(row, "Last Sale Date"),
        "last_sale_price": field(row, "Last Sale Price"),
        "zone_type": field(row, "Zone Type"),
        "cultural_tenant": field(row, "Cultural Tenant"),
        "cultural_status": field(row, "Cultural Status"),
        "business_category": field(row, "Business Category"),
        "business_segment": field(row, "Business Segment"),
        "vacant": field(row, "Vacant"),
        "vacancy_type": field(row, "Vacancy Type"),
        "operator_type": field(row, "Operator Type"),
        "outdoor_footprint": field(row, "Outdoor Footprint"),
        "building_footprint": field(row, "Building Footprint"),
        "building_height": field(row, "Building Height"),
        "open_violations": field(row, "Open Violation Count"),
        "owner": field(row, "Owner"),
        "mailing_city_state": field(row, "Mailing City/State"),
        "opa_property_use": field(row, "OPA Property Use"),
        "out_of_area_owner": field(row, "Out-of-Area Owner"),
        "corporate_owner": field(row, "Corporate Owner"),
    }
    rec["vacancy_state"] = derive_vacancy_state(
        rec["vacant"], rec["vacancy_type"], rec["operator_type"]
    )
    rec["last_sale_year"] = sale_year(rec["last_sale_date"])
    records.append(rec)


# ---------- 4. Write building_level_data.csv ----------

CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(headers)
    for r in data_rows:
        w.writerow([clean_cell(c) for c in r])
print(f"\nWrote {CSV_OUT.relative_to(ROOT)} ({len(data_rows)} rows)")


# ---------- 5. Build GeoJSON (no geocoder) ----------

if GEOJSON_OUT.exists() and GEOJSON_OUT.resolve() != BACKUP.resolve():
    shutil.copy2(GEOJSON_OUT, BACKUP)
    print(f"Backup: {BACKUP.name}")
else:
    print(f"Backup already exists at {BACKUP.name} (coordinate source), skipping overwrite")

features = []
no_coord = []

for rec in records:
    addr = rec["parcel_address"]
    if not addr:
        no_coord.append((rec["id"], "no address"))
        continue
    hit = coord_by_addr.get(addr)
    resolved_addr = addr
    if not hit:
        # Fallback: address was renamed by a fix script (e.g. 200-210 LOMBARD -> South St)
        hit = coord_by_id.get(rec["id"])
        if not hit:
            no_coord.append((rec["id"], addr))
            continue
        print(f"  ID fallback: id={rec['id']} xlsx_addr={addr!r} -> gj_addr={hit[3]!r}")
        resolved_addr = hit[3]  # use the fixed address from the existing GeoJSON
    lng, lat, match_type, _ = hit

    props = {
        "id": rec["id"],
        "address": resolved_addr,
        "corridor": rec["corridor"],
        "vacancy_state": rec["vacancy_state"],
        "vacant": rec["vacant"],
        "vacancy_type": rec["vacancy_type"],
        "business_category": rec["business_category"],
        "business_segment": rec["business_segment"],
        "operator_type": rec["operator_type"],
        "outdoor_footprint": rec["outdoor_footprint"],
        "cultural_tenant": rec["cultural_tenant"],
        "cultural_status": rec["cultural_status"],
        "year_built": rec["year_built"],
        "zone_type": rec["zone_type"],
        "building_footprint": rec["building_footprint"],
        "building_height": rec["building_height"],
        "open_violations": rec["open_violations"],
        "last_sale_year": rec["last_sale_year"],
        "last_sale_price": rec["last_sale_price"],
        "owner": rec["owner"],
        "opa_property_use": rec["opa_property_use"],
        "out_of_area_owner": rec["out_of_area_owner"],
        "corporate_owner": rec["corporate_owner"],
        "geocode_match_type": match_type,
    }
    features.append({
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": props,
    })

geojson = {"type": "FeatureCollection", "features": features}
GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
with GEOJSON_OUT.open("w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, separators=(",", ":"))

state_counts = Counter(f["properties"]["vacancy_state"] for f in features)
size = GEOJSON_OUT.stat().st_size

print(f"\n{'='*60}")
print("REBUILD REPORT (no geocode)")
print(f"{'='*60}")
print(f"Total xlsx rows:          {len(records)}")
print(f"GeoJSON features written: {len(features)}")
if no_coord:
    print(f"Skipped (no coord match): {len(no_coord)}")
    for rid, reason in no_coord[:10]:
        print(f"  id={rid}  {reason}")
print(f"\nVacancy state breakdown:")
for state in ["active", "non_commercial", "short_term", "long_term", "under_renovation"]:
    print(f"  {state:<18} {state_counts.get(state, 0):>4}")
print(f"\nGeoJSON: {size:,} bytes ({size/1024:.1f} KB)")
print(f"{'='*60}")
