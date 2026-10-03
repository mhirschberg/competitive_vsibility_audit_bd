import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  build: {
    outDir: "home-dist",
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(import.meta.dirname, "qaviso-home.html"),
    },
  },
});
