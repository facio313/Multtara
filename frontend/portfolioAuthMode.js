import { execFileSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import process from 'node:process'
import { fileURLToPath } from 'node:url'

const frontendDirectory = path.dirname(fileURLToPath(import.meta.url))
const repositoryRoot = path.resolve(frontendDirectory, '..')
const resolverPath = path.join(repositoryRoot, 'scripts', 'portfolio-auth-mode.sh')
const branchPattern = /^[A-Za-z0-9._/-]+$/

function modeForBranch(value) {
  const branch = value.replace(/^refs\/heads\//, '')
  if (!branch || !branchPattern.test(branch)) {
    throw new Error('PORTFOLIO_BRANCH is missing or invalid')
  }
  return ['main', 'dev'].includes(branch) ? 'sso' : 'local'
}

function canonicalMode(environment, resolverAvailable) {
  if (resolverAvailable) {
    return execFileSync('/bin/sh', [resolverPath, 'print'], {
      cwd: repositoryRoot,
      env: { ...process.env, ...environment },
      encoding: 'utf8',
      timeout: 5000,
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim()
  }

  const branch = environment.PORTFOLIO_BRANCH ?? environment.GITHUB_REF_NAME
  if (branch === undefined) {
    throw new Error('Packaged frontend builds must set PORTFOLIO_BRANCH explicitly')
  }
  const expectedMode = modeForBranch(branch)
  if (environment.PORTFOLIO_AUTH_MODE === undefined) {
    throw new Error('Packaged frontend builds must set PORTFOLIO_AUTH_MODE explicitly')
  }
  if (environment.PORTFOLIO_AUTH_MODE !== expectedMode) {
    throw new Error(`PORTFOLIO_BRANCH requires PORTFOLIO_AUTH_MODE=${expectedMode}`)
  }
  return expectedMode
}

export function resolveFrontendAuthMode(
  environment = process.env,
  resolverAvailable = existsSync(resolverPath),
) {
  const mode = canonicalMode(environment, resolverAvailable)
  if (!['sso', 'local'].includes(mode)) {
    throw new Error('The portfolio auth-mode resolver returned an invalid mode')
  }
  const expectedLegacyValue = mode === 'sso' ? 'true' : 'false'
  const legacyValue = environment.VITE_SSO_ENABLED
  if (legacyValue !== undefined && legacyValue !== '') {
    const normalizedLegacyValue = legacyValue.toLowerCase()
    if (!['true', 'false'].includes(normalizedLegacyValue)) {
      throw new Error('VITE_SSO_ENABLED must be true or false')
    }
    if (normalizedLegacyValue !== expectedLegacyValue) {
      throw new Error(`VITE_SSO_ENABLED conflicts with PORTFOLIO_AUTH_MODE=${mode}`)
    }
  }
  return Object.freeze({ mode, ssoEnabled: mode === 'sso' })
}
