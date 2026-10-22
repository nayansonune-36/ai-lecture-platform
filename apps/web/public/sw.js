/**
 * Service Worker for AI Lecture Platform PWA.
 * Fully offline-capable application shell.
 * Explicitly DOES NOT cache video/audio media chunks or HLS streams.
 * Explicitly NEVER depends on any external network resource outside self.location.origin.
 */

const CACHE_NAME = "lecture-shell-v1";
const SHELL_ASSETS = ["/", "/index.html", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(SHELL_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // 1. RULE: ZERO EXTERNAL NETWORK DEPENDENCIES (strictly same-origin only)
  if (url.origin !== self.location.origin) {
    return;
  }

  // 2. RULE: NEVER CACHE MEDIA (Video, Audio, HLS streams, master playlists)
  const isMedia =
    request.destination === "video" ||
    request.destination === "audio" ||
    url.pathname.startsWith("/media/") ||
    url.pathname.includes("/hls/") ||
    url.pathname.endsWith(".m3u8") ||
    url.pathname.endsWith(".m4s") ||
    url.pathname.endsWith(".mp4") ||
    url.pathname.endsWith(".webm") ||
    url.pathname.endsWith(".ts");

  if (isMedia) {
    // Let browser stream directly from network with zero interception
    return;
  }

  // 3. Do not cache non-GET or API calls
  if (request.method !== "GET" || url.pathname.startsWith("/api/")) {
    return;
  }

  // 4. App shell caching with Cache-First fallback to Network
  event.respondWith(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.match(request).then((cachedResponse) => {
        const fetchPromise = fetch(request)
          .then((networkResponse) => {
            if (networkResponse && networkResponse.status === 200) {
              cache.put(request, networkResponse.clone());
            }
            return networkResponse;
          })
          .catch(() => cachedResponse);

        return cachedResponse || fetchPromise;
      });
    })
  );
});
