// Behaviour status and investigation priority vocabularies (Final Architecture §13).
// These are display vocabularies only; the frontend never computes them.

export const BEHAVIOUR_STATUSES = {
  abnormal: { key: 'abnormal', label: 'Abnormal', tone: 'danger' },
  elevated: { key: 'elevated', label: 'Elevated', tone: 'warn' },
  normal: { key: 'normal', label: 'Normal', tone: 'ok' },
  insufficient: { key: 'insufficient', label: 'Insufficient History / Evidence', tone: 'muted' },
  not_applicable: { key: 'not_applicable', label: 'Not applicable (gated out)', tone: 'muted' },
  not_assessed: { key: 'not_assessed', label: 'Not assessed', tone: 'muted' },
};

export function behaviourKeyFromLabel(label) {
  const key = String(label ?? '').trim().toLowerCase();
  if (key === 'abnormal') return 'abnormal';
  if (key === 'elevated') return 'elevated';
  if (key === 'normal') return 'normal';
  if (key.startsWith('insufficient')) return 'insufficient';
  return null;
}

export const PRIORITIES = {
  high: { key: 'high', label: 'High', tone: 'danger' },
  medium: { key: 'medium', label: 'Medium', tone: 'warn' },
  low: { key: 'low', label: 'Low', tone: 'ok' },
};

export function priorityKeyFromLabel(label) {
  const key = String(label ?? '').trim().toLowerCase();
  return PRIORITIES[key] ? key : null;
}

// Behaviour layer filters. "persistent" only matches events that carry an
// explicit persistent-source flag from the backend — never inferred here.
export const BEHAVIOUR_FILTERS = {
  abnormal: { key: 'abnormal', label: 'Abnormal activity' },
  elevated: { key: 'elevated', label: 'Elevated activity' },
  persistent: { key: 'persistent', label: 'Persistent sources' },
};
