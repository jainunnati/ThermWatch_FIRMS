// Operational (non-scientific) UI configuration.

export const INDIA_VIEW = { center: { lat: 22.5, lng: 80.5 }, zoom: 5 };
export const FOCUS_ZOOM = 14;

// Recency windows, relative to "now". "All" is the default because satellite
// observation is intermittent and the packaged real dataset ends 2026-10-01.
export const LIVE_WINDOWS = [
  { value: null, label: 'All available' },
  { value: 24, label: 'Last 24 h' },
  { value: 72, label: 'Last 72 h' },
  { value: 24 * 7, label: 'Last 7 days' },
  { value: 24 * 30, label: 'Last 30 days' },
];

// Alert criterion: real Alert Priority tier (alert-priority-v1). Tiers:
// HIGH ≥ 0.60 · MEDIUM ≥ 0.40. One alert per source.
export const ALERT_RULE = {
  tiers: ['high'],
};
