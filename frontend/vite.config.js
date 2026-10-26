import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In development the Django API runs on :8000; in production Django serves dist/.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
