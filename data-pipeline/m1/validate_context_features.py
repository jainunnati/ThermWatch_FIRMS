"""Validate a built source_context_features.csv (real or fixture). Read-only. Exit 1 on any failure.

  python3 m1/validate_context_features.py --dir OUT_DIR [--osm-cache DIR] [--wc-cache DIR] [--expect-ids FILE]
"""
import argparse, csv, hashlib, json, math, sys
from pathlib import Path


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", required=True)
    ap.add_argument("--osm-cache"); ap.add_argument("--wc-cache"); ap.add_argument("--expect-ids")
    a = ap.parse_args(); D = Path(a.dir)
    sch = json.loads((D / "source_context_features.schema.json").read_text())
    man = json.loads((D / "feature_manifest.json").read_text())
    rows = list(csv.DictReader(open(D / "source_context_features.csv")))
    errs, warn = [], []
    def e(m): errs.append(m)
    hdr = list(rows[0]) if rows else []
    if hdr != sch["column_order"]: e("CSV header != schema column_order")
    if any(c for c in hdr if "label" in c.lower()): e("label-like column present")
    ids = [r["source_id"] for r in rows]
    if len(ids) != len(set(ids)): e("duplicate source_id")
    if a.expect_ids:
        want = set(Path(a.expect_ids).read_text().split())
        if set(ids) != want: e(f"source_id set != expected ({len(set(ids) ^ want)} differ)")
    if man["output_sha256"]["source_context_features.csv"] != sha(D / "source_context_features.csv"): e("manifest hash mismatch (csv)")
    for p, h in man.get("context_cache_files_sha256", {}).items():
        for root in (a.osm_cache, a.wc_cache):
            if root and (Path(root) / p).exists() and sha(Path(root) / p) != h: e(f"cache file changed since build: {p}")
    osm_cols = [c for c in hdr if c.startswith("osm_count_") or (c.startswith("osm_nearest_") and c.endswith("_m"))]
    osm_str = [c for c in hdr if c.startswith("osm_nearest_any_") and not c.endswith("_m")]
    wc_frac = [c for c in hdr if c.startswith("wc_frac_")]
    st = {"osm": {}, "wc": {}}
    for r in rows:
        sid = r["source_id"]; o, w = r["osm_status"], r["wc_status"]
        st["osm"][o] = st["osm"].get(o, 0) + 1; st["wc"][w.split(":")[0]] = st["wc"].get(w.split(":")[0], 0) + 1
        if o != "OK":
            if any(r[c] != "" for c in osm_cols + osm_str): e(f"{sid}: osm not OK but values present (missing must stay empty)")
        else:
            if not r["osm_base_timestamp"]: e(f"{sid}: OK without osm_base_timestamp")
            for c in osm_cols:
                if c.startswith("osm_count_"):
                    if r[c] == "" or int(r[c]) < 0: e(f"{sid}: {c} must be a non-negative int when OK")
                elif r[c] != "" and not (0 <= float(r[c]) <= 5000.5): e(f"{sid}: {c} outside 0..5000 m")
            if (r["osm_nearest_any_ref"] == "") != (r["osm_nearest_any_m"] == ""): e(f"{sid}: nearest_any ref/distance inconsistent")
            for cat in {c.split("osm_count_")[1].rsplit("_", 1)[0] for c in osm_cols if c.startswith("osm_count_")}:
                n1, n5 = int(r[f"osm_count_{cat}_1000m"]), int(r[f"osm_count_{cat}_5000m"])
                if n1 > n5: e(f"{sid}: {cat} 1km count > 5km count")
                if (n5 > 0) != (r[f"osm_nearest_{cat}_m"] != ""): e(f"{sid}: {cat} nearest/count inconsistent")
        if w.startswith("OK") or w.startswith("PARTIAL"):
            vals = [float(r[c]) for c in wc_frac if r[c] != ""]
            nod = float(r["wc_nodata_frac_500m"]) if r["wc_nodata_frac_500m"] else None
            if nod is not None and nod < 1 and abs(sum(vals) - 1) > 1e-3: e(f"{sid}: wc fractions sum {sum(vals):.4f} != 1")
            if not r["wc_n_pixels_500m"] or int(r["wc_n_pixels_500m"]) <= 0: e(f"{sid}: no pixels counted")
            if w.startswith("OK") and r["wc_n_pixels_500m"] and int(r["wc_n_pixels_500m"]) < 1000:
                warn.append(f"{sid}: only {r['wc_n_pixels_500m']} px in 500 m (expected ~7800 at 10 m)")
        else:
            if any(r[c] != "" for c in wc_frac + ["wc_class_at_point"]): e(f"{sid}: wc not OK but values present")
            if w.startswith("READ_ERROR"): warn.append(f"{sid}: {w}")
    rep = {"n_rows": len(rows), "status_counts": st, "errors": errs[:100], "n_errors": len(errs), "warnings": warn[:50],
           "n_warnings": len(warn), "passed": not errs}
    (D / "context_validation_report.json").write_text(json.dumps(rep, indent=1) + "\n")
    print(json.dumps({k: rep[k] for k in ("n_rows", "status_counts", "n_errors", "n_warnings", "passed")}))
    sys.exit(0 if not errs else 1)


if __name__ == "__main__":
    main()
