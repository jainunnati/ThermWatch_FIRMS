"""Small geodesy helpers (spherical Earth; adequate for sub-10 km extents)."""
import math

EARTH_RADIUS_M = 6371008.8


def haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def mean_centroid(points):
    """Arithmetic mean of (lat, lon). Not antimeridian-safe; fine for India-scale work."""
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def bbox(points):
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    return {"lat": [min(lats), max(lats)], "lon": [min(lons), max(lons)]}


def offset_m(lat, lon, north_m=0.0, east_m=0.0):
    """Return a point displaced by metres (used only to build test fixtures)."""
    dlat = math.degrees(north_m / EARTH_RADIUS_M)
    dlon = math.degrees(east_m / (EARTH_RADIUS_M * math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon
