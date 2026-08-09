import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { nodePolyfills } from "vite-plugin-node-polyfills";

// https://vitejs.dev/config/
export default defineConfig({
  envDir: "../",
  plugins: [
    react(),
    nodePolyfills({
      include: ["buffer", "util", "stream", "crypto"],
      globals: {
        Buffer: true,
        global: true,
        process: true,
      },
      // Prevent the plugin from injecting deprecated esbuildOptions
      protocolImports: true,
    }),
  ],
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  optimizeDeps: {
    // Exclude polyfill shims from Rolldown pre-bundling to avoid
    // the @esbuild-plugins/node-globals-polyfill "Not implemented" crash
    exclude: [
      "vite-plugin-node-polyfills/shims/buffer",
      "vite-plugin-node-polyfills/shims/global",
      "vite-plugin-node-polyfills/shims/process",
    ],
  },
  server: {
    port: 5173,
    proxy: {
      // Proxy /api calls to the FastAPI backend in development
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "esnext",
    outDir: "dist",
  },
});
