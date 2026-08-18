const EARTH_RADIUS_KM = 6371.0088;

function validCoordinate(value, minimum, maximum) {
  const number = Number(value);
  return Number.isFinite(number) && number >= minimum && number <= maximum
    ? number
    : null;
}

export function normalizeCoordinates(value) {
  const lat = validCoordinate(value?.lat ?? value?.latitude, -90, 90);
  const lng = validCoordinate(value?.lng ?? value?.longitude, -180, 180);
  return lat === null || lng === null ? null : { lat, lng };
}

export function distanceKm(origin, destination) {
  const from = normalizeCoordinates(origin);
  const to = normalizeCoordinates(destination);
  if (!from || !to) return null;

  const toRadians = (degrees) => degrees * (Math.PI / 180);
  const latDelta = toRadians(to.lat - from.lat);
  const lngDelta = toRadians(to.lng - from.lng);
  const fromLat = toRadians(from.lat);
  const toLat = toRadians(to.lat);
  const haversine = (Math.sin(latDelta / 2) ** 2)
    + (Math.cos(fromLat) * Math.cos(toLat) * (Math.sin(lngDelta / 2) ** 2));
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(haversine)));
}

export function sortSpotsByDistance(spots, origin) {
  if (!normalizeCoordinates(origin)) return [...spots];
  return [...spots].sort((left, right) => {
    const leftDistance = distanceKm(origin, left);
    const rightDistance = distanceKm(origin, right);
    if (leftDistance === null && rightDistance === null) {
      return String(left?.name ?? '').localeCompare(String(right?.name ?? ''), 'ko-KR');
    }
    if (leftDistance === null) return 1;
    if (rightDistance === null) return -1;
    if (leftDistance !== rightDistance) return leftDistance - rightDistance;
    return String(left?.name ?? '').localeCompare(String(right?.name ?? ''), 'ko-KR');
  });
}

export function liveWaterTemperatureC(view) {
  if (view?.dataState !== 'live' || view?.isDemoFallback) return null;
  const rawTemperature = view?.conditions?.waterTemperatureC;
  if (rawTemperature === null || rawTemperature === undefined || rawTemperature === '') return null;
  const temperature = Number(rawTemperature);
  return Number.isFinite(temperature) ? temperature : null;
}

export function waterTemperatureTone(value) {
  if (!Number.isFinite(value)) return 'unknown';
  if (value < 10) return 'very-cold';
  if (value < 16) return 'cold';
  if (value < 22) return 'cool';
  if (value < 28) return 'mild';
  return 'warm';
}

export function geolocationFailureKind(error) {
  if (error?.code === 1) return 'denied';
  if (error?.code === 2) return 'unavailable';
  if (error?.code === 3) return 'timeout';
  return 'error';
}
