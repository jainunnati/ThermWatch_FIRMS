// Industrial sub-type vocabulary (Level-2 source characterization and facility type).

export const INDUSTRIAL_TYPES = {
  refinery: { key: 'refinery', label: 'Refinery', aliases: ['refinery', 'oil refinery'] },
  petrochemical: { key: 'petrochemical', label: 'Petrochemical', aliases: ['petrochemical', 'petrochemical facility'] },
  thermal_power: { key: 'thermal_power', label: 'Thermal Power', aliases: ['thermal power', 'thermal power plant', 'power plant', 'coal power'] },
  steel: { key: 'steel', label: 'Iron & Steel', aliases: ['steel', 'iron & steel', 'iron and steel', 'steel industry', 'steel plant'] },
  mining: { key: 'mining', label: 'Mining', aliases: ['mining', 'mining area', 'mine', 'coalfield'] },
  lng_gas: { key: 'lng_gas', label: 'LNG / Gas', aliases: ['lng', 'lng / gas', 'lng/gas', 'lng terminal', 'gas', 'gas processing'] },
  other: { key: 'other', label: 'Other Industrial', aliases: ['other', 'other industrial', 'other/unknown industrial', 'industrial facility'] },
};

export const INDUSTRIAL_TYPE_ORDER = ['refinery', 'petrochemical', 'thermal_power', 'steel', 'mining', 'lng_gas', 'other'];

export function industrialTypeKey(label) {
  const key = String(label ?? '').trim().toLowerCase();
  if (!key) return null;
  for (const t of INDUSTRIAL_TYPE_ORDER) {
    if (INDUSTRIAL_TYPES[t].aliases.includes(key)) return t;
  }
  if (key.includes('refin')) return 'refinery';
  if (key.includes('petro')) return 'petrochemical';
  if (key.includes('power')) return 'thermal_power';
  if (key.includes('steel')) return 'steel';
  if (key.includes('min') || key.includes('coal')) return 'mining';
  if (key.includes('lng') || key.includes('gas')) return 'lng_gas';
  return 'other';
}

export function industrialTypeLabel(key) {
  return INDUSTRIAL_TYPES[key]?.label || 'Other Industrial';
}
