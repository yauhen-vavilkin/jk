import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";
import { execFileSync } from "node:child_process";

// design/tokens.json is the palette. Regenerate src/tokens.css from it on every
// start and every build, so a colour can never be edited in a copy.
function tokens(): Plugin {
  const write = (): void => {
    execFileSync("node", [
      fileURLToPath(new URL("./scripts/write-tokens-css.mjs", import.meta.url)),
    ]);
  };
  return { name: "jk-tokens", buildStart: write, configureServer: write };
}

// `npm run dev` serves the panel on 5173 and proxies the API to `jk serve --dev`.
export default defineConfig({
  plugins: [tokens(), react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: false,
      },
    },
  },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
