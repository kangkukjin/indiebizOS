import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
    strictPort: true,
    // 앱 표면 렌더 어휘의 순수 로직은 원격·폰 표면과 단일 소스(backend/static/app_render_core.js)라
    // frontend/ 밖을 import 한다 — dev 서버가 그 파일을 서빙하도록 저장소 루트를 허용.
    // (빌드는 rollup 이 번들에 인라인하므로 이 설정과 무관)
    fs: { allow: ['..'] },
  },
})
