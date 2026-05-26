"""
Extracts Building Level Data from the fieldwork xlsx, geocodes addresses via
the U.S. Census batch geocoder, and writes:

  source-files/building_level_data.csv   flat single-header CSV of all parcels
  src/data/parcels.geojson               point features for the Leaflet map
  source-files/geocoding_failures.csv    addresses Census could not match

Run:  python scripts/build_parcels.py
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime, date
from pathlib import Path

import openpyxl
import requests

ROOT = Path(__file__).resolve().parents[1]
XLSX = ROOT / "source-files" / "Corridor_Thesis_Fieldwork_-_Enriched.xlsx"
SHEET = "Building Level Data"
HEADER_ROW = 2

CSV_OUT = ROOT / "source-files" / "building_level_data.csv"
GEOJSON_OUT = ROOT / "public" / "data" / "parcels.geojson"
FAILURES_OUT = ROOT / "source-files" / "geocoding_failures.csv"

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
CENSUS_BENCHMARK = "Public_AR_Current"
CENSUS_TIMEOUT = 600  # seconds

PHILLY_LAT = (39.85, 40.10)
PHILLY_LNG = (-75.30, -74.95)


# ---------- helpers ----------

def clean_cell(v):
    """Normalize a cell value: dates to ISO, empty strings to None, strip strings."""
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


def normalize_street_for_geocode(addr: str) -> str:
    """Collapse range addresses like '200-210 LOMBARD' to '200 LOMBARD'."""
    if not addr:
        return addr
    return re.sub(r"^(\d+)-\d+\s", r"\1 ", addr.strip())


def sale_year(v) -> int | None:
    if not v:
        return None
    # Already coerced to ISO date string by clean_cell
    try:
        return int(str(v)[:4])
    except (ValueError, TypeError):
        return None


def derive_vacancy_state(vacant: str | None, vacancy_type: str | None,
                         operator_type: str | None) -> str:
    if vacancy_type == "Under Renovation":
        return "under_renovation"
    if vacancy_type == "Short-Term / Turnover":
        return "short_term"
    if vacancy_type == "Long-Term Vacancy":
        return "long_term"
    if vacant == "No" and not operator_type:
        return "non_commercial"
    if vacant == "No":
        return "active"
    # Fallback: vacant=='Yes' with no vacancy type, treat as long_term-ish.
    # Should not occur given the audit, but be defensive.
    return "long_term"


# ---------- 1. Read xlsx ----------

print(f"Reading {XLSX.name} ...")
wb = openpyxl.load_workbook(XLSX, data_only=True, read_only=True)
ws = wb[SHEET]

rows = list(ws.iter_rows(values_only=True))
headers = list(rows[HEADER_ROW - 1])
data_rows = rows[HEADER_ROW:]
# Drop fully-empty trailing rows defensively
data_rows = [r for r in data_rows if any(c not in (None, "") for c in r)]

print(f"Headers: {len(headers)} columns, {len(data_rows)} data rows")

# Build header -> index map
H = {h: i for i, h in enumerate(headers) if h}


def field(row, name):
    idx = H.get(name)
    return clean_cell(row[idx]) if idx is not None else None


# ---------- 2. Build canonical CSV ----------

CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
with CSV_OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(headers)
    for r in data_rows:
        w.writerow([clean_cell(c) for c in r])
print(f"Wrote {CSV_OUT.relative_to(ROOT)} ({len(data_rows)} rows)")


# ---------- 3. Build geocode input ----------

records = []
geocode_csv_buf = io.StringIO()
gw = csv.writer(geocode_csv_buf)

for i, row in enumerate(data_rows, start=1):
    raw_addr = field(row, "Parcel Address")
    geocode_street = normalize_street_for_geocode(raw_addr) if raw_addr else None
    rec = {
        "id": i,
        "xlsx_row": HEADER_ROW + i,  # original spreadsheet row number
        "parcel_address": raw_addr,
        "geocode_street": geocode_street,
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

    # Census batch CSV: id,street,city,state,zip   (no header)
    if geocode_street:
        gw.writerow([i, geocode_street, "Philadelphia", "PA", ""])

geocode_payload = geocode_csv_buf.getvalue()
to_geocode = [r for r in records if r["geocode_street"]]
print(f"Prepared {len(to_geocode)} addresses for Census batch geocoder")


# ---------- 4. Submit to Census batch ----------

print(f"POST {CENSUS_URL} (benchmark={CENSUS_BENCHMARK}) ... this can take ~30-120s")
resp = requests.post(
    CENSUS_URL,
    files={"addressFile": ("addresses.csv", geocode_payload, "text/csv")},
    data={"benchmark": CENSUS_BENCHMARK},
    timeout=CENSUS_TIMEOUT,
)
resp.raise_for_status()
result_text = resp.text
print(f"Census returned {len(result_text):,} bytes")


# ---------- 5. Parse geocoder response ----------

# Response columns (no header):
#   id, input_address, match_indicator, match_type, matched_address,
#   coordinates (lng,lat), tigerline_id, side
geocoded = {}  # id -> (lng, lat, matched_address, match_type)
failures = []  # list of (id, reason)

reader = csv.reader(io.StringIO(result_text))
for row in reader:
    if not row:
        continue
    try:
        rid = int(row[0])
    except (ValueError, IndexError):
        continue
    match_indicator = row[2] if len(row) > 2 else ""
    if match_indicator == "Match" and len(row) > 5 and row[5]:
        # coordinates field is "lng,lat"
        try:
            lng_str, lat_str = row[5].split(",")
            lng = float(lng_str)
            lat = float(lat_str)
        except ValueError:
            failures.append((rid, f"unparseable coords: {row[5]!r}"))
            continue
        matched = row[4] if len(row) > 4 else ""
        match_type = row[3] if len(row) > 3 else ""
        geocoded[rid] = (lng, lat, matched, match_type)
    else:
        failures.append((rid, match_indicator or "No_Match"))


# ---------- 6. Build GeoJSON ----------

features = []
sanity_outside = []  # points returned outside Philly bbox
unaddressed = []  # records with no parcel address at all

for rec in records:
    rid = rec["id"]
    if not rec["geocode_street"]:
        unaddressed.append((rid, rec["xlsx_row"]))
        continue
    hit = geocoded.get(rid)
    if not hit:
        # ensure a failure row exists even if Census omitted it
        if not any(f[0] == rid for f in failures):
            failures.append((rid, "No_Response"))
        continue
    lng, lat, matched, match_type = hit
    if not (PHILLY_LAT[0] <= lat <= PHILLY_LAT[1] and PHILLY_LNG[0] <= lng <= PHILLY_LNG[1]):
        sanity_outside.append((rid, lat, lng))
        failures.append((rid, f"outside_philly_bbox lat={lat:.4f} lng={lng:.4f}"))
        continue

    props = {
        "id": rid,
        "address": rec["parcel_address"],
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


# ---------- 7. Write failures CSV ----------

# Resolve id -> record for richer failure detail
by_id = {r["id"]: r for r in records}
with FAILURES_OUT.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["parcel_id", "xlsx_row", "parcel_address", "geocode_street",
                "corridor", "reason"])
    # add purely-unaddressed
    for rid, xlsx_row in unaddressed:
        rec = by_id[rid]
        w.writerow([rid, xlsx_row, rec["parcel_address"], rec["geocode_street"],
                    rec["corridor"], "no_address_in_source"])
    for rid, reason in failures:
        rec = by_id.get(rid)
        if not rec:
            continue
        w.writerow([rid, rec["xlsx_row"], rec["parcel_address"],
                    rec["geocode_street"], rec["corridor"], reason])


# ---------- 8. Report ----------

state_counts = Counter(f["properties"]["vacancy_state"] for f in features)
size_bytes = GEOJSON_OUT.stat().st_size

print()
print("=" * 60)
print("BUILD REPORT")
print("=" * 60)
print(f"Total parcels processed:     {len(records)}")
print(f"  - with parcel address:     {len(to_geocode)}")
print(f"  - missing address:         {len(unaddressed)}")
print(f"Census submitted:            {len(to_geocode)}")
print(f"Census matched in Philly:    {len(features)}")
print(f"Geocoding failures:          {len(failures) + len(unaddressed)}")
print()
print(f"GeoJSON file size:           {size_bytes:,} bytes "
      f"({size_bytes / 1024:.1f} KB)")
print(f"GeoJSON path:                {GEOJSON_OUT.relative_to(ROOT)}")
print()
print("Vacancy state breakdown (mapped points only):")
for state in ["active", "non_commercial", "short_term", "long_term", "under_renovation"]:
    print(f"  {state:<18} {state_counts.get(state, 0):>4}")
print()

if features:
    lats = [f["geometry"]["coordinates"][1] for f in features]
    lngs = [f["geometry"]["coordinates"][0] for f in features]
    print("Coordinate sanity check (expect lat ~39.9, lng ~-75.1):")
    print(f"  lat: min={min(lats):.4f}  max={max(lats):.4f}  "
          f"avg={sum(lats)/len(lats):.4f}")
    print(f"  lng: min={min(lngs):.4f}  max={max(lngs):.4f}  "
          f"avg={sum(lngs)/len(lngs):.4f}")

if failures or unaddressed:
    print()
    print(f"Failures written to {FAILURES_OUT.relative_to(ROOT)} "
          f"({len(failures) + len(unaddressed)} rows)")
    print("First 15 failures:")
    shown = 0
    for rid, xlsx_row in unaddressed:
        rec = by_id[rid]
        print(f"  row {xlsx_row:>3}  [{rec['corridor']}]  "
              f"<no address>   reason=no_address_in_source")
        shown += 1
        if shown >= 15:
            break
    for rid, reason in failures:
        if shown >= 15:
            break
        rec = by_id.get(rid)
        if not rec:
            continue
        print(f"  row {rec['xlsx_row']:>3}  [{rec['corridor']}]  "
              f"{rec['parcel_address']!r:<35}  reason={reason}")
        shown += 1

print("=" * 60)
