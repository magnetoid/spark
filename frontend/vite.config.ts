import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

// The app owns "/"; SPARK_SPA_BASE exists for serving it under a prefix (must match the backend).
const base = process.env.SPARK_SPA_BASE ?? "/";

export default defineConfig({
  base,
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/media": "http://localhost:8000",
      "/static": "http://localhost:8000",
    },
  },
  build: { outDir: "dist", sourcemap: false, target: "es2022" },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
