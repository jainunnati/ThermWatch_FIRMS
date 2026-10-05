"""Track B: reproducible draw of a NEW label-acquisition sample from the Step D registry (no labels created).

Frame: every registry source except --exclude ids (the 185 pilot sources). Strata use ONLY registry-native,
label-free attributes:
  persistence tier : EPISODIC (1 event) | RECURRENT (2-9 events) | PERSISTENT (>=10 events and span >= 90 d)
                     | OTHER (>=10 events, span < 90 d)
  region cell      : 5x5-degree cell of the centroid
Within each stratum, sources are ordered by sha256(seed|source_id) and the first n are taken. Allocation per tier is
explicit (--per-tier); within a tier it is split evenly across region cells (round-robin), so no region dominates.
Every drawn row carries its stratum, the stratum population and an inclusion probability, so later estimates can be
re-weighted. Sampling attributes are written ONLY to the private draw file, never to annotator packets.
"""
import argparse, csv, gzip, hashlib, json, math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

TIERS = ("EPISODIC", "RECURRENT", "PERSISTENT", "OTHER")


def tier(r):
    ne = int(r["n_events"])
    span = (datetime.fromisoformat(r["last_seen_utc"]) - datetime.fromisoformat(r["first_seen_utc"])).days
    if ne == 1: return "EPISODIC"
    if ne < 10: return "RECURRENT"
    return "PERSISTENT" if span >= 90 else "OTHER"


def cell(r):
    return f"{math.floor(float(r['centroid_lat']) / 5) * 5:+03d}_{math.floor(float(r['centroid_lon']) / 5) * 5:+04d}"


def draw(registry, exclude, per_tier, seed):
    strata = defaultdict(list); pop = defaultdict(int)
    with gzip.open(registry, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["source_id"] in exclude: continue
            s = (tier(r), cell(r)); pop[s] += 1
            strata[s].append((hashlib.sha256(f"{seed}|{r['source_id']}".encode()).hexdigest(), r["source_id"],
                              r["registry_id"]))
    out = []
    for t in TIERS:
        cells = sorted(c for (tt, c) in strata if tt == t)
        for k in cells: strata[(t, k)].sort()
        want, taken, i = per_tier.get(t, 0), defaultdict(int), 0
        while want > 0 and any(taken[c] < len(strata[(t, c)]) for c in cells):
            c = cells[i % len(cells)]; i += 1
            if taken[c] < len(strata[(t, c)]):
                h, sid, rid = strata[(t, c)][taken[c]]; taken[c] += 1; want -= 1
                out.append({"source_id": sid, "registry_id": rid, "stratum_tier": t, "stratum_cell": c, "order_hash": h})
        for row in out:
            if row["stratum_tier"] == t:
                n = taken[row["stratum_cell"]]; N = pop[(t, row["stratum_cell"])]
                row.update(stratum_population=N, stratum_drawn=n, inclusion_prob=round(n / N, 8))
    return out, {f"{t}|{c}": n for (t, c), n in sorted(pop.items())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True); ap.add_argument("--exclude", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--seed", default="thermwatch-label-sample-v1")
    ap.add_argument("--per-tier", default="PERSISTENT=150,RECURRENT=100,EPISODIC=100,OTHER=50")
    a = ap.parse_args()
    per = {k: int(v) for k, v in (x.split("=") for x in a.per_tier.split(","))}
    excl = set(Path(a.exclude).read_text().split())
    rows, pop = draw(a.registry, excl, per, a.seed)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    with open(out / "PRIVATE_label_sample_draw.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    (out / "label_sample_manifest.json").write_text(json.dumps({
        "seed": a.seed, "per_tier": per, "n_drawn": len(rows), "n_excluded_pilot": len(excl),
        "registry_sha256": hashlib.sha256(Path(a.registry).read_bytes()).hexdigest(),
        "drawn_by_tier": {t: sum(r["stratum_tier"] == t for r in rows) for t in TIERS},
        "frame_population_by_tier": {t: sum(n for k, n in pop.items() if k.startswith(t + "|")) for t in TIERS},
        "n_strata": len(pop)}, indent=1) + "\n")
    print(json.dumps({"n_drawn": len(rows), "by_tier": {t: sum(r["stratum_tier"] == t for r in rows) for t in TIERS}}))


if __name__ == "__main__":
    main()
