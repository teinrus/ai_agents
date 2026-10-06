import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/tasks": "http://127.0.0.1:8000",
      "/runs": "http://127.0.0.1:8000",
      "/threads": "http://127.0.0.1:8000",
    },
  },
});
