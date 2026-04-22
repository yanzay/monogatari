/* eslint-env serviceworker */
/**
 * Monogatari — Service Worker.
 *
 * Strategy
 * --------
 *  - App shell (HTML/CSS/JS): network-first → cache fallback. The user always
 *    sees the latest reader code if online, but the app still loads offline.
 *  - Stories (JSON): network-first → cache fallback. Lets us hot-swap a fixed
 *    story while still working on a plane.
 *  - Audio (MP3): cache-first. Audio is large and immutable per story; we
 *    avoid re-downloading on every play.
 *  - Data files under /data: stale-while-revalidate. Read from cache fast
 *    but refresh in the background.
 *
 * Cache busting
 * -------------
 *  Bump CACHE_VERSION to force clients to throw away the old cache on
 *  activation. Old caches are removed in `activate`.
 */
const CACHE_VERSION = 'v1-2026-04-22-200334';
const SHELL_CACHE   = `monogatari-shell-${CACHE_VERSION}`;
const STORY_CACHE   = `monogatari-stories-${CACHE_VERSION}`;
const AUDIO_CACHE   = `monogatari-audio-${CACHE_VERSION}`;
const DATA_CACHE    = `monogatari-data-${CACHE_VERSION}`;

const APP_SHELL = [
  './',
  './index.html',
  './css/style.css',
  './js/app.js',
];

// ── Install: pre-cache the app shell so first offline visit works. ─────────
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting())
  );
});

// ── Activate: drop any old versions. ───────────────────────────────────────
self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((k) => k.startsWith('monogatari-') && !k.endsWith(CACHE_VERSION))
        .map((k) => caches.delete(k))
    );
    await self.clients.claim();
  })());
});

// ── Fetch routing. ─────────────────────────────────────────────────────────
self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Same-origin only — never intercept cross-origin (Google fonts CDNs etc.).
  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith('/audio/') || url.pathname.includes('/audio/')) {
    event.respondWith(cacheFirst(req, AUDIO_CACHE));
    return;
  }
  if (url.pathname.startsWith('/stories/') || url.pathname.includes('/stories/')) {
    event.respondWith(networkFirst(req, STORY_CACHE));
    return;
  }
  if (url.pathname.startsWith('/data/') || url.pathname.includes('/data/')) {
    event.respondWith(staleWhileRevalidate(req, DATA_CACHE));
    return;
  }
  // App shell (everything else: html / css / js / icons)
  event.respondWith(networkFirst(req, SHELL_CACHE));
});

// ── Strategies. ────────────────────────────────────────────────────────────
async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const res = await fetch(req);
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    // Audio missing while offline — return a synthetic 503 so the player
    // can fail gracefully without breaking the page.
    return new Response('', { status: 503, statusText: 'offline' });
  }
}

async function networkFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const res = await fetch(req);
    if (res && res.ok) cache.put(req, res.clone());
    return res;
  } catch (err) {
    const hit = await cache.match(req);
    if (hit) return hit;
    if (req.mode === 'navigate') {
      // Final fallback for nav requests: serve cached index.
      const shell = await caches.match('./index.html');
      if (shell) return shell;
    }
    return new Response('', { status: 503, statusText: 'offline' });
  }
}

async function staleWhileRevalidate(req, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(req);
  const network = fetch(req)
    .then((res) => {
      if (res && res.ok) cache.put(req, res.clone());
      return res;
    })
    .catch(() => cached);
  return cached || network;
}

// ── Manual messaging hooks (used by the app's "update available" UI). ──────
self.addEventListener('message', (event) => {
  if (!event.data) return;
  if (event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
