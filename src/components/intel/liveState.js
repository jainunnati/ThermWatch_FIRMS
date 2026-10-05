// Live-vs-historical honesty rules (plain JS so it is unit-testable without a build).
export const LIVE_MAX_AGE_H = 6;
export function liveState(live, now = Date.now()) {
  if (!live) return { cls: 'off', text: '○ Live feed unavailable (no live artifact yet)' };
  if (live.mode !== 'LIVE') return { cls: 'off', text: '○ Live artifact is not in LIVE mode' };
  if (live.pipeline_status === 'LIVE_FEED_UNAVAILABLE') return { cls: 'off', text: `○ LIVE FEED UNAVAILABLE: ${live.pipeline_status_detail || 'unknown reason'}` };
  const age = (now - Date.parse(live.generated_at)) / 3.6e6;
  if (!(age >= 0)) return { cls: 'off', text: '○ Live artifact has an invalid timestamp' };
  if (age > LIVE_MAX_AGE_H) return { cls: 'stale', text: `◐ LIVE (stale): last update ${live.generated_at}` };
  return { cls: 'on', text: `● LIVE: last update ${live.generated_at}` };
}
