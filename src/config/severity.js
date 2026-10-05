// ---------------------------------------------------------------------------
// SEVERITY — single source of truth for marker visual treatment.
// Severity answers "how serious is it?" via size / halo / pulse only.
// It never changes the classification colour.
// ---------------------------------------------------------------------------

export const SEVERITIES = {
  low: {
    key: 'low',
    label: 'Low',
    markerSize: 16,
    treatment: 'static',
    description: 'Normal-size static marker',
  },
  medium: {
    key: 'medium',
    label: 'Medium',
    markerSize: 20,
    treatment: 'halo',
    description: 'Larger marker with a static halo',
  },
  high: {
    key: 'high',
    label: 'High',
    markerSize: 24,
    treatment: 'pulse',
    description: 'Largest marker with an expanding pulse (static ring when reduced motion is on)',
  },
};

export const SEVERITY_ORDER = ['low', 'medium', 'high'];
export const SEVERITY_RANK = { low: 1, medium: 2, high: 3 };

export function severityKeyFromLabel(label) {
  const key = String(label ?? '').trim().toLowerCase();
  if (key === 'high' || key === 'critical') return 'high';
  if (key === 'medium' || key === 'warning' || key === 'moderate') return 'medium';
  if (key === 'low') return 'low';
  return null;
}

export function severityOf(key) {
  return SEVERITIES[key] || null;
}
