"""Adapter: core results -> the existing §14 Final Assessment Object (frontend contract unchanged).

Honesty rules enforced here:
  * No trained classifier   -> source_characterization.status NOT_COMPUTED, class probabilities null.
  * No facility module      -> facility_attribution.status NOT_COMPUTED; G4 cannot pass; the event is
                               reported with its pre-gate evidence but behaviour = 'Insufficient Evidence'.
  * No calibrated thresholds-> behaviour never becomes Normal/Elevated/Abnormal (abstains instead).
  * Fusion weights are equal-prototype and labelled NOT validated.
  * Confidence dimensions are separate ordinal levels (never blended into one number).
  * 'persistent_source' is true only if recurrence AND opportunity-normalized evidence support it.
Extra keys (uncertainty, provenance, why_flagged, *_evidence) are additive; the frontend ignores unknown keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .baseline import BaselineParams, compute_baseline
from .events import EventFormationResult
from .opportunity import OpportunityTable, compute_onrr, persistence_deviation
from .profile import ProfileParams, build_source_profile
from .schema import PIPELINE_VERSION, SCHEMA_VERSION, TEST_FIXTURE_BANNER, DataMode

from datetime import timedelta


@dataclass(frozen=True)
class DecisionThresholds:
    elevated: float
    abnormal: float
    label: str = "UNVALIDATED demonstration cut-offs"   # must say where thresholds came from


MODE_WORDING = {
    DataMode.HISTORICAL: "historical replay (archived FIRMS data; not live)",
    DataMode.NRT: "latest available near-real-time FIRMS product (periodic satellite snapshots; not live monitoring)",
    DataMode.DEMO: "demonstration data (provenance unknown; not FIRMS evidence)",
    DataMode.TEST_FIXTURE: TEST_FIXTURE_BANNER,
}


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _conf_level(cls):
    return {"low": "LOW", "nominal": "MEDIUM", "high": "HIGH"}.get(cls, "UNKNOWN")


def _detection_confidence(obs):
    classes = [o.confidence_class for o in obs if o.confidence_class]
    if not classes:
        return {"level": "UNKNOWN", "basis": "no confidence field on these observations"}
    order = {"low": 0, "nominal": 1, "high": 2}
    lowest = min(classes, key=lambda c: order[c])
    return {"level": _conf_level(lowest), "basis": "lowest categorical FIRMS quality class among event observations; "
            "ordinal quality flag, not a probability",
            "counts": {c: classes.count(c) for c in sorted(set(classes))}}


def build_assessment(result: EventFormationResult, event_id: str, *,
                     baseline_params: BaselineParams = BaselineParams(),
                     profile_params: ProfileParams = ProfileParams(),
                     opportunity: Optional[OpportunityTable] = None,
                     onrr_window_days: int = 30,
                     characterization: Optional[dict] = None,
                     facility: Optional[dict] = None,
                     thresholds: Optional[DecisionThresholds] = None,
                     fusion_weights: Optional[dict] = None,
                     processed_utc: Optional[datetime] = None,
                     validation_stats: Optional[dict] = None,
                     max_observations_listed: int = 500) -> dict:
    processed_utc = processed_utc or datetime.now(timezone.utc)
    ev = result.events[event_id]
    src = result.sources[ev.source_id]
    ev_obs = sorted(result.observations_of_event(event_id), key=lambda o: o.timestamp_utc)
    src_obs = result.observations_of_source(ev.source_id)
    mode = ev_obs[0].data_mode
    is_real = mode.is_real_firms
    lab_obs = "R" if is_real else "S"

    last_date = max(o.utc_date for o in ev_obs)
    target = [o for o in ev_obs if o.utc_date == last_date]
    profile = build_source_profile(ev.source_id, src_obs, profile_params)
    base = compute_baseline(src_obs, target, baseline_params)

    detect_days = {o.utc_date for o in src_obs}
    onrr = compute_onrr(detect_days, opportunity, last_date, onrr_window_days)
    pdev = {"status": "OBSERVATION_OPPORTUNITY_UNKNOWN", "p_norm": None}
    if opportunity is not None and onrr.get("onrr") is not None:
        hist = []
        first = min(detect_days)
        for k in range(1, 25):
            end = last_date - timedelta(days=k * onrr_window_days)
            if end < first:
                break
            r = compute_onrr(detect_days, opportunity, end, onrr_window_days)
            if r.get("onrr") is not None:
                hist.append(r["onrr"])
        pdev = persistence_deviation(onrr["onrr"], hist, baseline_params.min_history, baseline_params.mad_fallback)

    # ---- fusion over abnormality-relevant, computable components only (attribution is NOT one) ----
    comps = {}
    if pdev.get("p_norm") is not None:
        comps["p_norm"] = pdev["p_norm"]
    if base.get("t_anom") is not None:
        comps["t_anom"] = base["t_anom"]
    w = fusion_weights or {k: 1.0 for k in comps}
    wsum = sum(w.get(k, 0) for k in comps)
    F = (sum(w[k] * v for k, v in comps.items()) / wsum) if comps and wsum > 0 else None

    # ---- characterization + G4 gate ----
    probs = (characterization or {}).get("class_probabilities")
    class_ok = False
    if characterization and probs and characterization.get("source_class") == "Industrial":
        class_ok = probs.get("Industrial", 0) >= 0.60 and max(probs, key=probs.get) == "Industrial"
    assoc_ok = bool(facility and facility.get("association_usable") is True)
    g4_pass = class_ok and assoc_ok
    g4_reasons = []
    if not characterization:
        g4_reasons.append("CLASSIFIER_NOT_AVAILABLE")
    elif not class_ok:
        g4_reasons.append("NOT_INDUSTRIAL_ABOVE_GATE")
    if not facility:
        g4_reasons.append("FACILITY_ASSOCIATION_NOT_COMPUTED")
    elif not assoc_ok:
        g4_reasons.append("NO_USABLE_FACILITY_ASSOCIATION")

    # ---- decision (abstains whenever the evidence/calibration does not exist) ----
    codes, caveats = [], []
    abstain = None
    if not g4_pass:
        status, abstain = "Insufficient Evidence", "INSUFFICIENT_EVIDENCE"
        codes += ["G4_NOT_PASSED"] + g4_reasons
    elif base["status"] == "INSUFFICIENT_HISTORY" and not comps:
        status, abstain = "Insufficient History", "INSUFFICIENT_HISTORY"
        codes.append("INSUFFICIENT_HISTORY")
    elif F is None:
        status, abstain = "Insufficient Evidence", "INSUFFICIENT_EVIDENCE"
        codes.append("NO_COMPUTABLE_ABNORMALITY_COMPONENT")
    elif thresholds is None:
        status, abstain = "Insufficient Evidence (thresholds not calibrated)", "REVIEW_REQUIRED"
        codes.append("THRESHOLDS_NOT_CALIBRATED")
    else:
        if F >= thresholds.abnormal:
            status = "Abnormal"
        elif F >= thresholds.elevated:
            status = "Elevated"
        else:
            status = "Normal"
        if status == "Abnormal" and len(comps) < 2:
            status = "Elevated"
            codes.append("SINGLE_DIMENSION_EVIDENCE_CAPPED")
    facility_status = (facility or {}).get("status", "NOT_COMPUTED")
    attribution_level = (facility or {}).get("attribution_confidence_level", "UNKNOWN")
    facility_wording = {
        "ASSOCIATED": "spatially associated with the selected facility; this does not establish causation",
        "MULTIPLE_CANDIDATES": "multiple candidate facilities remain; attribution is ambiguous",
        "UNRESOLVED": "no suitable facility was found within the configured candidate radius",
        "INSUFFICIENT_EVIDENCE": "facility data were supplied, but the available evidence was insufficient for association",
        "NOT_COMPUTED": "facility association was not computed because no facility dataset was supplied",
    }.get(facility_status, "facility association status is unknown")
    priority = None
    if thresholds is not None and abstain is None:
        if status == "Abnormal":
            priority = "High" if attribution_level in ("HIGH", "MEDIUM") else "Medium"
        elif status == "Elevated":
            priority = "Medium" if attribution_level in ("HIGH", "MEDIUM") else "Low"
        else:
            priority = "Low"
        caveats.append("Priority mapping is a provisional demonstration rule, not validated.")

    if onrr["status"] == "OBSERVATION_OPPORTUNITY_UNKNOWN":
        codes.append("OBSERVATION_OPPORTUNITY_UNKNOWN")
    caveats += ["Detection is not a confirmed fire; priority is not a confirmed incident.",
                "Event duration is the span between satellite snapshots, not continuous burning."]
    if not is_real:
        caveats.insert(0, MODE_WORDING[mode])

    why = []
    if base["status"] == "OK":
        why.append({"category": "thermal", "signal": "robust_frp_anomaly", "value": base["robust_z"],
                    "interpretation": f"FRP {base['target_value_mw']:.1f} MW vs facility-source median {base['median_mw']:.1f} MW "
                                      f"(MAD {base['mad_mw']:.2f}, method {base['method']}, n={base['n_eligible']})"})
    else:
        why.append({"category": "thermal", "signal": "robust_frp_anomaly", "value": None,
                    "interpretation": f"not computed: {base['status']} - {base.get('reason', '')}"})
    why.append({"category": "temporal", "signal": "onrr",
                "value": onrr.get("onrr"),
                "interpretation": ("ONRR computed from opportunity layer" if onrr.get("onrr") is not None
                                   else "not computed: observation opportunity unknown; missing detections are not inactivity")})
    why.append({"category": "historical", "signal": "recurrence_class", "value": profile["recurrence_class"],
                "interpretation": f"{profile['distinct_active_days']} active days over {profile['span_days_inclusive']} days "
                                  "(descriptive only; not persistence evidence)"})
    why.append({"category": "facility", "signal": "attribution", "value": facility_status,
                "interpretation": facility_wording})

    directions = []
    if base.get("robust_z") is not None:
        directions.append(base["robust_z"] > 0)
    if pdev.get("p_dev") is not None:
        directions.append(pdev["p_dev"] > 0)
    if len(directions) < 2:
        agreement = {"level": "NOT_APPLICABLE", "basis": "fewer than two computable abnormality components"}
    else:
        agreement = {"level": "AGREE" if len(set(directions)) == 1 else "DISAGREE",
                     "basis": "direction (above/below own baseline) of computable components"}

    beh_conf_reasons = []
    if base["status"] != "OK":
        beh_conf_reasons.append(base["status"])
    if onrr["status"] != "OK":
        beh_conf_reasons.append(onrr["status"])
    if base["status"] == "OK" and onrr["status"] == "OK":
        beh_level = "HIGH" if opportunity and opportunity.cloud_screened else "MEDIUM"
        if beh_level == "MEDIUM":
            beh_conf_reasons.append("OPPORTUNITY_NOT_CLOUD_SCREENED")
    elif base["status"] != "OK" and onrr["status"] != "OK":
        beh_level = "UNKNOWN"
    else:
        beh_level = "LOW"

    lastobs = ev_obs[-1].timestamp_utc
    obs_list = [o.to_dict() | {"label": lab_obs} for o in ev_obs[-max_observations_listed:]]
    versions = sorted({o.version_raw for o in ev_obs if o.version_raw})
    frps = [o.frp_mw for o in ev_obs if o.frp_mw is not None]
    obj = {
        "identity": {
            "event_id": ev.event_id, "source_id": ev.source_id,
            "source_record_ids": [o.observation_id for o in ev_obs][-max_observations_listed:],
            "start_utc": _iso(ev.start_utc), "end_utc": _iso(ev.end_utc), "state": ev.state,
            "mode": mode.value, "profile_version": f"pv-{mode.value}-{result.as_of_utc:%Y%m%d}",
            "label": lab_obs, "location_name": None,
        },
        "location": {"centroid": [ev.centroid[0], ev.centroid[1]], "label": "D"},
        "observations": obs_list,
        "observations_truncated": len(ev_obs) > max_observations_listed,
        "observation_evidence": {
            "count": len(ev_obs),
            "frp_mw": ({"min": min(frps), "max": max(frps), "mean": sum(frps) / len(frps)} if frps else None),
            "sensor": ", ".join(sorted({o.sensor_label for o in ev_obs if o.sensor_label})) or None,
            "confidence_classes": _detection_confidence(ev_obs).get("counts"), "label": lab_obs,
        },
        "temporal_evidence": {k: profile[k] for k in ("distinct_active_days", "span_days_inclusive", "gap_days",
                                                      "recurrence_class", "naive_detection_day_fraction")},
        "spatial_evidence": {"source_extent_m": src.extent_m, "event_bbox": ev.bbox,
                             "n_observations_in_source": len(src_obs), "label": "D"},
        "source_characterization": ({
            **characterization, "g4_gate": {"passed": g4_pass, "label": "C", "reasons": g4_reasons}}
            if characterization else {
            "source_class": None, "industrial_subclass": None, "class_probabilities": None,
            "status": "NOT_COMPUTED", "label": "NOT COMPUTED - no trained or validated classifier",
            "g4_gate": {"passed": False, "label": "C", "status": "UNEVALUATED", "reasons": g4_reasons}}),
        "facility_attribution": (facility if facility else {
            "candidate_facility_id": None, "candidate_facility_type": None, "status": "NOT_COMPUTED",
            "reason": "facility association was not supplied to the assessment",
            "spatial_score": None, "attribution_confidence": None,
            "alternative_candidates": [], "ambiguity_flag": None}),
        "land_context_evidence": {"status": "NOT_COMPUTED", "reason": "no land-cover provider configured; value to be established by ablation"},
        "historical_context": {
            "stratum": base.get("stratum"), "eligible_detections": base.get("n_eligible"),
            "sufficiency": ("sufficient" if base["status"] in ("OK", "DEGENERATE_BASELINE") else base["status"]),
            "excluded": [f"{k}: {v}" for k, v in sorted(base.get("excluded_counts", {}).items())],
            "label": "D"},
        "historical_behaviour": profile,
        "persistence": {
            "D_detect": onrr["D_detect"], "D_possible": onrr.get("D_possible"), "onrr": onrr.get("onrr"),
            "status": onrr["status"], "hist_median": pdev.get("hist_median"), "hist_mad": pdev.get("hist_mad"),
            "persistence_deviation": pdev.get("p_dev"), "p_norm": pdev.get("p_norm"),
            "caveats": onrr.get("caveats", []), "label": "D"},
        "thermal_anomaly": {
            "status": base["status"], "median_frp_mw": base.get("median_mw"), "mad_mw": base.get("mad_mw"),
            "frp_today_mw": base.get("target_value_mw"), "robust_z": base.get("robust_z"),
            "t_anom": base.get("t_anom"), "method": base.get("method"), "n_eligible": base.get("n_eligible"),
            "aggregator": base["aggregator"], "excluded_counts": base.get("excluded_counts"),
            "reason": base.get("reason"), "label": "D; aggregation and mapping calibration-open"},
        "spatial_behaviour": {"within_historical_footprint": None, "deviation_score": None,
                              "reason": "not computed in this phase; excluded from fusion"},
        "fusion": {"components": comps, "weights": ({k: w[k] for k in comps} if comps else {}),
                   "weights_label": "equal prototype weighting - NOT validated", "F": F,
                   "status": "OK" if F is not None else "INSUFFICIENT_EVIDENCE"},
        "ml_evidence": {"status": "NOT_AVAILABLE", "reason": "no validated labels; no trained model"},
        "verification_evidence": {"status": "NOT_AVAILABLE", "reason": "no independent verification linked"},
        "decision": {
            "behaviour_status": status, "priority": priority, "alert_state": None,
            "abstention": abstain,
            "label": (thresholds.label if thresholds else "No calibrated thresholds: system abstains"),
            "reason_codes": codes, "caveats": caveats},
        "why_flagged": why,
        "uncertainty": {
            "detection_confidence": _detection_confidence(ev_obs),
            "behaviour_persistence_confidence": {"level": beh_level, "reasons": beh_conf_reasons},
            "classification_confidence": {"level": "UNKNOWN", "basis": "no classifier"} if not characterization
            else {"level": "UNKNOWN", "basis": "supplied by caller; calibration not assessed"},
            "facility_attribution_confidence": {"level": attribution_level if facility else "UNKNOWN",
                                                "basis": facility_wording},
            "evidence_agreement": agreement,
            "investigation_priority": {"value": priority, "basis": "separate from every confidence above"},
            "allowed_abstentions": ["UNKNOWN", "INSUFFICIENT_EVIDENCE", "INSUFFICIENT_HISTORY", "REVIEW_REQUIRED"],
            "abstention": abstain},
        "provenance": {
            "data_mode": mode.value, "wording": MODE_WORDING[mode],
            "source_products": sorted({o.source_product for o in ev_obs if o.source_product}),
            "source_data_versions": versions,
            "satellites": sorted({o.satellite for o in ev_obs if o.satellite}),
            "instruments": sorted({o.instrument for o in ev_obs if o.instrument}),
            "first_acquisition_utc": _iso(ev_obs[0].timestamp_utc), "last_acquisition_utc": _iso(lastobs),
            "source_available_utc": None,
            "source_available_note": "FIRMS publication time is not in the CSV; unknown unless recorded at download",
            "ingested_utc": _iso(max(o.ingested_utc for o in ev_obs if o.ingested_utc)) if any(o.ingested_utc for o in ev_obs) else None,
            "processed_utc": _iso(processed_utc), "as_of_utc": _iso(result.as_of_utc),
            "observation_age_hours_at_as_of": round((result.as_of_utc - lastobs).total_seconds() / 3600, 2),
            "observation_age_hours_at_processing": round((processed_utc - lastobs).total_seconds() / 3600, 2),
            "source_files": sorted({o.source_file for o in ev_obs if o.source_file}),
            "pipeline_version": PIPELINE_VERSION, "schema_version": SCHEMA_VERSION, "model_version": None,
            "validation": ({k: validation_stats[k] for k in ("status", "n_input", "n_valid", "n_excluded", "file_sha256")
                            if k in validation_stats} if validation_stats else None),
            "facility_dataset": (facility.get("facility_dataset") if facility else None),
            "facility_parameters": (facility.get("parameters") if facility else None),
        },
        "persistent_source": bool(profile["recurrence_class"] == "RECURRENT_DETECTIONS" and onrr.get("onrr") is not None),
    }
    return obj
