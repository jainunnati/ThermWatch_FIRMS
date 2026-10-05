// ---------------------------------------------------------------------------
// SOURCE CLASSIFICATION — single source of truth for marker colour.
// Colour answers "what is it likely to be?" and NEVER changes with severity.
// ---------------------------------------------------------------------------

export const CLASSIFICATIONS = {
  industrial: {
    key: 'industrial',
    label: 'Industrial',
    color: '#D92D20',
    aliases: ['industrial', 'industrial fire', 'industrial-area anomaly', 'persistent thermal source'],
  },
  agricultural: {
    key: 'agricultural',
    label: 'Agricultural',
    color: '#EF7A0A',
    aliases: ['agricultural', 'agricultural burn', 'agricultural burning', 'agricultural/land fire', 'land fire'],
  },
  natural: {
    key: 'natural',
    label: 'Natural / Forest',
    color: '#16A34A',
    aliases: ['natural', 'forest', 'natural wildfire', 'natural fire', 'forest fire', 'forest/natural', 'natural / forest fire'],
  },
  unknown: {
    key: 'unknown',
    label: 'Unknown / Other',
    color: '#2563EB',
    aliases: ['unknown', 'other', 'other/unknown', 'unclassified', 'needs review'],
  },
};

export const CLASSIFICATION_ORDER = ['industrial', 'agricultural', 'natural', 'unknown'];

/** Map any backend/pipeline label onto one of the four classification keys. */
export function classificationKeyFromLabel(label) {
  const key = String(label ?? '').trim().toLowerCase();
  if (!key) return 'unknown';
  for (const c of CLASSIFICATION_ORDER) {
    if (CLASSIFICATIONS[c].aliases.includes(key)) return c;
  }
  if (key.includes('industrial')) return 'industrial';
  if (key.includes('agri')) return 'agricultural';
  if (key.includes('forest') || key.includes('natural') || key.includes('wildfire')) return 'natural';
  return 'unknown';
}

export function classificationOf(key) {
  return CLASSIFICATIONS[key] || CLASSIFICATIONS.unknown;
}
