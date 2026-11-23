import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  // strictPort: fail instead of moving to 5174, 5175...: the backend's CORS (BACKEND_CORS_ORIGINS) allows only 5173.
  server: { port: 5173, strictPort: true },
});
