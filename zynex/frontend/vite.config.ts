import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api/v1/tender': {
        target: process.env.VITE_TENDER_API_TARGET || 'http://localhost:8001',
        changeOrigin: true,
      },
      '/api/v1/tender-tiger': {
        target: process.env.VITE_TENDER_API_TARGET || 'http://localhost:8001',
        changeOrigin: true,
      },
      '/api/v1/eligibility': {
        target: process.env.VITE_TENDER_API_TARGET || 'http://localhost:8001',
        changeOrigin: true,
      },
      '/api': {
        target: process.env.VITE_API_TARGET || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
