import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  build: {
    rollupOptions: {
      input: {
        qavisoHome: resolve(import.meta.dirname, "qaviso-home.html"),
        workshop: resolve(import.meta.dirname, "index.html"),
        admin: resolve(import.meta.dirname, "admin.html"),
      },
    },
  },
});
