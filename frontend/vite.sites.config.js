import { cloudflare } from '@cloudflare/vite-plugin';
import { sites } from '@openai/sites-vite-plugin';
import react from '@vitejs/plugin-react';
import process from 'node:process';
import { defineConfig, loadEnv } from 'vite';
import { resolveFrontendAuthMode } from './portfolioAuthMode.js';

export default defineConfig(({ mode }) => {
  const environment = { ...loadEnv(mode, process.cwd(), ''), ...process.env };
  const auth = resolveFrontendAuthMode(environment);

  return {
    define: {
      'import.meta.env.VITE_SSO_ENABLED': JSON.stringify(String(auth.ssoEnabled)),
    },
    plugins: [
      react(),
      sites(),
      cloudflare({
        viteEnvironment: { name: 'server' },
        config: {
          name: 'pongdang-site',
          main: './worker/sites-worker.js',
          compatibility_date: '2026-05-22',
          compatibility_flags: ['nodejs_compat'],
          assets: {
            binding: 'ASSETS',
            not_found_handling: 'single-page-application',
          },
        },
      }),
    ],
  };
});
