import assert from 'node:assert/strict';
import test from 'node:test';

import { accountMessages } from './accountMessages.js';

test('account and itinerary additions have complete non-empty translations', () => {
  const canonicalKeys = Object.keys(accountMessages.ko).sort();

  Object.entries(accountMessages).forEach(([locale, dictionary]) => {
    assert.deepEqual(
      Object.keys(dictionary).sort(),
      canonicalKeys,
      `${locale} must contain the complete account and itinerary key set`,
    );
    canonicalKeys.forEach((key) => {
      assert.equal(typeof dictionary[key], 'string', `${locale} is missing ${key}`);
      assert.ok(dictionary[key].trim(), `${locale} has an empty ${key}`);
    });
  });
});
