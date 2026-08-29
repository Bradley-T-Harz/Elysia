import { defineConfig } from "vite";

export default defineConfig({
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
    target: "es2021",
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/react") || id.includes("/node_modules/scheduler")) {
            return "react-runtime";
          }
          if (id.endsWith("/ConversationsPage.tsx")) {
            return "conversations-room";
          }
          if (
            id.endsWith("/ProjectDetailPage.tsx") ||
            id.endsWith("/ProjectWorkbenchPanel.tsx") ||
            id.endsWith("/ProjectsPage.tsx")
          ) {
            return "projects-room";
          }
          return undefined;
        }
      }
    }
  }
});
