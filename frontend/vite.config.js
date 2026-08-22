import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import process from 'node:process'
import { resolveFrontendAuthMode } from './portfolioAuthMode.js'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const environment = { ...loadEnv(mode, process.cwd(), ''), ...process.env }
  const auth = resolveFrontendAuthMode(environment)

  return {
    base: environment.VITE_APP_BASE_PATH || '/',
    define: {
      'import.meta.env.VITE_SSO_ENABLED': JSON.stringify(String(auth.ssoEnabled)),
    },
    plugins: [react()],
  }
})
