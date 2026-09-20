import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";


export default defineConfig({
  plugins: [react()],

  server: {
    host: "0.0.0.0",
    port: 5173,

    allowedHosts: [
      ".apps.launchpad.nvidia.com",
    ],

    proxy: {
      "/api": {
        target: "http://127.0.0.1:8001",
        changeOrigin: true,
        timeout: 300000,
        proxyTimeout: 300000,
      },
    },

    hmr: {
      protocol: "wss",
      host:
        "abe0e51d-a083-7166-a4b8-2d5ef7d4d702.apps.launchpad.nvidia.com",
      clientPort: 443,
    },
  },
});


