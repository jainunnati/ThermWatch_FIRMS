import { ALERT_RULE } from '../config/app.js';

const REASON_TEXT = {
  PIHS_CANDIDATE: 'PIHS candidate',
  RECENT_ACTIVITY: 'recent activity',
  INTENSITY_ABOVE_OWN_BASELINE: 'intensity above own FRP mean',
  LONG_RUNNING: 'long-running',
  FACILITY_CONTEXT: 'facility context',
};

/**
 * Alerts = real ranked sources whose Alert Priority tier is in ALERT_RULE.tiers
 * (alert-priority-v1). One alert per source, in rank order. A triage prompt, not a confirmed incident.
 */
export function deriveAlerts(events) {
  const out = [];
  for (const e of events) {
    if (!ALERT_RULE.tiers.includes(e.priority)) continue;
    const s = e.real?.source;
    const codes = s?.intelligence?.alert_reason_codes || [];
    const reason = s
      ? `Alert Priority ${s.intelligence.alert_tier} ${s.intelligence.alert_priority_score.toFixed(3)} · ${codes.map((c) => REASON_TEXT[c] || c).join(', ') || 'no reason codes'}`
      : `Alert Priority ${String(e.priority).toUpperCase()} · rank #${e.rank}${e.persistentSource ? ' · PIHS candidate' : ''} (reason codes packaged for top-300 only)`;
    out.push({ id: `ALERT-${e.id}`, eventId: e.id, rank: e.rank, state: 'new', createdUtc: e.endUtc, reason });
  }
  return out;
}

export async function listAlerts(events) {
  return deriveAlerts(events);
}
