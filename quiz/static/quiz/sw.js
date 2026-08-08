// SantuarioEdu Service Worker
// IMPORTANTE: sempre que HTML/JS/CSS mudar significativamente, bump CACHE_VERSION
// pra invalidar cache antigo do browser.
const CACHE_VERSION = 'santuario-v8';       // v8: offline robusto (quiz cache dedicado)
const CACHE_NAME    = CACHE_VERSION;
const QUIZ_CACHE    = 'santuario-quiz-v1';  // cache dedicado pra questoes (persistente)
const OFFLINE_URL   = '/offline/';

// Precache expandido — inclui rotas comuns pra funcionamento offline
const PRECACHE_ASSETS = [
  '/',
  '/dashboard/',
  '/estudar/',
  OFFLINE_URL,
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return Promise.allSettled(
        PRECACHE_ASSETS.map(url => cache.add(url).catch(() => {}))
      );
    }).then(() => self.skipWaiting())
  );
});

// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      // Preserva QUIZ_CACHE mesmo em upgrade (questoes offline permanecem)
      Promise.all(keys.filter(k => k !== CACHE_NAME && k !== QUIZ_CACHE)
                      .map(k => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

// Helper: rota e "questao/estudo" e deve entrar no cache dedicado?
function isRotaQuiz(pathname) {
  return (
    pathname === '/quiz/' ||
    pathname.startsWith('/quiz/') && !pathname.startsWith('/quiz/estilo-banca/') ||
    pathname.startsWith('/estudar/') ||
    pathname.startsWith('/assuntos/') ||
    pathname.startsWith('/simulado/questao/') ||
    pathname.startsWith('/flashcards/')
  );
}

// ── Fetch ─────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET') return;
  if (url.pathname.startsWith('/admin/')) return;
  if (url.pathname.startsWith('/api/')) return;
  if (url.origin !== self.location.origin) return;

  // ── Rotas de quiz/estudo: cache separado, mantido entre versoes ──
  // Estrategia: network-first, mas guarda TUDO num cache dedicado.
  // Se offline: serve do QUIZ_CACHE. Usuario pode estudar mesmo sem net.
  if (request.mode === 'navigate' && isRotaQuiz(url.pathname)) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(QUIZ_CACHE).then(c => {
              // Limita tamanho: guarda ate 50 questoes/paginas recentes
              c.put(request, clone);
              _limitarCache(QUIZ_CACHE, 50);
            });
          }
          return response;
        })
        .catch(() =>
          caches.match(request, { cacheName: QUIZ_CACHE })
            .then(cached => cached || caches.match(OFFLINE_URL))
        )
    );
    return;
  }

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

// ── Helper: limitar tamanho do cache ──────────────────────────────────────────
async function _limitarCache(cacheName, maxItens) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length > maxItens) {
    // Remove os mais antigos (primeiros a entrar)
    const remover = keys.slice(0, keys.length - maxItens);
    await Promise.all(remover.map(k => cache.delete(k)));
  }
}

// ── Push Notifications ────────────────────────────────────────────────────────
self.addEventListener('push', event => {
  let data = { title: 'SantuarioEdu', body: 'Você tem revisões pendentes!', url: '/dashboard/' };
  try { data = JSON.parse(event.data.text()); } catch(e) {}
  event.waitUntil(
    self.registration.showNotification(data.title, {
      body: data.body,
      icon: '/static/quiz/icon-192.svg',
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
