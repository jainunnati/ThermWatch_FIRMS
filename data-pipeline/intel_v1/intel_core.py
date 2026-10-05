"""ThermWatch intelligence layer v1: PIHS detector, alert prioritisation, why-cards. Rule-based, deterministic.
NOT ground truth, NOT a supervised classifier, NOT probabilities.

PIHS (Persistent Industrial Heat Source) - transparent rule grounded in the industrial-heat-source literature
(temporal persistence + night-time operation + spatial aggregation; e.g. Liu et al. 2018, Ma et al. 2024), thresholds chosen
for ThermWatch's own feature definitions (fixed before results):
  PERSISTENT_ACTIVITY : active_days >= 20                                     (+3)
  MULTI_DAY_ACTIVITY  : active_days >= 5                                      (+1)
  NIGHT_DOMINANT      : night_frac >= 0.6 and detection_count >= 3            (+2)
  REPEATED_EVENTS     : event_count >= 3                                      (+1)
  SPATIALLY_COMPACT   : spatial_extent_m <= 750 (~2 VIIRS pixels) and detection_count >= 3   (+1)
  PIHS_SCORE = sum (0-8). PIHS_FLAG = PERSISTENT_ACTIVITY and NIGHT_DOMINANT and SPATIALLY_COMPACT.
  Missing inputs -> PIHS_FLAG False, PIHS_SCORE None, reason INSUFFICIENT_DATA (never treated as zero activity).

ALERT_PRIORITY_SCORE (0-1, operational triage, not probability) =
  0.35*pihs(score/8) + 0.25*recency(min(1, recent_30d/5)) + 0.15*intensity_jump(min(1,(frp_max/frp_mean-1)/4), n>=3)
  + 0.15*persistence(min(1, active_days/60)) + 0.10*facility_context(top facility weight/100; capped -> distance cannot dominate)
  Tiers: HIGH >= 0.60, MEDIUM >= 0.40, else LOW. Ties broken by source_id."""
PIHS_RULES_VERSION = "pihs-v1"; ALERT_VERSION = "alert-priority-v1"
POINTS = {"PERSISTENT_ACTIVITY": 3, "MULTI_DAY_ACTIVITY": 1, "NIGHT_DOMINANT": 2, "REPEATED_EVENTS": 1, "SPATIALLY_COMPACT": 1}
TEXT = {"PERSISTENT_ACTIVITY": "Persistent: active on {ad} separate days", "MULTI_DAY_ACTIVITY": "Active on multiple days",
        "NIGHT_DOMINANT": "Night-dominant: {nf}% of detections at night", "REPEATED_EVENTS": "Repeated: {ev} separate thermal events",
        "SPATIALLY_COMPACT": "Spatially compact: detections within {ext} m"}
FACILITY_CATS = {"STEEL_METAL", "THERMAL_POWER", "LNG_GAS"}


def _num(v):
    try: return None if v in (None, "") else float(v)
    except (TypeError, ValueError): return None


def pihs(f):
    ad, nf, n, ev, ext = (_num(f.get(k)) for k in ("active_days", "night_frac", "detection_count", "event_count", "spatial_extent_m"))
    if None in (ad, nf, n, ev, ext):
        return {"pihs_flag": False, "pihs_score": None, "pihs_reasons": ["INSUFFICIENT_DATA"], "pihs_version": PIHS_RULES_VERSION}
    r = []
    if ad >= 20: r.append("PERSISTENT_ACTIVITY")
    if ad >= 5: r.append("MULTI_DAY_ACTIVITY")
    if nf >= 0.6 and n >= 3: r.append("NIGHT_DOMINANT")
    if ev >= 3: r.append("REPEATED_EVENTS")
    if ext <= 750 and n >= 3: r.append("SPATIALLY_COMPACT")
    flag = {"PERSISTENT_ACTIVITY", "NIGHT_DOMINANT", "SPATIALLY_COMPACT"} <= set(r)
    return {"pihs_flag": flag, "pihs_score": sum(POINTS[x] for x in r), "pihs_reasons": r, "pihs_version": PIHS_RULES_VERSION}


def alert(f, p, attr):
    ad, n, rec, fmax, fmean = (_num(f.get(k)) or 0.0 for k in ("active_days", "detection_count", "recent_30d_detections", "frp_max", "frp_mean"))
    comp = {"pihs": (p["pihs_score"] or 0) / 8, "recency": min(1.0, rec / 5), "intensity_jump": min(1.0, max(0.0, (fmax / fmean - 1) / 4)) if (n >= 3 and fmean > 0) else 0.0,
            "persistence": min(1.0, ad / 60), "facility_context": 0.0}
    if attr and attr.get("top") in FACILITY_CATS: comp["facility_context"] = attr["top_pct"] / 100
    W = {"pihs": .35, "recency": .25, "intensity_jump": .15, "persistence": .15, "facility_context": .10}
    s = round(sum(W[k] * comp[k] for k in W), 4)
    codes = [c for c, ok in (("PIHS_CANDIDATE", p["pihs_flag"]), ("RECENT_ACTIVITY", rec > 0), ("INTENSITY_ABOVE_OWN_BASELINE", comp["intensity_jump"] >= 0.5),
                             ("LONG_RUNNING", ad >= 20), ("FACILITY_CONTEXT", comp["facility_context"] > 0)) if ok]
    return {"alert_priority_score": s, "alert_tier": "HIGH" if s >= 0.6 else ("MEDIUM" if s >= 0.4 else "LOW"), "alert_reason_codes": codes,
            "alert_components": {k: round(v, 3) for k, v in comp.items()}, "alert_version": ALERT_VERSION}


def why_card(rank, f, p, a, attr, coverage):
    ad, nf, n, ev, ext = int(_num(f["active_days"]) or 0), _num(f["night_frac"]) or 0, int(_num(f["detection_count"]) or 0), int(_num(f["event_count"]) or 0), _num(f["spatial_extent_m"]) or 0
    reasons = [TEXT[r].format(ad=ad, nf=round(nf * 100), ev=ev, ext=round(ext)) for r in p["pihs_reasons"] if r in TEXT] or ["Insufficient data for persistence assessment"]
    facts = [f"{n} detections on {ad} days between {f['first_seen'][:10]} and {f['last_seen'][:10]}", f"{round(nf * 100)}% of detections at night",
             f"{int(_num(f.get('recent_30d_detections')) or 0)} detections in the last 30 days of the record"]
    near = []
    if attr and attr.get("nearest_name"):
        near = [{"name": attr["nearest_name"], "type": attr["nearest_type"], "distance_km": attr["nearest_km"]}]
        facts.append(f"{attr['nearest_name']} ({attr['nearest_type'].replace('_', ' ').lower()}) is {attr['nearest_km']:.2f} km away")
    heur = (f"ThermWatch attribution assigns {attr['top_pct']}% relative weight to {attr['top'].replace('_', ' ').lower()} (proximity-driven heuristic)"
            if attr and attr.get("top") else "No facility within 5 km: attribution UNKNOWN")
    expl = " ".join([reasons[0] + ".", ("Night-dominant. " if "NIGHT_DOMINANT" in p["pihs_reasons"] else ""),
                     (f"Lies {attr['nearest_km']:.2f} km from {attr['nearest_name']}. " if near else "No documented facility within 5 km. "), heur + ".", "Cause not confirmed."]).replace("  ", " ").strip()
    return {"source_id": f["source_id"], "alert_rank": rank, "alert_tier": a["alert_tier"], "alert_priority_score": a["alert_priority_score"], "alert_reason_codes": a["alert_reason_codes"],
            "latitude": f["latitude"], "longitude": f["longitude"], "pihs_flag": p["pihs_flag"], "pihs_score": p["pihs_score"], "pihs_reasons": reasons,
            "activity_summary": facts, "attribution": (attr or {}).get("all", {}), "attribution_statement": heur, "nearby_facilities": near,
            "coverage_status": coverage, "confidence": (attr or {}).get("confidence", "UNKNOWN"), "cause": "Not confirmed",
            "explanation": expl, "caveats": ["Attribution weights are heuristic and proximity-driven, not calibrated probabilities.",
                                              "PIHS is a transparent rule-based detector, not ground truth.", "No incident found does not mean no incident occurred."]}
