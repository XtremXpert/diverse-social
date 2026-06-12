/**
 * PWA registration — vanilla JS, no OWL.
 *
 * - Registers /sw.js at scope /
 * - Captures beforeinstallprompt and stashes it (no auto mini-infobar on
 *   sensitive pages — install only via explicit user action in
 *   /my/profile/edit).
 * - When the install button is present, wires it to the stashed prompt.
 * - Wires the push-subscribe button when present and when VAPID is configured.
 */
(function () {
    'use strict';

    let deferredPrompt = null;

    // ── Service worker registration ─────────────────────────────────────────
    function registerServiceWorker() {
        if (!('serviceWorker' in navigator)) return;
        // Hide registration errors — a missing/failing SW shouldn't break the
        // site. SW failures aren't a security issue, just a feature loss.
        navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
    }

    // ── Capture install prompt (suppress automatic mini-infobar) ────────────
    window.addEventListener('beforeinstallprompt', (e) => {
        e.preventDefault();
        deferredPrompt = e;
        showInstallButton();
    });

    function showInstallButton() {
        const btn = document.getElementById('pwa_install_btn');
        const fallback = document.getElementById('pwa_install_unavailable');
        if (btn) {
            btn.style.display = 'inline-block';
            if (fallback) fallback.style.display = 'none';
        }
    }

    async function handleInstallClick() {
        if (!deferredPrompt) return;
        deferredPrompt.prompt();
        try { await deferredPrompt.userChoice; } catch (_) {}
        deferredPrompt = null;
        const btn = document.getElementById('pwa_install_btn');
        if (btn) btn.style.display = 'none';
    }

    // ── Push notifications ──────────────────────────────────────────────────
    function urlBase64ToUint8Array(base64String) {
        const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
        const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
        const rawData = atob(base64);
        const out = new Uint8Array(rawData.length);
        for (let i = 0; i < rawData.length; ++i) out[i] = rawData.charCodeAt(i);
        return out;
    }

    function sameApplicationServerKey(sub, appKey) {
        const current = sub.options && sub.options.applicationServerKey;
        if (!current) return false;
        const bytes = new Uint8Array(current);
        if (bytes.length !== appKey.length) return false;
        for (let i = 0; i < bytes.length; ++i) {
            if (bytes[i] !== appKey[i]) return false;
        }
        return true;
    }

    async function fetchVapidKey() {
        try {
            const r = await fetch('/pwa/vapid_public_key', { credentials: 'same-origin' });
            if (!r.ok) return '';
            return (await r.text()).trim();
        } catch (_) {
            return '';
        }
    }

    async function jsonRpc(url, params) {
        const r = await fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', params }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        return data.result || {};
    }

    async function subscribePush() {
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
        const vapid = await fetchVapidKey();
        if (!vapid) {
            alert('Push notifications aren\'t configured on this server.');
            return;
        }
        const perm = await Notification.requestPermission();
        if (perm !== 'granted') return;
        const reg = await navigator.serviceWorker.ready;
        const appKey = urlBase64ToUint8Array(vapid);
        let sub = await reg.pushManager.getSubscription();
        if (sub && !sameApplicationServerKey(sub, appKey)) {
            // The server rotated its VAPID keys — the old subscription is
            // bound to the old key and would be rejected with a 403.
            try { await sub.unsubscribe(); } catch (_) {}
            sub = null;
        }
        if (!sub) {
            sub = await reg.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: appKey,
            });
        }
        const j = sub.toJSON();
        await jsonRpc('/pwa/subscribe', {
            endpoint: j.endpoint,
            keys: { p256dh: j.keys.p256dh, auth: j.keys.auth },
        });
        const btn = document.getElementById('pwa_push_btn');
        if (btn) btn.textContent = '🔔 Notifications enabled';
    }

    function maybeShowPushButton() {
        const btn = document.getElementById('pwa_push_btn');
        if (!btn) return;
        if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
        btn.style.display = 'inline-block';
        btn.addEventListener('click', subscribePush);
    }

    // ── Init ────────────────────────────────────────────────────────────────
    function init() {
        registerServiceWorker();
        const installBtn = document.getElementById('pwa_install_btn');
        if (installBtn) installBtn.addEventListener('click', handleInstallClick);
        maybeShowPushButton();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
