import { sveltekit } from '@sveltejs/kit/vite';
import { SvelteKitPWA } from '@vite-pwa/sveltekit';
import { defineConfig } from 'vitest/config';

export default defineConfig(({ mode }) => {
  const dev = mode !== 'production';
  const base = dev ? '/' : '/monogatari/';

  return {
    plugins: [
      sveltekit(),
      SvelteKitPWA({
        strategies: 'generateSW',
        registerType: 'prompt',
        injectRegister: false, // we register manually so we can show an update toast
        scope: base,
        base,
        manifest: {
          name: 'Monogatari',
          short_name: 'Monogatari',
          description: 'Graded Japanese reader with click-to-lookup vocab, SRS, and per-token audio.',
          theme_color: '#c0392b',
          background_color: '#faf8f4',
          start_url: base,
          scope: base,
          display: 'standalone',
          lang: 'en',
          icons: [],
        },
        workbox: {
          // Take over open tabs immediately when a new SW activates.
          // Required for the "Reload" button in ReloadPrompt to actually
          // trigger a controllerchange event and surface the new shell.
          skipWaiting: true,
          clientsClaim: true,
          globPatterns: ['**/*.{html,js,css,svg,woff2}'],
          // Don't precache big stuff — runtime caching handles stories/audio
          globIgnores: ['**/audio/**', '**/stories/**', '**/data/**'],
          maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
          navigateFallback: `${base}index.html`,
          navigateFallbackDenylist: [/^\/api\//, /\/[^/?]+\.[^/]+$/],
          runtimeCaching: [
            {
              // Story JSON: network-first so a fresh deploy is picked up,
              // but works offline from cache.
              urlPattern: ({ url }) => url.pathname.includes('/stories/') && url.pathname.endsWith('.json'),
              handler: 'NetworkFirst',
              options: {
                cacheName: 'monogatari-stories',
                networkTimeoutSeconds: 3,
                expiration: { maxEntries: 500, maxAgeSeconds: 30 * 24 * 3600 },
              },
            },
            {
              // Audio: cache-first with LRU eviction. Per-token MP3s are immutable.
              urlPattern: ({ url }) => url.pathname.includes('/audio/') && url.pathname.endsWith('.mp3'),
              handler: 'CacheFirst',
              options: {
                cacheName: 'monogatari-audio',
                expiration: { maxEntries: 2000, maxAgeSeconds: 60 * 24 * 3600 },
                rangeRequests: true,
              },
            },
            {
              // Vocab/grammar state: stale-while-revalidate.
              urlPattern: ({ url }) => url.pathname.includes('/data/') && url.pathname.endsWith('.json'),
              handler: 'StaleWhileRevalidate',
              options: {
                cacheName: 'monogatari-data',
                expiration: { maxEntries: 50, maxAgeSeconds: 7 * 24 * 3600 },
              },
            },
          ],
        },
        devOptions: { enabled: false },
      }),
    ],
    test: {
      environment: 'happy-dom',
      include: ['tests/unit/**/*.test.ts'],
      globals: true,
    },
    server: {
      fs: {
        // allow serving static/data, static/stories, static/audio
        strict: false,
      },
    },
  };
});
