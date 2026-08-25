const CACHE_NAME = 'kopykat-static-v2';
const ASSETS_TO_CACHE = [
  '/static/styles.css',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        return cache.addAll(ASSETS_TO_CACHE);
      })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            return caches.delete(name);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  // Cache only same-origin static assets. Never cache documents, API responses,
  // authentication responses, redirects, or user-specific query strings.
  if (event.request.method !== 'GET') return;
  const requestUrl = new URL(event.request.url);
  const isStaticAsset = requestUrl.origin === self.location.origin
    && requestUrl.pathname.startsWith('/static/')
    && ['style', 'script', 'image', 'font'].includes(event.request.destination)
    && !requestUrl.search;
  if (!isStaticAsset) return;

  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        return response || fetch(event.request).then((fetchRes) => {
          if (!fetchRes.ok || fetchRes.type !== 'basic') return fetchRes;
          return caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, fetchRes.clone());
            return fetchRes;
          });
        });
      })
  );
});
