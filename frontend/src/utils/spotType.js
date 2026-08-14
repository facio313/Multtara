export const SPOT_TYPE_LABELS = {
  sea: '바다',
  pool: '수영장',
  hotspring: '온천',
  valley: '계곡',
  lake: '호수',
  waterpark: '워터파크',
  waterfall: '폭포',
  tidal_flat: '갯벌',
  riverside: '강변',
};

export const ACTIVITY_LABELS = {
  swim: '물놀이',
  surf: '서핑',
  relax: '물멍',
  mudflat: '갯벌',
  onsen: '온천',
  rafting: '래프팅',
};

export function spotTypeLabel(type) {
  return SPOT_TYPE_LABELS[type] || type;
}
