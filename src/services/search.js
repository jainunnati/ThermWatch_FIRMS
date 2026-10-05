import { parseCoordinateQuery } from '../utils/geo.js';

/**
 * Client-side search over the loaded real data: source IDs, facilities (name, type, registry
 * kind — e.g. "Hazira", "steel", "coal") and ranked sources by their nearest documented
 * facility / attribution context. Exact source-ID matches come first, then facilities, then
 * sources in Alert Priority rank order. Nothing is invented: unmatched queries return nothing.
 */
export function searchAll(query, { events, facilities }, limit = 8) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return [];
  const out = [];
  const coord = parseCoordinateQuery(q);
  if (coord) out.push({ kind: 'coordinate', id: `coord-${coord.lat},${coord.lng}`, label: `Go to ${coord.lat}, ${coord.lng}`, sublabel: 'Coordinates', ...coord });

  const evRow = (e) => ({ kind: 'event', id: e.id, label: `${e.id} · ${e.locationName}`, sublabel: `Source · Alert Priority ${String(e.priority || '—').toUpperCase()} #${e.rank}${e.persistentSource ? ' · PIHS' : ''}`, lat: e.latitude, lng: e.longitude });
  const exact = events.find((e) => e.id.toLowerCase() === q);
  if (exact) out.push(evRow(exact));

  const facs = [];
  for (const f of facilities) {
    const hay = `${f.name} ${f.type} ${f.typeDetail || ''} ${f.locationLabel || ''} ${f.id}`.toLowerCase();
    if (hay.includes(q)) facs.push({ kind: 'facility', id: f.id, label: f.name, sublabel: `Facility · ${f.type}${f.nearbySources?.length ? ` · ${f.nearbySources.length} ranked source${f.nearbySources.length > 1 ? 's' : ''} ≤ 5 km` : ''}`, lat: f.latitude, lng: f.longitude });
  }
  const evs = [];
  for (const e of events) {
    if (e === exact) continue;
    const hay = `${e.id} ${e.locationName} ${e.facility?.name || ''} ${e.classification.label} ${e.classification.sourceLabel || ''} ${e.classification.industrialSubclassLabel || ''}`.toLowerCase();
    if (hay.includes(q)) evs.push(e);
  }
  evs.sort((a, b) => a.rank - b.rank);
  const nFac = Math.min(facs.length, Math.max(3, limit - out.length - evs.length));
  out.push(...facs.slice(0, nFac), ...evs.map(evRow));
  return out.slice(0, limit);
}
