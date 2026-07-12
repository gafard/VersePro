import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendPort = process.env.VITE_BACKEND_PORT || '8001'
const backendHttp = `http://localhost:${backendPort}`
const backendWs = `ws://localhost:${backendPort}`

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': backendHttp,
      '/projection': backendHttp,
      '/output': backendHttp,
      '/obs': backendHttp,
      '/follow': backendHttp,
      '/stage': backendHttp,
      '/ws': {
        target: backendWs,
        ws: true
      }
    }
  }
})
