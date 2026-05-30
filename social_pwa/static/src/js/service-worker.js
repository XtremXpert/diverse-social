/**
 * Service worker — minimal, privacy-aware.
 *
 * Caches: versioned static assets only (hashed URLs under /web/assets/),
 * plus the manifest and our own icons. Never caches HTML pages or JSON
 * endpoints — login/logout transitions between users on the same browser
 * would otherwise leak content across sessions.
 *
 * Offline fallback: when a navigation request fails, the SW serves the
 * /pwa/offline shell (cached at install time).
 *
 * Push: receives generic-payload pushes and renders them. The server
 * never sends sender names or message previews — see /pwa/subscribe + the
 * notification.create() hook in models/.
 */
'use strict';

const CACHE_PREFIX = 'diverse-pwa-';
// Bump this to invalidate the SW's cache. Browsers re-fetch sw.js on
// every navigation and only honour the new cache name on activate.
const VERSION = 'v3';
const CACHE_NAME = `${CACHE_PREFIX}${VERSION}`;
const OFFLINE_URL = '/pwa/offline';
const STATIC_PRECACHE = [
    OFFLINE_URL,
    '/social_pwa/static/src/img/icon-192.png',
    '/social_pwa/static/src/img/icon-512.png',
    '/social_pwa/static/src/img/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_PRECACHE))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil((async () => {
        const names = await caches.keys();
        await Promise.all(
            names.filter((n) => n.startsWith(CACHE_PREFIX) && n !== CACHE_NAME)
                 .map((n) => caches.delete(n))
        );
        await self.clients.claim();
    })());
});

/** Decide whether a request is safe to cache. */
function isCachableStatic(url) {
    // Versioned bundle assets: hashed URL, perfect to cache.
    if (url.pathname.startsWith('/web/assets/')) return true;
    // Our own icon set + offline shell — explicit allowlist.
    if (url.pathname.startsWith('/social_pwa/static/')) return true;
    if (url.pathname === '/manifest.webmanifest') return true;
    return false;
}

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;
    const url = new URL(req.url);

    // Navigations: network-first, fallback to offline shell on failure.
    // Never cache the HTML response itself.
    if (req.mode === 'navigate') {
        event.respondWith((async () => {
            try {
                return await fetch(req);
            } catch (_) {
                const cache = await caches.open(CACHE_NAME);
                const cached = await cache.match(OFFLINE_URL);
                return cached || new Response('Offline', { status: 503 });
            }
        })());
        return;
    }

    // Static assets: cache-first.
    if (isCachableStatic(url)) {
        event.respondWith((async () => {
            const cache = await caches.open(CACHE_NAME);
            const cached = await cache.match(req);
            if (cached) return cached;
            try {
                const resp = await fetch(req);
                if (resp && resp.status === 200) cache.put(req, resp.clone());
                return resp;
            } catch (_) {
                return cached || new Response('Offline', { status: 503 });
            }
        })());
        return;
    }

    // Everything else (JSON APIs, /web/dataset, /web/session/*) is
    // intentionally NOT intercepted — let the network handle it directly.
});

// ── Push handler ─────────────────────────────────────────────────────────────
// The server controls the displayed text via /pwa/subscribe payloads. We
// fall back to a generic constant if the push has no JSON body.
self.addEventListener('push', (event) => {
    let payload = { title: 'MétéoMédia', body: 'Nouvelle activité — ouvrez l\'app pour voir.' };
    try {
        if (event.data) {
            const json = event.data.json();
            if (json && typeof json === 'object') payload = json;
        }
    } catch (_) { /* keep default */ }
    event.waitUntil(
        self.registration.showNotification(payload.title || 'MétéoMédia', {
            body: payload.body || '',
            icon: '/social_pwa/static/src/img/icon-192.png',
            badge: '/social_pwa/static/src/img/icon-192.png',
            tag: 'social-generic',
            renotify: false,
        })
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    event.waitUntil((async () => {
        const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const client of all) {
            if ('focus' in client) return client.focus();
        }
        if (self.clients.openWindow) return self.clients.openWindow('/my/dashboard');
    })());
});
