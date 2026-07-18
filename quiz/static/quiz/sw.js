// SantuarioEdu Service Worker
// IMPORTANTE: sempre que HTML/JS/CSS mudar significativamente, bump CACHE_VERSION
// pra invalidar cache antigo do browser. O activate handler apaga todos os caches
// de versões anteriores automaticamente.
const CACHE_VERSION = 'santuario-v4';
const CACHE_NAME    = CACHE_VERSION;
const OFFLINE_URL   = '/offline/';

// Só o essencial. Menos precache = menos risco de servir HTML velho.
const PRECACHE_ASSETS = [
  '/',
  OFFLINE_URL,
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      // Pre-cache critical app pages — ignore failures for CDN assets
      return Promise.allSettled(
        PRECACHE_ASSETS.map(url =>
          cache.add(url).catch(() => {})
        )
      );
    }).then(() => self.skipWaiting())
  );
});

// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET, cross-origin API calls, admin panel
  if (request.method !== 'GET') return;
  if (url.pathname.startsWith('/admin/')) return;
  if (url.pathname.startsWith('/api/')) return;

  // For HTML navigation requests: network-first, fall back to cache
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Cache successful HTML responses
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(c => c.put(request, clone));
          }
          return response;
        })
        .catch(() =>
          caches.match(request).then(cached => cached || caches.match(OFFLINE_URL))
        )
    );
    return;
  }

  // For static assets: stale-while-revalidate (serve cache imediato, atualiza em bg)
  // Fontes/CDN: cache-first (raramente mudam)
  const isFonteOuCdn = (
    url.hostname.includes('cdn.tailwindcss.com') ||
    url.hostname.includes('fonts.googleapis.com') ||
    url.hostname.includes('fonts.gstatic.com') ||
    url.hostname.includes('cdn.jsdelivr.net') ||
    url.pathname.match(/\.(woff2?|ttf|ico)$/)
  );
  const isAssetLocal = url.pathname.match(/\.(css|js|svg|png|jpg)$/);

  if (isFonteOuCdn) {
    event.respondWith(
      caches.match(request).then(cached => cached || fetch(request).then(response => {
        if (response.ok) caches.open(CACHE_NAME).then(c => c.put(request, response.clone()));
        return response;
      }))
    );
    return;
  }

  if (isAssetLocal) {
    event.respondWith(
      caches.match(request).then(cached => {
        const rede = fetch(request).then(response => {
          if (response.ok) caches.open(CACHE_NAME).then(c => c.put(request, response.clone()));
          return response;
        }).catch(() => cached);
        // Serve cache imediato (se existe) enquanto atualiza em background
        return cached || rede;
      })
    );
    return;
  }

  // Default: network-first
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});

// ── Push Notifications ────────────────────────────────────────────────────────
self.addEventListener('push', event => {
  let data = { title: 'SantuarioEdu', body: 'Você tem revisões pendentes!', url: '/dashboard/' };
  try { data = JSON.parse(event.data.text()); } catch(e) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/quiz/icon-192.png',
      badge: '/static/quiz/icon-192.png',
      data: { url: data.url || '/' },
      vibrate: [200, 100, 200],
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(clients.openWindow(url));
});
