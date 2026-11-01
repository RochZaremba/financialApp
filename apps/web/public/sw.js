// Cache only public install assets. Never cache private API or authenticated pages.
const CACHE = 'razem-shell-v1';
self.addEventListener('install', event => { event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(['/offline.html','/icon-192.png','/icon-512.png']))); self.skipWaiting(); });
self.addEventListener('activate', event => { event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))).then(() => self.clients.claim())); });
self.addEventListener('fetch', event => {
  if (event.request.mode === 'navigate') event.respondWith(fetch(event.request).catch(() => caches.match('/offline.html')));
});

// Notifications contain generic prompts only, never bank amounts, payees or credentials.
self.addEventListener('push', event => {
  event.waitUntil((async () => {
    await self.registration.showNotification('Nowy wpis do uzupełnienia', {
      body: 'Otwórz Razem, aby opisać operację lub dodać paragon.',
      icon: '/icon-192.png', badge: '/icon-192.png', tag: 'bank-updates',
      data: { url: '/bank' }
    });
  })());
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil((async () => {
    const url = new URL('/bank', self.location.origin).href;
    const windows = await self.clients.matchAll({type:'window', includeUncontrolled:true});
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(url); return client.focus();
      }
    }
    return self.clients.openWindow(url);
  })());
});
