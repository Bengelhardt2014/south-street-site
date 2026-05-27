"""
Pull ten additional parcel-level fields from source-files/building_level_data.csv
into public/data/parcels.geojson so the Day 3 filter sidebar has the full
property set to bind against.

Reads:  source-files/building_level_data.csv   (canonical CSV)
        public/data/parcels.geojson            (read-modify-write)
Writes: public/data/parcels.geojson            (overwritten; backup first)

Fields added (GeoJSON name <- CSV column):
    block_number             <- Block_Number             (int)
    years_since_last_sale    <- Years Since Last Sale    (float)
    lot_area                 <- Lot Area                 (int, sqft)
    frontage                 <- Frontage                 (int, ft)
    storefront_condition     <- Storefront Condition Score (int 1-5)
    structural_condition     <- Structural Condition Score (int 1-5)
    consumer_price_level     <- Consumer Price Level     (int)
    peak_activation_period   <- Peak Activation Period   (int OR str "6 N/A")
    mailing_city_state       <- Mailing City/State       (str)
    last_sale_date           <- Last Sale Date           (ISO date str)

Idempotent: rerunning overwrites the same ten keys, no other props touched.
"""

from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "source-files" / "building_level_data.csv"
GJ_PATH = ROOT / "public" / "data" / "parcels.geojson"
BACKUP = ROOT / "public" / "data" / "parcels.geojson.preaug.bak"


# (gj_key, csv_column, parser_tag)
FIELDS = [
    ("block_number",            "Block_Number",                 "int"),
    ("years_since_last_sale",   "Years Since Last Sale",        "float"),
    ("lot_area",                "Lot Area",                     "int"),
    ("frontage",                "Frontage",                     "int"),
    ("storefront_condition",    "Storefront Condition Score",   "int"),
    ("structural_condition",    "Structural Condition Score",   "int"),
    ("consumer_price_level",    "Consumer Price Level",         "int"),
    ("peak_activation_period",  "Peak Activation Period",       "int_or_str"),
    ("mailing_city_state",      "Mailing City/State",           "str"),
    ("last_sale_date",          "Last Sale Date",               "str"),
]


def parse_int(v):
    if v is None: return None
    s = str(v).strip()
    if not s: return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def parse_float(v):
    if v is None: return None
    s = str(v).strip()
    if not s: return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def parse_int_or_str(v):
    """Peak Activation Period: int when value cleanly parses, else null.
    The '6 N/A' sentinel means 'not applicable' (vacant / non-commercial parcels)
    and should be treated as missing for filter purposes."""
    if v is None: return None
    s = str(v).strip()
    if not s: return None
    if "N/A" in s.upper(): return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def parse_str(v):
    """String fields with dash placeholders ('-') treated as null."""
    if v is None: return None
    s = str(v).strip()
    if not s or s == "-": return None
    return s


PARSERS = {
    "int": parse_int,
    "float": parse_float,
    "int_or_str": parse_int_or_str,
    "str": parse_str,
}


# ---------- Backup ----------
shutil.copy2(GJ_PATH, BACKUP)
print(f"Backup: {BACKUP.name}\n")


# ---------- Load ----------
csv_rows = list(csv.DictReader(open(CSV_PATH, encoding="utf-8")))
gj = json.load(open(GJ_PATH, encoding="utf-8"))
by_pid = {i + 1: r for i, r in enumerate(csv_rows)}

print(f"Loaded {len(csv_rows)} CSV rows, {len(gj['features'])} GeoJSON features\n")


# ---------- Augment ----------
missing_counts = Counter()
updated = 0
for feat in gj["features"]:
    pid = feat["properties"]["id"]
    r = by_pid.get(pid)
    if not r:
        continue
    for gj_key, csv_col, tag in FIELDS:
        raw = r.get(csv_col)
        parser = PARSERS[tag]
        val = parser(raw)
        feat["properties"][gj_key] = val
        if val is None or val == "":
            missing_counts[gj_key] += 1
    updated += 1


# ---------- Write ----------
with GJ_PATH.open("w", encoding="utf-8") as f:
    json.dump(gj, f, ensure_ascii=False, separators=(",", ":"))


# ---------- Report ----------
print(f"Augmented {updated} features\n")

# Confirm all 10 fields are present in every feature
keys_present = set()
for f in gj["features"]:
    keys_present.update(f["properties"].keys())
for gj_key, _, _ in FIELDS:
    mark = "OK" if gj_key in keys_present else "MISSING"
    print(f"  [{mark}]  {gj_key}")

# Per-field missing counts (where field value is None/blank in source)
print(f"\nMissing-value counts per new field (out of {updated} parcels):")
total = updated
for gj_key, _, _ in FIELDS:
    n = missing_counts[gj_key]
    pct = (n / total) * 100 if total else 0
    print(f"  {gj_key:<28} {n:>4} parcels missing  ({pct:5.1f}%)")

# Spot-check the three former 200-210 LOMBARD parcels (now Abbots Square frontage)
print(f"\nSpot-check Abbots Square parcels (formerly 200-210 LOMBARD):")
for pid in (177, 178, 179):
    feat = next((f for f in gj["features"] if f["properties"]["id"] == pid), None)
    if not feat:
        continue
    p = feat["properties"]
    print(f"\n  parcel {pid}: address={p['address']!r}  vacancy_state={p['vacancy_state']!r}")
    for gj_key, _, _ in FIELDS:
        print(f"    {gj_key:<28} {p[gj_key]!r}")

size = GJ_PATH.stat().st_size
print(f"\nGeoJSON: {size:,} bytes ({size/1024:.1f} KB)")
