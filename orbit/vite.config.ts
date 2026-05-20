import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const rootDir = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  build: {
    // TLDraw is loaded only when the optional spatial canvas opens. Keep the
    // main Orbit bundle small while allowing that lazy chunk to remain intact.
    chunkSizeWarningLimit: 1600
  },
  resolve: {
    alias: { '@': path.resolve(rootDir, 'src') }
  },
  server: {
    port: 3000,
    proxy: {
      '/api': 'http://localhost:3001'
    }
  }
})
