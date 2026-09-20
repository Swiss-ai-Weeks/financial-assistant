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

      // The desk is opened through whatever forwards the port:
      // VS Code, a Launchpad URL, a tunnel. Their hostnames are
      // not known in advance, and a development server that
      // answers "host not allowed" is a dead end on demo day.
      // Set VITE_ALLOWED_HOSTS to a comma-separated list to
      // restrict it again.
      allowedHosts: env.VITE_ALLOWED_HOSTS
        ? env.VITE_ALLOWED_HOSTS.split(',').map((host) => host.trim())
        : true,

      proxy: {
        '/api': env.VITE_API_PROXY ?? 'http://127.0.0.1:8080',
      },

      hmr: env.VITE_HMR_HOST
        ? { protocol: 'wss', host: env.VITE_HMR_HOST, clientPort: 443 }
        : undefined,
    },
  }
})
