import assert from 'node:assert/strict';
import test from 'node:test';

import {
  accountLocaleToUiLocale,
  classifyAccountError,
  isMissingSession,
  normalizeActivity,
  normalizeAccountUser,
  normalizeEcoAction,
  normalizePassport,
  uiLocaleToAccountLocale,
} from './accountApi.js';

test('account locale mapping preserves the backend simplified-Chinese contract', () => {
  assert.equal(uiLocaleToAccountLocale('ko'), 'ko');
  assert.equal(uiLocaleToAccountLocale('zh'), 'zh-hans');
  assert.equal(accountLocaleToUiLocale('zh-hans'), 'zh');
  assert.equal(accountLocaleToUiLocale('unexpected'), 'ko');
});

test('account errors are bounded and never return backend detail text', () => {
  const error = {
    response: {
      status: 500,
      data: { detail: 'database password and internal host' },
    },
  };
  const result = classifyAccountError(error);

  assert.equal(result.kind, 'response');
  assert.equal(result.messageKey, 'account.error.response');
  assert.equal(JSON.stringify(result).includes('database'), false);
});

test('sensitive account validation maps fields to public error categories', () => {
  assert.equal(
    classifyAccountError({ response: { status: 400, data: { username: ['secret raw detail'] } } }, 'register').kind,
    'username',
  );
  assert.equal(
    classifyAccountError({ response: { status: 400, data: { new_password: ['raw policy'] } } }, 'password').kind,
    'password-policy',
  );
  assert.equal(
    classifyAccountError({ response: { status: 400, data: { current_password: ['raw mismatch'] } } }, 'delete').kind,
    'current-password',
  );
  assert.equal(
    classifyAccountError({ response: { status: 400, data: { non_field_errors: ['raw credential detail'] } } }, 'login').kind,
    'credentials',
  );
});

test('missing sessions include both DRF unauthenticated status shapes', () => {
  assert.equal(isMissingSession({ response: { status: 401 } }), true);
  assert.equal(isMissingSession({ response: { status: 403 } }), true);
  assert.equal(isMissingSession({ response: { status: 500 } }), false);
});

test('account responses require an id and username and bound profile enums', () => {
  assert.throws(() => normalizeAccountUser({ id: null, username: '' }), TypeError);
  assert.deepEqual(
    normalizeAccountUser({
      id: 7,
      username: ' water-user ',
      email: 'user@example.com',
      persona_type: 'unexpected',
      preferred_locale: 'unexpected',
    }),
    {
      id: 7,
      username: 'water-user',
      email: 'user@example.com',
      first_name: '',
      last_name: '',
      persona_type: '',
      mood_state: '',
      home_region: '',
      preferred_locale: 'ko',
      date_joined: null,
    },
  );
});

test('activity records preserve self-report semantics and reject malformed reviews', () => {
  const visit = normalizeActivity({
    id: 2,
    spot: 3,
    spot_detail: { id: 3, name: 'Beach', type: 'beach', region: 'Gangwon' },
    action: 'visit',
    rating: null,
    review_text: '',
    created_at: '2026-08-18T12:00:00Z',
  });
  assert.equal(visit.action, 'visit');
  assert.equal(visit.is_legacy, false);
  assert.throws(() => normalizeActivity({
    ...visit,
    id: 4,
    action: 'review',
  }), TypeError);
});

test('legacy activity enums are bounded read-only rows and remain invalid for new writes', () => {
  const payload = {
    id: 12,
    spot: 3,
    spot_detail: { id: 3, name: 'Beach', type: 'beach', region: 'Gangwon' },
    action: 'old_import_kind',
    rating: 99,
    review_text: 'legacy fields are not reinterpreted',
    created_at: '2026-08-18T12:00:00Z',
  };

  assert.throws(() => normalizeActivity(payload), TypeError);
  const legacy = normalizeActivity(payload, { allowLegacyAction: true });
  assert.equal(legacy.action, 'legacy');
  assert.equal(legacy.is_legacy, true);
  assert.equal(legacy.rating, null);
  assert.equal(legacy.review_text, '');
  assert.equal(JSON.stringify(legacy).includes('old_import_kind'), false);
});

test('passport and eco records require explicit verification enums', () => {
  const passport = normalizePassport({
    id: 4,
    spot: { id: 3, name: 'Beach', type: 'beach', region: 'Gangwon' },
    verified_at: '2026-08-18T12:00:00Z',
    verification_method: 'qr',
    evidence_url: 'https://evidence.example.com/item?token=removed',
  });
  assert.equal(passport.verification_method, 'qr');
  assert.equal(passport.evidence_url, 'https://evidence.example.com/item');

  const eco = normalizeEcoAction({
    id: 5,
    spot: null,
    spot_detail: null,
    action_type: 'cleanup',
    state: 'pending',
    note: '',
    evidence_url: '',
    occurred_on: '2026-08-18',
    submitted_at: '2026-08-18T12:00:00Z',
  });
  assert.equal(eco.state, 'pending');
  assert.throws(() => normalizeEcoAction({ ...eco, state: 'rewarded' }), TypeError);
  assert.throws(() => normalizeEcoAction({ ...eco, state: 'verified' }), TypeError);
});
