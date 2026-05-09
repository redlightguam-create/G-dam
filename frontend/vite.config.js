import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/artist-profiles': 'http://127.0.0.1:8000',
      '/songs': 'http://127.0.0.1:8000',
      '/collaborators': 'http://127.0.0.1:8000',
      '/upload': 'http://127.0.0.1:8000',
      '/send-links': 'http://127.0.0.1:8000',
      '/song-credits': 'http://127.0.0.1:8000',
      '/signature': 'http://127.0.0.1:8000'
    }
  }
});
