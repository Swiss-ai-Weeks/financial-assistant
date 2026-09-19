import process from 'node:process'

import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Local development needs no configuration.
//
// Behind a reverse proxy (e.g. NVIDIA Launchpad) set
// VITE_HMR_HOST to the public hostname so hot reload
// connects back through the proxy over wss.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [react()],

    server: {
      host: '0.0.0.0',
      port: 5173,

      allowedHosts: ['.apps.launchpad.nvidia.com'],

      proxy: {
        '/api': env.VITE_API_PROXY ?? 'http://127.0.0.1:8080',
      },

      hmr: env.VITE_HMR_HOST
        ? { protocol: 'wss', host: env.VITE_HMR_HOST, clientPort: 443 }
        : undefined,
    },
  }
})
