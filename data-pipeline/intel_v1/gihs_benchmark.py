"""EVALUATION-ONLY external benchmark vs the Global Industrial Heat Source dataset (Ma et al., Scientific Data 2024; Zenodo).
GIHS is NEVER used as training labels. Download it on a networked machine, then:
  python3 data-pipeline/intel_v1/gihs_benchmark.py --gihs GIHS.csv --lat-col LAT --lon-col LON --intel public/thermwatch_intel.json --pihs PIHS_CANDIDATES.csv
Reports: share of ThermWatch PIHS candidates within R km of a GIHS source; share of in-region GIHS sources with a PIHS candidate within R km.
Caveats: GIHS covers 2012-2021 (ThermWatch window is 2026); both derive from VIIRS detections, so agreement is consistency, not independent truth."""
import argparse, csv, json, math

def km(a, b, c, d):
    r = math.radians; x = math.sin(r(c - a) / 2) ** 2 + math.cos(r(a)) * math.cos(r(c)) * math.sin(r(d - b) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, x)))

def match_rate(A, B, r_km):
    grid = {}
    for la, lo in B: grid.setdefault((math.floor(la / 0.1), math.floor(lo / 0.1)), []).append((la, lo))
    hit = sum(1 for la, lo in A if any(km(la, lo, x, y) <= r_km for di in (-1, 0, 1) for dj in (-1, 0, 1) for x, y in grid.get((math.floor(la / 0.1) + di, math.floor(lo / 0.1) + dj), [])))
    return hit, len(A)

def run(pihs_pts, gihs_pts, bbox=(6.0, 68.0, 37.5, 97.5), radii=(0.5, 1.0, 2.0)):
    g = [(a, b) for a, b in gihs_pts if bbox[0] <= a <= bbox[2] and bbox[1] <= b <= bbox[3]]
    return {"gihs_in_region": len(g), "pihs_candidates": len(pihs_pts),
            "by_radius_km": {str(r): {"pihs_near_gihs": match_rate(pihs_pts, g, r), "gihs_near_pihs": match_rate(g, pihs_pts, r)} for r in radii},
            "note": "consistency check only; not accuracy; GIHS 2012-2021 vs ThermWatch 2026; never used as labels"}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--gihs", required=True); ap.add_argument("--lat-col", required=True); ap.add_argument("--lon-col", required=True)
    ap.add_argument("--pihs", required=True, help="CSV with latitude,longitude of PIHS candidates"); a = ap.parse_args()
    G = [(float(r[a.lat_col]), float(r[a.lon_col])) for r in csv.DictReader(open(a.gihs))]
    P = [(float(r["latitude"]), float(r["longitude"])) for r in csv.DictReader(open(a.pihs))]
    print(json.dumps(run(P, G), indent=1))
