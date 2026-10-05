"""One streaming pass: per-source activity features for ALL registry sources (read-only over Step D + raw FIRMS).
Output (gz CSV): source_id, detection_count, active_days, night_frac, frp_max, frp_median_approx(=mean), first_seen, last_seen, recent_30d_detections."""
import csv, glob, gzip, os, sys
from datetime import datetime, timezone, timedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from thermwatch_core.schema import make_physical_key
MEMB = "/home/claude/stepd_out/registry_membership_v1.tsv.gz"; RAW = "/home/claude/w/data_jan_oct_final"
END = datetime(2026, 10, 1, 23, 59, tzinfo=timezone.utc); RECENT = END - timedelta(days=30)

def main(out):
    k2s = {}
    with gzip.open(MEMB, "rt") as f:
        next(f)
        for line in f:
            p = line.split("\t", 3); k2s[p[0]] = p[2]
    agg, seen = {}, set()
    for fn in sorted(glob.glob(os.path.join(RAW, "*.csv"))):
        with open(fn, newline="") as f:
            for r in csv.DictReader(f):
                t = datetime.strptime(r["acq_date"] + r["acq_time"].zfill(4), "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
                pk = make_physical_key(r["instrument"], r["satellite"], t, float(r["latitude"]), float(r["longitude"]))
                if pk in seen or pk not in k2s: continue
                seen.add(pk); sid = k2s[pk]; frp = float(r["frp"])
                a = agg.get(sid)
                if a is None: a = agg[sid] = [0, set(), 0, 0.0, 0.0, t, t, 0]
                a[0] += 1; a[1].add(t.toordinal()); a[2] += r["daynight"] == "N"; a[3] = max(a[3], frp); a[4] += frp
                if t < a[5]: a[5] = t
                if t > a[6]: a[6] = t
                a[7] += t >= RECENT
    with gzip.GzipFile(out, "wb", mtime=0) as gz:
        gz.write(b"source_id,detection_count,active_days,night_frac,frp_max,frp_mean,first_seen,last_seen,recent_30d_detections\n")
        for sid in sorted(agg):
            a = agg[sid]
            gz.write(f"{sid},{a[0]},{len(a[1])},{a[2]/a[0]:.4f},{a[3]:.2f},{a[4]/a[0]:.3f},{a[5].isoformat()},{a[6].isoformat()},{a[7]}\n".encode())
    print("sources", len(agg), "detections", len(seen))

if __name__ == "__main__":
    main(sys.argv[1])
