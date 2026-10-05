# LEAKAGE_AUDIT_V1

## Per-column verdict
| column | used as ML feature | verdict | basis |
|---|---|---|---|
| source_id | NO | EXCLUDED (PASS) | identifier; hash of anchor key, no predictive meaning; join key only |
| centroid_lat | NO | EXCLUDED (PASS) | raw location acts as a site/region proxy; used only for grouping |
| centroid_lon | NO | EXCLUDED (PASS) | as centroid_lat |
| first_seen_utc | NO | EXCLUDED (PASS) | absolute date encodes data period/stream, not source type |
| last_seen_utc | NO | EXCLUDED (PASS) | as first_seen_utc |
| grade_composition | NO | EXCLUDED (PASS) | data-processing provenance, not physics |
| detection_count | YES | PASS | LOW |
| active_days | YES | PASS | LOW |
| event_count | YES | PASS | LOW |
| duration_days | YES | PASS | LOW |
| detections_per_active_day | YES | PASS | LOW |
| max_gap_d | YES | PASS | LOW |
| median_gap_d | YES | PASS | LOW |
| span_frac | YES | PASS | LOW |
| modal_month_frac | YES | PASS | LOW |
| frp_mean | YES | PASS | LOW |
| frp_median | YES | PASS | LOW |
| frp_max | YES | PASS | LOW |
| frp_cv | YES | PASS | LOW |
| ti4_median | YES | PASS | LOW |
| ti4_max | YES | PASS | LOW |
| ti4_sat_frac | YES | PASS | LOW |
| night_frac | YES | PASS | LOW |
| conf_high_frac | YES | PASS | LOW |
| spatial_extent_m | YES | PASS | LOW |
| dist_nearest_steel_km | YES | PASS | MEDIUM: GEM distances also generated the candidate frame; allowed as FEATURE (never as label); report ablation |
| dist_nearest_power_km | YES | PASS | MEDIUM (see above) |
| dist_nearest_oilgas_km | YES | PASS | MEDIUM (see above) |
| dist_nearest_any_km | YES | PASS | MEDIUM (see above) |
| candidate_count_5km | YES | PASS | MEDIUM (see above) |
| candidate_type_count_5km | YES | PASS | MEDIUM (see above) |
| competing_facility_count_2km | YES | PASS | MEDIUM (see above) |
| osm_status | NO | EXCLUDED (PASS) | missingness indicator only; coverage is a fetch artefact (pilot87 tiles) |
| osm_count_industrial_landuse_1000m | YES | PASS | LOW (empty=unknown) |
| osm_count_power_plant_1000m | YES | PASS | LOW |
| osm_count_farmland_1000m | YES | PASS | LOW |
| osm_count_forest_1000m | YES | PASS | LOW |
| wc_status | NO | EXCLUDED (PASS) | not downloaded (always MISSING) |

## Fields inspected and confirmed absent from the feature table (PASS)
candidate_group, candidate_subgroup, candidate_reason, sampling weights/inclusion probabilities/strata, candidate ordering/evidence_priority, candidate IDs, LABEL_FACTORY/EXPANSION decisions, REVIEW status, annotation decisions (MS/HM), adjudication (mh), evidence conclusions, research results, AI hypothesis/attribution scores, FIRMS type fractions, registry/source IDs, site_complex_id (used only for grouping).

## Conditional risk (flagged, not failed)
- **GEM distance features**: the candidate frame and any future facility-context labels are derived from GEM proximity. They are legal as features, but if labels are proximity-anchored the model can relearn the candidate rule. **Required: report every future model with and without GEM features (ablation).**
- **Persistence features**: the confounding audit showed persistence separates proximity-derived steel/coal groups. Any future evaluation must include the matched/persistence-controlled analysis.
- **OSM coverage**: only 46/6,892 sources have OSM context (pilot tiles). `osm_status` is excluded, so fetch coverage cannot become a signal; OSM counts are NaN elsewhere.

Verified by `test_ml_v1.test_no_forbidden_features` and `test_missing_context_is_empty_not_zero`.
