"""
Clip South Street and East Passyunk centerlines in streets.geojson so they
only extend across the longitudinal/spatial range of the parcels in
parcels.geojson, with a small buffer.

South Street: clip by longitude range only (street is east-west).
East Passyunk: clip by 2D bounding box (street runs diagonally).

Buffer: ~10 m (0.0001 deg lat/lng) on each side per user spec.

Re-emits public/data/streets.geojson with clipped MultiLineString geometries.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from shapely.geometry import LineString, MultiLineString, box, mapping, shape

ROOT = Path(__file__).resolve().parents[1]
PARCELS = ROOT / "public" / "data" / "parcels.geojson"
STREETS = ROOT / "public" / "data" / "streets.geojson"
BACKUP = ROOT / "public" / "data" / "streets.geojson.unclipped.bak"

BUFFER_DEG = 0.0001  # ~10 m at this latitude


def parcel_bbox(features):
    """Return (lat_min, lat_max, lng_min, lng_max) plus endpoint feature refs."""
    lats = []
    lngs = []
    by_lat = {"min": None, "max": None}
    by_lng = {"min": None, "max": None}
    for f in features:
        lng, lat = f["geometry"]["coordinates"]
        lats.append(lat)
        lngs.append(lng)
        if by_lat["min"] is None or lat < by_lat["min"][0]:
            by_lat["min"] = (lat, f)
        if by_lat["max"] is None or lat > by_lat["max"][0]:
            by_lat["max"] = (lat, f)
        if by_lng["min"] is None or lng < by_lng["min"][0]:
            by_lng["min"] = (lng, f)
        if by_lng["max"] is None or lng > by_lng["max"][0]:
            by_lng["max"] = (lng, f)
    return (min(lats), max(lats), min(lngs), max(lngs), by_lat, by_lng)


def clip_mls(feature, clip_box):
    """Clip a LineString/MultiLineString GeoJSON geometry to a shapely box.
    Returns the new geometry dict (always a MultiLineString)."""
    mls = shape(feature["geometry"])
    clipped = mls.intersection(clip_box)

    if clipped.is_empty:
        return {"type": "MultiLineString", "coordinates": []}

    if clipped.geom_type == "LineString":
        lines = [list(clipped.coords)]
    elif clipped.geom_type == "MultiLineString":
        lines = [list(g.coords) for g in clipped.geoms]
    else:
        # GeometryCollection — extract any LineStrings
        lines = []
        for g in clipped.geoms:
            if g.geom_type == "LineString":
                lines.append(list(g.coords))
            elif g.geom_type == "MultiLineString":
                lines.extend(list(sub.coords) for sub in g.geoms)
    return {"type": "MultiLineString", "coordinates": lines}


# ---------- Load ----------
parcels = json.load(open(PARCELS, encoding="utf-8"))
streets = json.load(open(STREETS, encoding="utf-8"))

shutil.copy2(STREETS, BACKUP)
print(f"Backup: {BACKUP.name}\n")

south_parcels = [f for f in parcels["features"]
                 if f["properties"].get("corridor") == "South Street"]
ep_parcels = [f for f in parcels["features"]
              if f["properties"].get("corridor") == "East Passyunk"]
print(f"Parcel counts: South Street {len(south_parcels)}, East Passyunk {len(ep_parcels)}\n")


# ---------- South Street: clip by longitude only ----------
ss_lat_min, ss_lat_max, ss_lng_min, ss_lng_max, _, ss_by_lng = parcel_bbox(south_parcels)
ss_west_lat, ss_west_feat = ss_by_lng["min"][0], ss_by_lng["min"][1]
ss_east_lat, ss_east_feat = ss_by_lng["max"][0], ss_by_lng["max"][1]
ss_west_addr = ss_west_feat["properties"]["address"]
ss_east_addr = ss_east_feat["properties"]["address"]

# In Philly's lng convention: more negative = west, less negative = east
# So lng_min (most negative) = westernmost, lng_max (least negative) = easternmost
ss_lng_min_clip = ss_lng_min - BUFFER_DEG
ss_lng_max_clip = ss_lng_max + BUFFER_DEG
ss_box = box(ss_lng_min_clip, ss_lat_min - 0.005, ss_lng_max_clip, ss_lat_max + 0.005)
# (Generous lat padding — we don't want to clip on lat for South Street)

print("South Street clip range:")
print(f"  Westernmost parcel (min lng):  {ss_west_addr:<22}  lng={ss_west_lat:.5f}")
print(f"  Easternmost parcel (max lng):  {ss_east_addr:<22}  lng={ss_east_lat:.5f}")
print(f"  Clip lng range with +/-{BUFFER_DEG} buffer:")
print(f"    [{ss_lng_min_clip:.5f}, {ss_lng_max_clip:.5f}]")


# ---------- East Passyunk: clip by full bbox ----------
ep_lat_min, ep_lat_max, ep_lng_min, ep_lng_max, ep_by_lat, ep_by_lng = parcel_bbox(ep_parcels)
ep_box = box(
    ep_lng_min - BUFFER_DEG, ep_lat_min - BUFFER_DEG,
    ep_lng_max + BUFFER_DEG, ep_lat_max + BUFFER_DEG,
)

print("\nEast Passyunk clip bbox:")
print(f"  Northernmost parcel (max lat): "
      f"{ep_by_lat['max'][1]['properties']['address']:<22}  "
      f"lat={ep_by_lat['max'][0]:.5f}")
print(f"  Southernmost parcel (min lat): "
      f"{ep_by_lat['min'][1]['properties']['address']:<22}  "
      f"lat={ep_by_lat['min'][0]:.5f}")
print(f"  Easternmost parcel (max lng):  "
      f"{ep_by_lng['max'][1]['properties']['address']:<22}  "
      f"lng={ep_by_lng['max'][0]:.5f}")
print(f"  Westernmost parcel (min lng):  "
      f"{ep_by_lng['min'][1]['properties']['address']:<22}  "
      f"lng={ep_by_lng['min'][0]:.5f}")
print(f"  Clip bbox with +/-{BUFFER_DEG} buffer:")
print(f"    lng [{ep_lng_min - BUFFER_DEG:.5f}, {ep_lng_max + BUFFER_DEG:.5f}]")
print(f"    lat [{ep_lat_min - BUFFER_DEG:.5f}, {ep_lat_max + BUFFER_DEG:.5f}]")


# ---------- Apply clipping ----------
for feat in streets["features"]:
    name = feat["properties"].get("name")
    if name == "South Street":
        clipping_box = ss_box
    elif name == "East Passyunk Avenue":
        clipping_box = ep_box
    else:
        continue

    before = shape(feat["geometry"])
    new_geom = clip_mls(feat, clipping_box)
    after = shape(new_geom) if new_geom["coordinates"] else None

    before_segs = (
        len(before.geoms) if before.geom_type == "MultiLineString" else 1
    )
    after_segs = len(new_geom["coordinates"])
    before_verts = sum(len(list(g.coords)) for g in (
        before.geoms if before.geom_type == "MultiLineString" else [before]
    ))
    after_verts = sum(len(c) for c in new_geom["coordinates"])

    print(f"\n{name}:")
    print(f"  segments {before_segs} -> {after_segs}")
    print(f"  vertices {before_verts} -> {after_verts}")
    if after is not None and not after.is_empty:
        # Compute total length in meters for context (rough — degrees * factor)
        # using haversine would be more accurate but factor is OK
        try:
            total_m = after.length * 100000  # very rough
            print(f"  approx length: {total_m:.0f} m (rough degrees-to-meters)")
        except Exception:
            pass

    feat["geometry"] = new_geom


# ---------- Write ----------
with STREETS.open("w", encoding="utf-8") as f:
    json.dump(streets, f, ensure_ascii=False, separators=(",", ":"))

size = STREETS.stat().st_size
print(f"\nWrote {STREETS.relative_to(ROOT)}: {size:,} bytes")
