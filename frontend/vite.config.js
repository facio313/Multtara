import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const frontendDir = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(frontendDir, '..')

export default defineConfig(({ mode }) => {
  const fromFrontend = loadEnv(mode, frontendDir, '')
  const fromRoot = loadEnv(mode, repoRoot, '')
  const kakaoKey =
    fromFrontend.VITE_KAKAO_MAP_KEY ||
    fromRoot.VITE_KAKAO_MAP_KEY ||
    fromRoot.KAKAO_MAP_API_KEY ||
    ''

  return {
    plugins: [react()],
    define: {
      'import.meta.env.VITE_KAKAO_MAP_KEY': JSON.stringify(kakaoKey),
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
        '/media': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
