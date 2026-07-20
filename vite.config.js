// KalenDAV Vite pipeline. Wave 2.
//
// Inputs:
//   app/static/src/main.js       — global entry (htmx, lucide, dark mode)
//   app/static/src/calendar.js   — code-split entry (FullCalendar; calendar page only)
//   app/static/src/main.css      — Tailwind + design tokens
//
// Output:
//   app/static/dist/             — hashed assets + manifest.json
//
// In dev (VITE_DEV=true), the FastAPI vite_asset filter points at
// http://localhost:5173/<entry> instead of the built manifest.

import { defineConfig } from 'vite';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

const projectRoot = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // Mount point for the built assets. FastAPI serves app/static/dist at
  // /static/, so all hashed URLs (font-face src, asset imports) must be
  // rooted there too. The dev server (origin: http://localhost:5173) is
  // unaffected — vite_asset() returns full dev-server URLs in that mode.
  base: '/static/',
  define: {
    'process.env.NODE_ENV': JSON.stringify(process.env.NODE_ENV || 'development'),
  },
  resolve: {
    alias: {
      '@': resolve(projectRoot, './app/static/src'),
    },
  },
  build: {
    outDir: 'app/static/dist',
    manifest: 'manifest.json',
    emptyOutDir: true,
    assetsInlineLimit: 4096,
    cssCodeSplit: false,
    rollupOptions: {
      input: {
        main: resolve(projectRoot, 'app/static/src/main.js'),
        calendar: resolve(projectRoot, 'app/static/src/calendar.js'),
      },
      output: {
        manualChunks: {
          'vendor-htmx': ['htmx.org'],
          'vendor-calendar': [
            '@fullcalendar/core',
            '@fullcalendar/daygrid',
            '@fullcalendar/timegrid',
            '@fullcalendar/interaction',
            '@fullcalendar/rrule',
            'rrule',
          ],
        },
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    origin: 'http://localhost:5173',
    hmr: {
      clientPort: 5173,
    },
  },
});
