"""
Fetch South Street and East Passyunk Avenue centerlines from OpenStreetMap
via the Overpass API, scoped to the bounding box of the geocoded parcels.

Writes: src/data/streets.geojson
        (FeatureCollection of two MultiLineString features)

Run:  python scripts/fetch_street_centerlines.py
"""

from __future__ import annotations

import json
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
PARCELS = ROOT / "public" / "data" / "parcels.geojson"
OUT = ROOT / "public" / "data" / "streets.geojson"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Names exactly as tagged in OSM for Philly
STREETS = [
    ("South Street", "south_street"),
    ("East Passyunk Avenue", "east_passyunk"),
]


# ---------- 1. Compute bbox from parcels with a small pad ----------

gj = json.load(open(PARCELS, encoding="utf-8"))
lats = [f["geometry"]["coordinates"][1] for f in gj["features"]]
lngs = [f["geometry"]["coordinates"][0] for f in gj["features"]]
PAD = 0.01  # ~1.1 km — give the street ways some room
south = min(lats) - PAD
north = max(lats) + PAD
west = min(lngs) - PAD
east = max(lngs) + PAD
bbox = f"{south:.4f},{west:.4f},{north:.4f},{east:.4f}"
print(f"Parcel bbox + pad: {bbox}")


# ---------- 2. Build Overpass query ----------

name_clauses = "\n".join(
    f'  way["name"="{name}"]["highway"]({bbox});'
    for name, _ in STREETS
)
query = f"""
[out:json][timeout:60];
(
{name_clauses}
);
out geom;
"""

print("POST Overpass query ...")
headers = {"User-Agent": "saving-south-street-site/1.0 (urban planning thesis project; contact via github)"}
resp = requests.post(OVERPASS_URL, data={"data": query}, headers=headers, timeout=90)
resp.raise_for_status()
data = resp.json()
elements = data.get("elements", [])
print(f"Overpass returned {len(elements)} ways")


# ---------- 3. Group ways by street name ----------

by_name = {name: [] for name, _ in STREETS}
for el in elements:
    if el.get("type") != "way":
        continue
    name = el.get("tags", {}).get("name")
    if name not in by_name:
        continue
    geom = el.get("geometry") or []
    coords = [[pt["lon"], pt["lat"]] for pt in geom]
    if len(coords) >= 2:
        by_name[name].append(coords)


# ---------- 4. Build GeoJSON ----------

features = []
for name, key in STREETS:
    lines = by_name.get(name, [])
    print(f"  {name}: {len(lines)} way(s)")
    if not lines:
        continue
    features.append({
        "type": "Feature",
        "geometry": {"type": "MultiLineString", "coordinates": lines},
        "properties": {"name": name, "corridor": key},
    })

out_gj = {"type": "FeatureCollection", "features": features}
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", encoding="utf-8") as f:
    json.dump(out_gj, f, ensure_ascii=False, separators=(",", ":"))

size = OUT.stat().st_size
print()
print(f"Wrote {OUT.relative_to(ROOT)} ({size:,} bytes, {size/1024:.1f} KB)")

# Quick sanity: lat/lng envelope of all street coords
all_pts = [pt for f in features for line in f["geometry"]["coordinates"] for pt in line]
if all_pts:
    plats = [p[1] for p in all_pts]
    plngs = [p[0] for p in all_pts]
    print(f"Centerline envelope: lat [{min(plats):.4f}, {max(plats):.4f}]  "
          f"lng [{min(plngs):.4f}, {max(plngs):.4f}]")
    print(f"Total vertex count: {len(all_pts)}")
