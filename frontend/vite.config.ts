import { resolve } from 'node:path'

import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const rootDir = resolve(__dirname, '..')

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, rootDir, 'VITE_')
  const backendTarget = env.VITE_DEV_PROXY_TARGET ?? process.env.VITE_DEV_PROXY_TARGET ?? 'http://127.0.0.1:8000'

  return {
    envDir: rootDir,
    plugins: [react(), tailwindcss()],
    server: {
      proxy: {
        '/health': backendTarget,
        '/queues': backendTarget,
        '/subscriptions': backendTarget,
        '/organizer': backendTarget,
        '/dry-run': backendTarget,
        '/tmdb': backendTarget,
        '/tencent': backendTarget,
        '/runtime': backendTarget,
        '/netdisk': backendTarget,
        '/resources': backendTarget,
        '/collectors': backendTarget,
        '/log-center': backendTarget,
        '/transfer-queue': backendTarget,
        '/logs': backendTarget,
        '/notification': backendTarget,
        '/ai': backendTarget,
      },
    },
  }
})
