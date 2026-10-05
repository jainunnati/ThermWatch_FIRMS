"""
ENRICH: industrial facility + forest/land-cover context
---------------------------------------------------------------------------
FIRMS only tells us "something hot happened here". This module adds the
geographic context needed to make a sensible prototype classification:

  1. Industrial facilities - pulled from OpenStreetMap via the Overpass API
     (landuse=industrial, man_made=works, power=plant, industrial=* tags).
  2. Forest/natural land - pulled the same way (natural=wood, landuse=forest)
     and reduced to a set of representative centroids.

Both are cached to disk under data-pipeline/raw/ so the pipeline can be
re-run without hammering the public Overpass endpoint, and so it still works
offline once you've fetched once.

This is intentionally a simple point-proximity model, not a real GIS
polygon/point-in-polygon system - documented clearly per the "keep it
prototype-sized" instruction. It is enough to distinguish "near known
industry" from "near known forest" from "neither", which is exactly what
the classification step needs.
---------------------------------------------------------------------------
"""

import json
import math
import time

import requests

import config

FACILITIES_CACHE = config.RAW_DIR / "facilities_osm.json"
FOREST_CACHE = config.RAW_DIR / "forest_osm.json"

# Human-readable facility type per OSM tag, matching the frontend's existing
# FACILITY_TYPES vocabulary where possible.
TAG_TO_TYPE = {
    ("man_made", "works"): "Industrial Works",
    ("landuse", "industrial"): "Industrial Area",
    ("power", "plant"): "Thermal Power Plant",
    ("industrial", "refinery"): "Refinery",
    ("industrial", "oil"): "Refinery",
    ("man_made", "petroleum_well"): "Petrochemical Facility",
    ("industrial", "mine") : "Mining Area",
    ("landuse", "quarry"): "Mining Area",
}


def _haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _bbox_to_overpass(bbox_str):
    """config bbox is 'west,south,east,north' -> Overpass wants 'south,west,north,east'."""
    west, south, east, north = (float(x) for x in bbox_str.split(","))
    return f"{south},{west},{north},{east}"


def _run_overpass(query, cache_path, use_cache=True):
    if use_cache and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    resp = requests.post(config.OVERPASS_URL, data={"data": query}, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    cache_path.write_text(json.dumps(data), encoding="utf-8")
    time.sleep(1)
    return data


def fetch_facilities(use_cache=True):
    """Query Overpass for industrial facilities within the configured bbox."""
    bbox = _bbox_to_overpass(config.REGION_BBOX)
    query = f"""
    [out:json][timeout:90];
    (
      node["landuse"="industrial"]({bbox});
      way["landuse"="industrial"]({bbox});
      node["man_made"="works"]({bbox});
      way["man_made"="works"]({bbox});
      node["power"="plant"]({bbox});
      way["power"="plant"]({bbox});
      way["industrial"]({bbox});
    );
    out center tags;
    """
    data = _run_overpass(query, FACILITIES_CACHE, use_cache)

    facilities = []
    for i, el in enumerate(data.get("elements", [])):
        tags = el.get("tags", {})
        lat = el.get("lat") or el.get("center", {}).get("lat")
        lon = el.get("lon") or el.get("center", {}).get("lon")
        if lat is None or lon is None:
            continue

        facility_type = "Industrial Facility"
        for (k, v), label in TAG_TO_TYPE.items():
            if tags.get(k) == v:
                facility_type = label
                break

        name = tags.get("name") or f"Unnamed {facility_type} ({el['type']}/{el['id']})"

        facilities.append({
            "id": f"FAC-OSM-{el['id']}",
            "name": name,
            "type": facility_type,
            "latitude": lat,
            "longitude": lon,
        })

    print(f"[enrich] {len(facilities)} industrial facilities from OpenStreetMap")
    return facilities


def fetch_forest_centroids(use_cache=True):
    """Query Overpass for forest/natural-wood areas, reduced to centroids."""
    bbox = _bbox_to_overpass(config.REGION_BBOX)
    query = f"""
    [out:json][timeout:90];
    (
      way["natural"="wood"]({bbox});
      way["landuse"="forest"]({bbox});
      relation["natural"="wood"]({bbox});
      relation["landuse"="forest"]({bbox});
    );
    out center;
    """
    data = _run_overpass(query, FOREST_CACHE, use_cache)

    centroids = []
    for el in data.get("elements", []):
        center = el.get("center")
        if center:
            centroids.append((center["lat"], center["lon"]))

    print(f"[enrich] {len(centroids)} forest/natural-land areas from OpenStreetMap")
    return centroids


def nearest_facility(lat, lon, facilities):
    best, best_dist = None, None
    for f in facilities:
        dist = _haversine_km(lat, lon, f["latitude"], f["longitude"])
        if best_dist is None or dist < best_dist:
            best, best_dist = f, dist
    return best, best_dist


def nearest_forest_km(lat, lon, forest_centroids):
    if not forest_centroids:
        return None
    return min(_haversine_km(lat, lon, flat, flon) for flat, flon in forest_centroids)


def enrich_detection(detection, facilities, forest_centroids):
    """Attach facility + land-cover context fields to one detection dict."""
    facility, distance_km = nearest_facility(detection["latitude"], detection["longitude"], facilities)
    is_industrial = facility is not None and distance_km <= config.INDUSTRIAL_PROXIMITY_KM

    forest_distance = nearest_forest_km(detection["latitude"], detection["longitude"], forest_centroids)
    is_forest = forest_distance is not None and forest_distance <= 1.0

    if is_industrial:
        land_cover = "Industrial Area"
    elif is_forest:
        land_cover = "Forest"
    else:
        land_cover = "Mixed / Peri-urban"

    detection.update({
        "facilityId": facility["id"] if is_industrial else None,
        "facilityName": facility["name"] if is_industrial else None,
        "facilityType": facility["type"] if is_industrial else None,
        "distanceToFacilityKm": round(distance_km, 2) if distance_km is not None else None,
        "landCover": land_cover,
    })
    return detection
