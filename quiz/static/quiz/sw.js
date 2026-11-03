// Only public static assets and the anonymous offline page may be cached.
const CACHE_NAME = 'santuario-v9';
const OFFLINE_URL = '/offline/';
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE_NAME).then(async cache => {
    const response = await fetch(OFFLINE_URL, {credentials: 'omit', cache: 'reload'});
    if (response.ok && !response.redirected) await cache.put(OFFLINE_URL, response);
  }).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(k => k.startsWith('santuario-') && k !== CACHE_NAME)
        .map(k => caches.delete(k))
  )).then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const {request} = event;
  const url = new URL(request.url);
  if (request.method !== 'GET' || url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request, {cache: 'no-store'}).catch(async () =>
      (await caches.open(CACHE_NAME)).match(OFFLINE_URL).then(cached =>
        cached || new Response('Sem conexão. Tente novamente.', {
          status: 503, headers: {'Content-Type': 'text/plain; charset=utf-8'}
        }))
    ));
    return;
  }
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(caches.open(CACHE_NAME).then(async cache => {
      const cached = await cache.match(request);
      if (cached) return cached;
      const response = await fetch(request);
      if (response.ok && !response.redirected) await cache.put(request, response.clone());
      return response;
    }));
  }
});

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
