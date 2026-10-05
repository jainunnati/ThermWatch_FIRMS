"""ThermWatch LIVE update (reuses data-pipeline/ingest_firms.py and Step C's physical key). Never fabricates live data.
  python3 data-pipeline/intel_v1/live_update.py --indexes data-pipeline/intel_v1/live_indexes --out public/data/thermwatch_live.json [--input-csv FILE]
Without --input-csv it calls the FIRMS Area API for the last day of VIIRS NRT (FIRMS_MAP_KEY from the environment; never in code).
Association is INCREMENTAL and approximate: nearest historical source within 375 m, else a provisional NEW source (clustered at 375 m).
It does not re-run the validated Step C streaming formation."""
import argparse, csv, gzip, hashlib, json, math, os, sys
from datetime import datetime, timezone
from pathlib import Path
HERE = Path(__file__).resolve().parent; ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "m1"))
from thermwatch_core.schema import make_physical_key
import importlib.util
_spec = importlib.util.spec_from_file_location("attribution_mvp_v1", ROOT / "m1" / "attribution_mvp_v1.py"); AM = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(AM)
CONTRACT = "thermwatch-contract-v2"; BBOX = "68,6,97.5,37.5"; SOURCES = ["VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT", "VIIRS_SNPP_NRT"]; R_KM = 0.375


def fetch_live():
    import ingest_firms as IF, config  # existing client; raises FirmsAuthError if FIRMS_MAP_KEY missing
    from datetime import date
    rows = []
    for s in SOURCES:
        rows += IF.fetch_window(s, date.today(), 1, use_cache=False, bbox=BBOX)   # all-India live area (not the config.REGION_BBOX dev box)
    return rows


def grid_index(rows, key=lambda r: (r["lat"], r["lon"])):
    g = {}
    for r in rows:
        la, lo = key(r); g.setdefault((math.floor(la / 0.01), math.floor(lo / 0.01)), []).append(r)
    return g


def nearest(g, la, lo, r_km):
    best = None
    for di in (-1, 0, 1):
        for dj in (-1, 0, 1):
            for c in g.get((math.floor(la / 0.01) + di, math.floor(lo / 0.01) + dj), []):
                d = AM.haversine_km(la, lo, c["lat"], c["lon"])
                if d <= r_km and (best is None or (d, c["source_id"]) < best[0]): best = ((d, c["source_id"]), c)
    return best


def run(raw_rows, idx_dir, status="OK", status_detail=""):
    idx = Path(idx_dir)
    reg = [{"source_id": r["source_id"], "lat": float(r["lat"]), "lon": float(r["lon"]), "n_obs": int(r["n_obs"])} for r in csv.DictReader(gzip.open(idx / "registry_index.csv.gz", "rt"))]
    rg = grid_index(reg); pihs = {r["source_id"]: r for r in csv.DictReader(open(idx / "pihs_index.csv"))}
    fac = [(r["kind"], r["site_id"], r["name"], float(r["lat"]), float(r["lon"])) for r in csv.DictReader(open(idx / "facilities_index.csv"))]
    seen, obs = set(), []
    for r in raw_rows:
        t = datetime.strptime(r["acq_date"] + str(r["acq_time"]).zfill(4), "%Y-%m-%d%H%M").replace(tzinfo=timezone.utc)
        pk = make_physical_key(r.get("instrument", "VIIRS"), r["satellite"], t, float(r["latitude"]), float(r["longitude"]))
        if pk in seen: continue
        seen.add(pk); obs.append({"pk": pk, "t": t.isoformat(), "lat": float(r["latitude"]), "lon": float(r["longitude"]), "frp": float(r.get("frp") or 0), "dn": r.get("daynight", "")})
    obs.sort(key=lambda o: (o["t"], o["pk"])); groups, new = {}, []
    for o in obs:
        m = nearest(rg, o["lat"], o["lon"], R_KM)
        if m: groups.setdefault(m[1]["source_id"], {"kind": "EXISTING", "src": m[1], "obs": []})["obs"].append(o); continue
        hit = next((n for n in new if AM.haversine_km(o["lat"], o["lon"], n["lat"], n["lon"]) <= R_KM), None)
        if hit is None:
            hit = {"source_id": "LIVE-" + hashlib.sha256(o["pk"].encode()).hexdigest()[:10], "lat": o["lat"], "lon": o["lon"], "obs": []}; new.append(hit)
        hit["obs"].append(o)
    items = []
    def nearby(la, lo):
        return [f for f in fac if abs(f[3] - la) < 0.06 and abs(f[4] - lo) < 0.07]
    for sid, g in sorted(groups.items()):
        s = g["src"]; o = g["obs"]; p = pihs.get(sid)
        a = AM.attribute({"source_id": sid, "lat": s["lat"], "lon": s["lon"], "active_days": 0, "night_frac": 0, "observation_count": 2}, nearby(s["lat"], s["lon"]))
        items.append({"source_id": sid, "status": "EXISTING_SOURCE", "lat": s["lat"], "lon": s["lon"], "live_detections": len(o), "last_detection": o[-1]["t"],
                      "historical_detections": s["n_obs"], "pihs": "PIHS candidate (historical window)" if p else "Not a PIHS candidate in historical window",
                      "attribution": a["weights"], "attribution_confidence": a["confidence"], "cause": "Not confirmed"})
    for n in new:
        a = AM.attribute({"source_id": n["source_id"], "lat": n["lat"], "lon": n["lon"], "active_days": 0, "night_frac": 0, "observation_count": 2}, nearby(n["lat"], n["lon"]))
        items.append({"source_id": n["source_id"], "status": "NEW_PROVISIONAL_SOURCE", "lat": round(n["lat"], 5), "lon": round(n["lon"], 5), "live_detections": len(n["obs"]),
                      "last_detection": n["obs"][-1]["t"], "historical_detections": 0, "pihs": "Insufficient history for persistence classification",
                      "attribution": a["weights"], "attribution_confidence": a["confidence"], "cause": "Not confirmed"})
    items.sort(key=lambda x: (x["status"] != "EXISTING_SOURCE" or x["pihs"].startswith("Not"), -x["live_detections"], x["source_id"]))
    ts = max((o["t"] for o in obs), default=None)
    return {"contract_version": CONTRACT, "mode": "LIVE", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "data_timestamp": ts,
            "pipeline_status": status if (status != "OK" or obs) else "OK_NO_DETECTIONS", "pipeline_status_detail": status_detail,
            "pipeline_run_id": "live-" + hashlib.sha256(json.dumps([o["pk"] for o in obs]).encode()).hexdigest()[:12],
            "coverage_status": "Live NRT window only; no detection in a live window is NOT evidence of no fire.",
            "system_stats": {"live_observations": len(raw_rows), "live_observations_dedup": len(obs), "existing_sources_active": len(groups), "new_provisional_sources": len(new)},
            "live_sources": items, "disclaimer": "Live association is incremental (nearest historical source within 375 m). Attribution is heuristic; cause not confirmed."}


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--indexes", required=True); ap.add_argument("--out", required=True); ap.add_argument("--input-csv"); a = ap.parse_args()
    try:
        rows = list(csv.DictReader(open(a.input_csv))) if a.input_csv else fetch_live(); res = run(rows, a.indexes)
    except Exception as e:  # never fake data: publish an explicit unavailable status
        detail = "FIRMS credentials missing or rejected" if type(e).__name__ == "FirmsAuthError" else f"{type(e).__name__}: feed request failed"
        res = run([], a.indexes, "LIVE_FEED_UNAVAILABLE", detail)   # sanitised: never echo URLs, keys or raw error text
    Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n")
    print(res["pipeline_status"], json.dumps(res["system_stats"]))


if __name__ == "__main__":
    main()
