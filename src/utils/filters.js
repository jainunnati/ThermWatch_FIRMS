// Layer filter logic. Within a group: OR. Across groups: AND.
import { CLASSIFICATION_ORDER } from '../config/classification.js';
import { SEVERITY_ORDER } from '../config/severity.js';
import { INDUSTRIAL_TYPE_ORDER } from '../config/industrialTypes.js';

const allOn = (keys) => Object.fromEntries(keys.map((k) => [k, true]));

export function defaultFilters() {
  return {
    classes: allOn(CLASSIFICATION_ORDER),
    // Default map = alert points only (Alert Priority HIGH + MEDIUM). LOW-tier ranked
    // monitored sources stay loaded and are revealed with the existing "Low" layer toggle.
    severities: { ...allOn(SEVERITY_ORDER), low: false },
    industrialTypes: allOn(INDUSTRIAL_TYPE_ORDER),
    // Behaviour toggles narrow the map ("show only"). None checked = no narrowing.
    behaviours: { abnormal: false, elevated: false, persistent: false },
    // Facilities are optional context (existing Layers toggle). Out-of-range sources are
    // not drawn by default, so the time control changes what is visible.
    context: { facilities: false, landcover: false },
    historical: { events: false, facilityActivity: true },
  };
}

export function eventMatchesFilters(event, f) {
  const cls = event.classification?.key || 'unknown';
  if (!f.classes[cls]) return false;

  // Events with no supplied severity are shown with the Low treatment and
  // filtered as Low, but labelled "not supplied" in the investigation view.
  const sev = event.severity || 'low';
  if (!f.severities[sev]) return false;

  if (cls === 'industrial') {
    const t = event.classification?.industrialType || 'other';
    if (!f.industrialTypes[t]) return false;
  }

  const wanted = Object.entries(f.behaviours).filter(([, on]) => on).map(([k]) => k);
  if (wanted.length) {
    const ok = wanted.some((k) => (k === 'persistent' ? event.persistentSource === true : event.behaviour === k));
    if (!ok) return false;
  }
  return true;
}

export function countBy(events, keyFn) {
  const out = {};
  for (const e of events) {
    const k = keyFn(e);
    if (k == null) continue;
    out[k] = (out[k] || 0) + 1;
  }
  return out;
}
