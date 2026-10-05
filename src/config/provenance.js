// Provenance of every record shown in the UI. All records are real ThermWatch
// pipeline outputs; the kinds only say how much of the record is packaged.

export const DATA_KINDS = {
  real_detailed: {
    key: 'real_detailed',
    label: 'Real source · full record',
    banner: 'Real FIRMS-derived ThermWatch source with full event-level record (top-300 by Alert Priority).',
  },
  real_ranked: {
    key: 'real_ranked',
    label: 'Real source · ranked point',
    banner: 'Real FIRMS-derived ThermWatch source from the top-3,000 Alert Priority layer. Event-level detail is not packaged in this build.',
  },
};
