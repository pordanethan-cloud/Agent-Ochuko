import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    // Pin HMR to the same host the browser uses (localhost), so the dev
    // websocket stops probing 127.0.0.1 and failing to reconnect.
    hmr: {
      host: 'localhost',
      protocol: 'ws',
    },
  },
  build: {
    chunkSizeWarningLimit: 1000,
    emptyOutDir: false,
  },
  plugins: [
    react(),
    VitePWA({
      selfDestroying: true,
      registerType: 'prompt',
      includeAssets: ['favicon.png', 'favicon.svg'],
      manifest: {
        name: 'Agent Ochuko',
        short_name: 'Ochuko',
        description: 'AI assistant built on Azure AI Foundry',
        theme_color: '#1a1a18',
        background_color: '#1a1a18',
        display: 'standalone',
        start_url: '/',
        icons: [
          {
            src: 'favicon.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'favicon.png',
            sizes: '512x512',
            type: 'image/png'
          },
          {
            src: 'favicon.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable'
          }
        ]
      },
      workbox: {
        runtimeCaching: [
          {
            // Do NOT cache backend API calls (especially responses stream)
            urlPattern: /\/v1\/.*/,
            handler: 'NetworkOnly'
          }
        ]
      }
    })
  ]
})
