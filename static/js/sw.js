const CACHE = 'caracasbull-v1';
const STATIC = [
    '/static/css/main.css',
    '/static/js/main.js',
];

self.addEventListener('install', e => {
    e.waitUntil(
        caches.open(CACHE).then(c => c.addAll(STATIC))
    );
    self.skipWaiting();
});

self.addEventListener('activate', e => {
    e.waitUntil(
        caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', e => {
    // Solo cachear GET de assets estáticos
    if (e.request.method !== 'GET') return;
    if (e.request.url.includes('/static/')) {
        e.respondWith(
            caches.match(e.request).then(cached => cached || fetch(e.request))
        );
    }
});
