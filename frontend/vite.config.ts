import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const envDir = '..'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, envDir, '')
  return {
    plugins: [react()],
    envDir,
    server: {
      // Explicit IPv4: "localhost" may resolve to ::1, which uvicorn does not listen on.
      host: '127.0.0.1',
      port: 5173,
      strictPort: true,
      proxy: {
        '/api': env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
      },
    },
  }
})
