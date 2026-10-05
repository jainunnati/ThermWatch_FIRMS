"""Additive, polite OSM fetcher (core context_osm unchanged). One tile per call via context_osm.fetch_tiles, so failed
tiles are never cached. Adds: base interval, Retry-After/exponential backoff on 429/504/timeouts, stop after N
consecutive failures, per-request JSONL log with UTC timestamps. Resumable: cached tiles are skipped.
  python3 m1/fetch_osm_backoff.py --plan runs/X/fetch_plan.json --osm-cache context_cache/osm --log runs/X/osm_requests.jsonl"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from thermwatch_core import context_osm as osm   # noqa: E402

def run(tiles, cache, transport, endpoint, log, base=30.0, max_backoff=900.0, max_consecutive=5, sleep=time.sleep, now=time.time):
    fails, done, backoff = 0, [], base
    for t in sorted(set(tiles)):
        if cache.has(t): continue
        r = osm.fetch_tiles([t], cache, transport, endpoint, min_interval_s=0, sleep=sleep, log=lambda *a: None)
        err = r["failed"].get(t); rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now())), "tile": t, "ok": t in r["fetched"], "error": err}
        log.write(json.dumps(rec) + "\n"); log.flush()
        if rec["ok"]: done.append(t); fails = 0; backoff = base; sleep(base); continue
        fails += 1
        if fails >= max_consecutive: return {"fetched": done, "stopped": f"{fails} consecutive failures (last: {err})"}
        wait = backoff
        if err and ("429" in err or "504" in err or "Timeout" in err or "timed out" in err): backoff = min(backoff * 2, max_backoff)
        sleep(wait)
    return {"fetched": done, "stopped": None}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True); ap.add_argument("--osm-cache", required=True); ap.add_argument("--log", required=True)
    ap.add_argument("--endpoint", default="https://overpass-api.de/api/interpreter"); ap.add_argument("--interval", type=float, default=30.0)
    a = ap.parse_args(); plan = json.loads(Path(a.plan).read_text())
    with open(a.log, "a") as lg:
        res = run(plan["osm_tiles"], osm.OSMCache(a.osm_cache), osm.requests_transport(), a.endpoint, lg, base=a.interval)
    print(json.dumps({"fetched": len(res["fetched"]), "stopped": res["stopped"]}))
