"""Build compact indexes the live runner needs (committable; no raw data): registry centroids, historical PIHS flags, GEM facilities.
  python3 data-pipeline/intel_v1/build_live_indexes.py OUT_DIR"""
import csv, gzip, sys
from pathlib import Path
sys.path.insert(0, "/home/claude/gem")
def main(out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    with gzip.open("/home/claude/stepd_out/source_registry_v1.csv.gz", "rt") as f, gzip.GzipFile(out / "registry_index.csv.gz", "wb", mtime=0) as g:
        g.write(b"source_id,lat,lon,n_obs\n")
        for r in csv.DictReader(f): g.write(f"{r['source_id']},{float(r['centroid_lat']):.5f},{float(r['centroid_lon']):.5f},{r['n_obs']}\n".encode())
    import shutil; shutil.copy("/home/claude/intel/out/pihs_candidates.csv", out / "pihs_index.csv")
    import register_match as RM
    S = sorted((s for s in RM.sites() if s["lat"] is not None and 5 <= s["lat"] <= 39 and 66 <= s["lon"] <= 99), key=lambda s: (s["kind"], str(s["site_id"])))
    with open(out / "facilities_index.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(["kind", "site_id", "name", "lat", "lon"])
        for s in S: w.writerow([s["kind"], s["site_id"], s["name"], f"{s['lat']:.6f}", f"{s['lon']:.6f}"])
    print("indexes written to", out)
if __name__ == "__main__":
    main(sys.argv[1])
