import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/v1': { target: 'http://localhost:8020', changeOrigin: true },
      '/health': { target: 'http://localhost:8020', changeOrigin: true },
    },
  },
})
