import { mkdirSync } from 'node:fs'
import { resolve } from 'node:path'
import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// Windows 下 C:\WINDOWS\TEMP 可能对当前用户不可写（esbuild 需要创建/删除临时文件），
// 统一把临时目录指到项目内 .tmp，保证 npm run build 开箱可用。
if (process.platform === 'win32') {
  const localTemp = resolve(process.cwd(), '.tmp')
  mkdirSync(localTemp, { recursive: true })
  process.env.TEMP = localTemp
  process.env.TMP = localTemp
  process.env.TMPDIR = localTemp
}

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    // Element Plus 采用全量引入（约 940 kB / gzip 300 kB），如需进一步瘦身可切按需引入
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks: {
          vue: ['vue', 'vue-router', 'pinia'],
          element: ['element-plus', '@element-plus/icons-vue'],
          markdown: ['markdown-it', 'dompurify'],
        },
      },
    },
  },
})
