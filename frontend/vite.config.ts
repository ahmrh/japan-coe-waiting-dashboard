import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [vue()],
    server: {
      host: '0.0.0.0',
      port: 5173,
      proxy: {
        '/api': env.VITE_API_PROXY || 'http://127.0.0.1:8000',
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (id.includes('/node_modules/echarts/')) return 'charts'
            if (id.includes('/node_modules/vue/')) return 'vue'
          },
        },
      },
    },
  }
})
