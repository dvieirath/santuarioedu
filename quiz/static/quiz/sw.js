// SantuarioEdu Service Worker
// IMPORTANTE: sempre que HTML/JS/CSS mudar significativamente, bump CACHE_VERSION
// pra invalidar cache antigo do browser. O activate handler apaga todos os caches
// de versões anteriores automaticamente.
const CACHE_VERSION = 'santuario-v7';  // v7: push icon .png -> .svg (arquivo nao existia)
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

  // Skip non-GET, API, admin — deixa passar direto
  if (request.method !== 'GET') return;
  if (url.pathname.startsWith('/admin/')) return;
  if (url.pathname.startsWith('/api/')) return;

  // CRITICAL: NAO intercepta requests cross-origin (CDN, fontes google, etc).
  // O SW tentando clonar Response de CDN dava "Failed to execute 'clone'" e
  // quebrava scripts tipo markmap-autoloader. Deixa o browser cuidar sozinho —
  // ele ja faz cache-http padrao com Cache-Control (jsdelivr serve immutable
  // com max-age=1 ano, entao browser cacheia com eficiencia total).
  if (url.origin !== self.location.origin) return;

  // A partir daqui: SO same-origin (santuarioedu.com.br)

  // HTML navigation: network-first, fallback cache -> offline
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
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

  // Assets locais (css/js/svg/img): stale-while-revalidate
  const isAssetLocal = url.pathname.match(/\.(css|js|svg|png|jpg|woff2?|ttf|ico)$/);
  if (isAssetLocal) {
    event.respondWith(
      caches.match(request).then(cached => {
        const rede = fetch(request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(c => c.put(request, clone));
          }
          return response;
        }).catch(() => cached);
        return cached || rede;
      })
    );
    return;
  }

  // Default same-origin: network-first
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
      icon: '/static/quiz/icon-192.svg',  // era .png (nao existe no repo)
      badge: '/static/quiz/icon-192.svg',
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
