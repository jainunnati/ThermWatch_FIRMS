# FEATURE_MANIFEST_V1 (ml_v1-features-1; generated from build_features_v1.MANIFEST)

| feature | group | definition | source | prediction-time | allowed for ML | reason if excluded | leakage risk |
|---|---|---|---|---|---|---|---|
| source_id | id | registry source identifier | Step D | YES | NO | identifier; hash of anchor key, no predictive meaning; join key only | LOW (excluded) |
| centroid_lat | spatial | source centroid latitude | Step D | YES | NO | raw location acts as a site/region proxy; used only for grouping | HIGH if used |
| centroid_lon | spatial | source centroid longitude | Step D | YES | NO | as centroid_lat | HIGH if used |
| first_seen_utc | temporal | first detection time | Step D | YES | NO | absolute date encodes data period/stream, not source type | MEDIUM |
| last_seen_utc | temporal | last detection time | Step D | YES | NO | as first_seen_utc | MEDIUM |
| grade_composition | provenance | SP/NRT mix | Step D | YES | NO | data-processing provenance, not physics | MEDIUM |
| detection_count | thermal | number of member detections | registry/raw | YES | YES |  | LOW |
| active_days | thermal | distinct UTC dates with a detection | raw | YES | YES |  | LOW |
| event_count | thermal | registry events of the source | Step D | YES | YES |  | LOW |
| duration_days | thermal | last - first detection, days | raw | YES | YES |  | LOW |
| detections_per_active_day | thermal | detection_count / active_days | derived | YES | YES |  | LOW |
| max_gap_d | thermal | max gap between consecutive detections (days); empty if 1 detection | raw | YES | YES |  | LOW |
| median_gap_d | thermal | median gap between consecutive detections (days) | raw | YES | YES |  | LOW |
| span_frac | thermal | active_days / (ceil(duration)+1) | raw | YES | YES |  | LOW |
| modal_month_frac | thermal | share of detections in the most frequent month (temporal concentration) | raw | YES | YES |  | LOW |
| frp_mean | thermal | mean FRP (MW) | raw | YES | YES |  | LOW |
| frp_median | thermal | median FRP (MW) | raw | YES | YES |  | LOW |
| frp_max | thermal | max FRP (MW) | raw | YES | YES |  | LOW |
| frp_cv | thermal | FRP coefficient of variation (std/mean); 0 if 1 detection | raw | YES | YES |  | LOW |
| ti4_median | thermal | median bright_ti4 (K) | raw | YES | YES |  | LOW |
| ti4_max | thermal | max bright_ti4 (K) | raw | YES | YES |  | LOW |
| ti4_sat_frac | thermal | share with bright_ti4 >= 367 K | raw | YES | YES |  | LOW |
| night_frac | thermal | share of night detections | raw | YES | YES |  | LOW |
| conf_high_frac | thermal | share with confidence = h | raw | YES | YES |  | LOW |
| spatial_extent_m | spatial | max distance from centroid to a member (m) | raw | YES | YES |  | LOW |
| dist_nearest_steel_km | context | GEM steel site distance (<=5 km, else empty) | GEM trackers | YES | YES |  | MEDIUM: GEM distances also generated the candidate frame; allowed as FEATURE (never as label); report ablation |
| dist_nearest_power_km | context | GEM coal plant distance | GEM trackers | YES | YES |  | MEDIUM (see above) |
| dist_nearest_oilgas_km | context | GEM oil/gas field distance | GEM trackers | YES | YES |  | MEDIUM (see above) |
| dist_nearest_any_km | context | nearest GEM site of any type | GEM trackers | YES | YES |  | MEDIUM (see above) |
| candidate_count_5km | context | GEM sites within 5 km | GEM trackers | YES | YES |  | MEDIUM (see above) |
| candidate_type_count_5km | context | distinct GEM site types within 5 km | GEM trackers | YES | YES |  | MEDIUM (see above) |
| competing_facility_count_2km | context | GEM sites within 2 km minus one | GEM trackers | YES | YES |  | MEDIUM (see above) |
| osm_status | context | OK / MISSING_NOT_FETCHED | OSM cache | YES | NO | missingness indicator only; coverage is a fetch artefact (pilot87 tiles) | HIGH (coverage bias) |
| osm_count_industrial_landuse_1000m | context | OSM industrial landuse within 1 km (empty if not fetched) | OSM | YES | YES |  | LOW (empty=unknown) |
| osm_count_power_plant_1000m | context | OSM power plants within 1 km | OSM | YES | YES |  | LOW |
| osm_count_farmland_1000m | context | OSM farmland within 1 km | OSM | YES | YES |  | LOW |
| osm_count_forest_1000m | context | OSM forest within 1 km | OSM | YES | YES |  | LOW |
| wc_status | context | WorldCover status | WorldCover | YES | NO | not downloaded (always MISSING) | n/a |

**30 ML features; 8 columns kept for joins/grouping/QA but excluded from ML.**

**Not implemented in v1 (documented rather than faked):** WorldCover features (tiles not downloaded); observation/source density; latitude-derived features (excluded: geographic proxy).
