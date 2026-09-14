// 从 vitest/config 引入 defineConfig，才能带上 test 字段的类型
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// 开发期把 /api 代理到后端；生产环境由 nginx / 后端静态托管，
// 因此前端代码里始终只使用相对路径 /api，不需要区分环境。
const API_TARGET = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        // SSE 需要关掉代理层缓冲，否则事件会被攒到连接结束才一次性吐出来
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            const contentType = String(proxyRes.headers['content-type'] ?? '')
            if (contentType.includes('text/event-stream')) {
              proxyRes.headers['cache-control'] = 'no-cache, no-transform'
            }
          })
        },
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    chunkSizeWarningLimit: 1500,
  },
  test: {
    // 组件测试需要 DOM；纯函数测试跑在 jsdom 上也没有副作用
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    // 每个用例前重置 vi.fn / vi.spyOn，避免用例间串味
    restoreMocks: true,
    // 用例里用 vi.stubGlobal 注入的 fetch / 语音 API 在用例结束后自动还原
    unstubGlobals: true,
    // 组件不依赖真实样式，跳过 CSS 处理能明显加快启动
    css: false,
  },
})
