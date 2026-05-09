import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/artist-profiles': 'https://g-dam.onrender.com',
      '/songs': 'https://g-dam.onrender.com',
      '/collaborators': 'https://g-dam.onrender.com',
      '/upload': 'https://g-dam.onrender.com',
      '/send-links': 'https://g-dam.onrender.com',
      '/song-credits': 'https://g-dam.onrender.com',
      '/signature': 'https://g-dam.onrender.com'
    }
  }
});
