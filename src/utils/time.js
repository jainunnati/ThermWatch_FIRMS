// Time helpers. All filtering uses acquisition timestamps in UTC.

/** Parse an <input type="datetime-local"> value as UTC. */
export function parseUtcInput(value) {
  if (!value) return null;
  const t = new Date(`${value.length === 16 ? `${value}:00` : value}Z`).getTime();
  return Number.isFinite(t) ? t : null;
}

export function toUtcInput(ms) {
  const d = new Date(ms);
  if (!Number.isFinite(d.getTime())) return '';
  return d.toISOString().slice(0, 16);
}

/** Every acquisition time we know for an event (never synthesised). */
export function acquisitionTimes(event) {
  const times = (event?.observations || [])
    .map((o) => new Date(o.timestampUtc).getTime())
    .filter(Number.isFinite);
  if (times.length) return times;
  return [event?.startUtc, event?.endUtc]
    .map((v) => new Date(v).getTime())
    .filter(Number.isFinite);
}

export function latestAcquisition(event) {
  const times = acquisitionTimes(event);
  return times.length ? Math.max(...times) : null;
}

/**
 * Does the event have at least one acquisition inside the active time filter?
 * Live: window relative to now (null = all). Historical: explicit UTC range.
 */
export function eventMatchesTime(event, time, now = Date.now()) {
  const times = acquisitionTimes(event);
  // Ranked sources whose acquisition times are not packaged have no time to filter on:
  // they are shown only under "All available" and never assigned an invented time.
  if (!times.length) return time.mode === 'live' && time.liveWindowHours == null;
  if (time.mode === 'historical') {
    const from = parseUtcInput(time.fromUtc);
    const to = parseUtcInput(time.toUtc);
    if (from !== null && to !== null && from > to) return false;
    return times.some((t) => (from === null || t >= from) && (to === null || t <= to));
  }
  if (time.liveWindowHours == null) return true;
  const cutoff = now - time.liveWindowHours * 3600000;
  return times.some((t) => t >= cutoff);
}

export function historicalRangeError(time) {
  if (time.mode !== 'historical') return null;
  const from = parseUtcInput(time.fromUtc);
  const to = parseUtcInput(time.toUtc);
  if (from !== null && to !== null && from > to) return '"From" is after "To".';
  return null;
}
