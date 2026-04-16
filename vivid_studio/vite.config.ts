import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@rfx": path.resolve(__dirname, "../dry_test/remotion/src/components"),
      // FX 컴포넌트(dry_test)의 remotion/react import를 vivid_studio 인스턴스로 통일
      // → useCurrentFrame() 등이 Player Context 안에서 올바르게 실행됨
      remotion: path.resolve(__dirname, "node_modules/remotion"),
      react: path.resolve(__dirname, "node_modules/react"),
      "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
    },
  },
  server: {
    port: 3001,
    host: "127.0.0.1",
    // FastAPI(port 8000)로 API 요청 프록시 → CORS 불필요
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
});
