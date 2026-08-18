import assert from 'node:assert/strict';
import test from 'node:test';

import {
  API_SPOT_TYPES,
  canonicalSpotType,
  spotTypeMeta,
  spotTypeSupportsActivity,
} from './spotTypes.js';
import { messages } from '../i18n/messages.js';

test('the frontend declares the complete backend WaterSpot enum exactly once', () => {
  assert.deepEqual(API_SPOT_TYPES, [
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
  assert.deepEqual(Object.keys(spotTypeMeta), API_SPOT_TYPES);
});

test('only explicit legacy aliases are accepted and unknown types never become river', () => {
  assert.equal(canonicalSpotType('sea'), 'beach');
  assert.equal(canonicalSpotType('tidal_flat'), 'mudflat');
  assert.equal(canonicalSpotType('MYSTERY'), null);
});

test('activity-compatible type choices mirror the backend environment contract', () => {
  assert.equal(spotTypeSupportsActivity('beach', 'surf'), true);
  assert.equal(spotTypeSupportsActivity('coastal_road', 'relax'), true);
  assert.equal(spotTypeSupportsActivity('river', 'rafting'), true);
  assert.equal(spotTypeSupportsActivity('lake', 'swim'), true);
  assert.equal(spotTypeSupportsActivity('mudflat', 'mudflat'), true);
  assert.equal(spotTypeSupportsActivity('pool', 'onsen'), true);
  assert.equal(spotTypeSupportsActivity('waterfall', 'swim'), false);
  assert.equal(spotTypeSupportsActivity('hotspring', 'surf'), false);
});

test('every supported locale labels every backend spot type and recommendation scope control', () => {
  Object.entries(messages).forEach(([locale, dictionary]) => {
    API_SPOT_TYPES.forEach((spotType) => {
      assert.equal(
        typeof dictionary[`map.type.${spotType}`],
        'string',
        `${locale} is missing map.type.${spotType}`,
      );
    });
    [
      'concierge.controls.region',
      'concierge.controls.regionPlaceholder',
      'concierge.controls.regionHelp',
      'concierge.controls.regionNationwideHelp',
      'concierge.controls.spotType',
      'concierge.controls.allCompatibleTypes',
      'concierge.controls.spotTypeHelp',
    ].forEach((key) => {
      assert.equal(typeof dictionary[key], 'string', `${locale} is missing ${key}`);
    });
  });
});
