import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveFrontendAuthMode } from './portfolioAuthMode.js';

for (const branch of ['main', 'dev', 'refs/heads/main', 'refs/heads/dev']) {
  test(`${branch} enables SSO`, () => {
    assert.deepEqual(resolveFrontendAuthMode({
      PORTFOLIO_BRANCH: branch,
      PORTFOLIO_AUTH_MODE: 'sso',
      VITE_SSO_ENABLED: 'true',
    }), { mode: 'sso', ssoEnabled: true });
  });
}

test('a feature branch keeps local auth', () => {
  assert.deepEqual(resolveFrontendAuthMode({
    PORTFOLIO_BRANCH: 'codex-auth-contract',
    PORTFOLIO_AUTH_MODE: 'local',
    VITE_SSO_ENABLED: 'false',
  }), { mode: 'local', ssoEnabled: false });
});

test('canonical and legacy mismatches fail closed', () => {
  assert.throws(() => resolveFrontendAuthMode({
    PORTFOLIO_BRANCH: 'main',
    PORTFOLIO_AUTH_MODE: 'local',
  }));
  assert.throws(() => resolveFrontendAuthMode({
    PORTFOLIO_BRANCH: 'main',
    PORTFOLIO_AUTH_MODE: 'sso',
    VITE_SSO_ENABLED: 'false',
  }), /VITE_SSO_ENABLED/);
});

test('a packaged build requires both canonical values', () => {
  assert.throws(
    () => resolveFrontendAuthMode({}, false),
    /PORTFOLIO_BRANCH/,
  );
  assert.throws(
    () => resolveFrontendAuthMode({ PORTFOLIO_BRANCH: 'main' }, false),
    /PORTFOLIO_AUTH_MODE/,
  );
});
