// Display formatting helpers. Missing values are shown as "—", never as 0.

export const DASH = '—';

export function isMissing(v) {
  return v === null || v === undefined || v === '' || (typeof v === 'number' && !Number.isFinite(v));
}

export function fmtNum(v, digits = 2) {
  if (isMissing(v)) return DASH;
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toFixed(digits);
}

export function fmtUtc(iso, { withSeconds = false } = {}) {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return DASH;
  const s = d.toISOString();
  return `${s.slice(0, 10)} ${s.slice(11, withSeconds ? 19 : 16)} UTC`;
}

export function fmtDateUtc(iso) {
  if (!iso) return DASH;
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? d.toISOString().slice(0, 10) : DASH;
}

export function fmtCoord(lat, lng, digits = 4) {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return DASH;
  const ns = lat >= 0 ? 'N' : 'S';
  const ew = lng >= 0 ? 'E' : 'W';
  return `${Math.abs(lat).toFixed(digits)}° ${ns}, ${Math.abs(lng).toFixed(digits)}° ${ew}`;
}

export function fmtRelative(iso, now = Date.now()) {
  const t = new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const mins = Math.round((now - t) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 60) return `${days} days ago`;
  return `${Math.round(days / 30)} months ago`;
}

export function fmtHoursSpan(startIso, endIso) {
  const a = new Date(startIso).getTime();
  const b = new Date(endIso).getTime();
  if (!Number.isFinite(a) || !Number.isFinite(b)) return DASH;
  return `${((b - a) / 3600000).toFixed(1)} h`;
}
