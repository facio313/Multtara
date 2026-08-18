export const API_SPOT_TYPES = Object.freeze([
  'beach',
  'river',
  'valley',
  'hotspring',
  'pool',
  'waterpark',
  'lake',
  'waterfall',
  'riverside',
  'reservoir',
  'mudflat',
  'coastal_road',
]);

export const spotTypeMeta = Object.freeze({
  beach: Object.freeze({ type: 'beach', label: '해변', icon: '🌊', environment: 'marine_beach' }),
  river: Object.freeze({ type: 'river', label: '강·하천', icon: '🏞️', environment: 'inland_water' }),
  valley: Object.freeze({ type: 'valley', label: '계곡', icon: '💧', environment: 'inland_water' }),
  hotspring: Object.freeze({ type: 'hotspring', label: '온천', icon: '♨️', environment: 'licensed_facility' }),
  pool: Object.freeze({ type: 'pool', label: '수영장', icon: '🏊', environment: 'licensed_facility' }),
  waterpark: Object.freeze({ type: 'waterpark', label: '워터파크', icon: '💦', environment: 'licensed_facility' }),
  lake: Object.freeze({ type: 'lake', label: '호수', icon: '🫧', environment: 'inland_water' }),
  waterfall: Object.freeze({ type: 'waterfall', label: '폭포', icon: '🌊', environment: 'waterside' }),
  riverside: Object.freeze({ type: 'riverside', label: '수변', icon: '🌿', environment: 'inland_water' }),
  reservoir: Object.freeze({ type: 'reservoir', label: '저수지', icon: '💧', environment: 'inland_water' }),
  mudflat: Object.freeze({ type: 'mudflat', label: '갯벌', icon: '🦀', environment: 'tidal_flat' }),
  coastal_road: Object.freeze({ type: 'coastal_road', label: '해안도로', icon: '🚗', environment: 'marine_beach' }),
});

const LEGACY_ALIASES = Object.freeze({
  sea: 'beach',
  tidal_flat: 'mudflat',
});

const ACTIVITY_ENVIRONMENTS = Object.freeze({
  swim: new Set(['marine_beach', 'inland_water']),
  surf: new Set(['marine_beach']),
  relax: new Set(['marine_beach']),
  mudflat: new Set(['tidal_flat']),
  onsen: new Set(['licensed_facility']),
  rafting: new Set(['inland_water']),
});

export const spotTypeOptions = Object.freeze(
  API_SPOT_TYPES.map((id) => Object.freeze({ id, label: spotTypeMeta[id].label })),
);

export function canonicalSpotType(value) {
  const normalized = String(value ?? '').trim().toLowerCase();
  const canonical = LEGACY_ALIASES[normalized] ?? normalized;
  return Object.hasOwn(spotTypeMeta, canonical) ? canonical : null;
}

export function getSpotTypeMeta(value) {
  const canonical = canonicalSpotType(value);
  if (canonical) return spotTypeMeta[canonical];
  return {
    type: 'unknown',
    label: '기타 물가',
    icon: '💧',
    environment: 'waterside',
  };
}

export function spotTypeSupportsActivity(spotType, activity) {
  const meta = getSpotTypeMeta(spotType);
  return ACTIVITY_ENVIRONMENTS[activity]?.has(meta.environment) ?? false;
}
