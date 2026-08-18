import assert from 'node:assert/strict';
import test from 'node:test';

import {
  distanceKm,
  geolocationFailureKind,
  liveWaterTemperatureC,
  normalizeCoordinates,
  sortSpotsByDistance,
  waterTemperatureTone,
} from './mapData.js';

test('coordinates are normalized only inside geographic bounds', () => {
  assert.deepEqual(normalizeCoordinates({ latitude: '37.5', longitude: '127' }), {
    lat: 37.5,
    lng: 127,
  });
  assert.equal(normalizeCoordinates({ lat: 91, lng: 127 }), null);
  assert.equal(normalizeCoordinates({ lat: 37, lng: 'unknown' }), null);
});

test('distance uses the haversine formula and rejects missing coordinates', () => {
  const oneDegreeNorth = distanceKm({ lat: 0, lng: 0 }, { lat: 1, lng: 0 });

  assert.ok(oneDegreeNorth > 111 && oneDegreeNorth < 112);
  assert.equal(distanceKm({ lat: 0, lng: 0 }, { name: 'missing' }), null);
});

test('nearby sorting is deterministic and puts coordinate-less spots last', () => {
  const sorted = sortSpotsByDistance([
    { id: 'far', name: 'Far', lat: 37.7, lng: 128.9 },
    { id: 'missing', name: 'Missing' },
    { id: 'near', name: 'Near', lat: 37.5001, lng: 127.0001 },
  ], { lat: 37.5, lng: 127 });

  assert.deepEqual(sorted.map((spot) => spot.id), ['near', 'far', 'missing']);
});

test('temperature overlay accepts only non-demo live evidence', () => {
  const liveView = {
    dataState: 'live',
    isDemoFallback: false,
    conditions: { waterTemperatureC: 19.4 },
  };

  assert.equal(liveWaterTemperatureC(liveView), 19.4);
  assert.equal(liveWaterTemperatureC({ ...liveView, dataState: 'stale' }), null);
  assert.equal(liveWaterTemperatureC({ ...liveView, isDemoFallback: true }), null);
  assert.equal(liveWaterTemperatureC({ ...liveView, conditions: { waterTemperatureC: null } }), null);
});

test('temperature tones have explicit boundaries and a missing state', () => {
  assert.equal(waterTemperatureTone(null), 'unknown');
  assert.equal(waterTemperatureTone(9.9), 'very-cold');
  assert.equal(waterTemperatureTone(10), 'cold');
  assert.equal(waterTemperatureTone(16), 'cool');
  assert.equal(waterTemperatureTone(22), 'mild');
  assert.equal(waterTemperatureTone(28), 'warm');
});

test('geolocation browser failures map to safe UI states', () => {
  assert.equal(geolocationFailureKind({ code: 1 }), 'denied');
  assert.equal(geolocationFailureKind({ code: 2 }), 'unavailable');
  assert.equal(geolocationFailureKind({ code: 3 }), 'timeout');
  assert.equal(geolocationFailureKind({ code: 99 }), 'error');
});
