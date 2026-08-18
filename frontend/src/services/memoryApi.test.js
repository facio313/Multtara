import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeTripMemory } from './memoryApi.js';

const memory = {
  id: 8,
  spot: 3,
  spot_detail: { id: 3, name: 'Memory Beach', type: 'beach', region: 'Gangwon' },
  photo_url: 'https://images.example.org/photo.jpg?private=value',
  taken_at: '2026-08-17T10:00:00Z',
  estimated_location: 'Beach entrance',
};

test('trip memory normalization preserves the private owner row and sanitizes its public URL', () => {
  const normalized = normalizeTripMemory(memory, { now: '2026-08-18T00:00:00Z' });
  assert.equal(normalized.spot_detail.name, 'Memory Beach');
  assert.equal(normalized.photo_url, 'https://images.example.org/photo.jpg');
  assert.equal(normalized.estimated_location, 'Beach entrance');
});

test('trip memory rejects mismatched spots, private URLs, future times, and control characters', () => {
  const now = '2026-08-18T00:00:00Z';
  assert.throws(() => normalizeTripMemory({ ...memory, spot: 4 }, { now }), TypeError);
  assert.throws(() => normalizeTripMemory({ ...memory, photo_url: 'http://127.0.0.1/private.jpg' }, { now }), TypeError);
  assert.throws(() => normalizeTripMemory({ ...memory, taken_at: '2026-08-18T01:00:01Z' }, { now }), TypeError);
  assert.throws(() => normalizeTripMemory({ ...memory, estimated_location: 'line\ncontrol' }, { now }), TypeError);
});
