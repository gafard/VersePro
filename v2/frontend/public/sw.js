/*
 * VersePro — Service worker
 * Stratégie :
 *  - Navigation : réseau d'abord, repli sur le shell en cache (usage hors-ligne).
 *  - Assets statiques même origine (js/css/img/fonts) : stale-while-revalidate.
 *  - /api et /ws ne sont JAMAIS mis en cache (données temps réel).
 */

const CACHE_NAME = 'versepro-shell-v3'
const CORE_ASSETS = [
  '/',
  '/media/versepro-launch.mp4',
  '/media/versepro-launch-poster.jpg',
  '/media/versepro-launch-still.jpg'
]

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
  )
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})

self.addEventListener('fetch', (event) => {
  const { request } = event
  if (request.method !== 'GET') return

  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/ws/')) return

  // Navigations : réseau d'abord, repli hors-ligne sur le shell
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then((response) => {
          const copy = response.clone()
          caches.open(CACHE_NAME).then((cache) => cache.put('/', copy))
          return response
        })
        .catch(() => caches.match('/'))
    )
    return
  }

  // Assets : cache immédiat, rafraîchi en arrière-plan
  event.respondWith(
    caches.match(request).then((cached) => {
      const refresh = fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone()
            caches.open(CACHE_NAME).then((cache) => cache.put(request, copy))
          }
          return response
        })
        .catch(() => cached)
      return cached || refresh
    })
  )
})
