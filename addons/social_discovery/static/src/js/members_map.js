/**
 * Members map — vanilla JS, no OWL.
 *
 * Loads point batches from /members/map.json keyed by the current map viewport
 * (bbox). Reloads on every moveend, debounced so dragging doesn't spam the
 * backend.
 */
(function () {
    'use strict';

    const DEBOUNCE_MS = 350;
    const STORAGE_KEY = 'members_map_view';

    function init() {
        const el = document.getElementById('members_map');
        if (!el || typeof L === 'undefined') return;

        // Leaflet's default marker icons reference images via a relative path
        // that breaks under Odoo's asset bundling. Pin them to the static lib.
        delete L.Icon.Default.prototype._getIconUrl;
        L.Icon.Default.mergeOptions({
            iconRetinaUrl: '/social_discovery/static/lib/leaflet/images/marker-icon-2x.png',
            iconUrl:       '/social_discovery/static/lib/leaflet/images/marker-icon.png',
            shadowUrl:     '/social_discovery/static/lib/leaflet/images/marker-shadow.png',
        });

        const defaultLat = parseFloat(el.dataset.defaultLat) || 46.0;
        const defaultLng = parseFloat(el.dataset.defaultLng) || -72.0;
        const defaultZoom = parseInt(el.dataset.defaultZoom, 10) || 7;
        const endpoint = el.dataset.endpoint || '/members/map.json';

        const initialView = restoreView() || { lat: defaultLat, lng: defaultLng, zoom: defaultZoom };
        const map = L.map(el, { worldCopyJump: true })
            .setView([initialView.lat, initialView.lng], initialView.zoom);

        L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 18,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>',
        }).addTo(map);

        const markers = L.layerGroup().addTo(map);
        const status = document.getElementById('members_map_status');

        let reloadTimer = null;
        let lastBbox = '';

        function setStatus(msg) {
            if (status) status.textContent = msg || '';
        }

        function persistView() {
            const c = map.getCenter();
            try {
                localStorage.setItem(STORAGE_KEY, JSON.stringify({
                    lat: c.lat, lng: c.lng, zoom: map.getZoom(),
                }));
            } catch (_) { /* private mode etc. */ }
        }

        async function reload() {
            const b = map.getBounds();
            const bbox = [
                b.getSouth().toFixed(5),
                b.getWest().toFixed(5),
                b.getNorth().toFixed(5),
                b.getEast().toFixed(5),
            ].join(',');
            if (bbox === lastBbox) return;
            lastBbox = bbox;

            setStatus('Loading…');
            try {
                const r = await fetch(`${endpoint}?bbox=${bbox}`, { credentials: 'same-origin' });
                if (!r.ok) {
                    if (r.status === 403) {
                        setStatus('Not authorized.');
                    } else {
                        setStatus(`Error ${r.status}`);
                    }
                    return;
                }
                const data = await r.json();
                if (!data.success) {
                    setStatus('Error loading members.');
                    return;
                }
                renderPoints(data.points);
                setStatus(`${data.count} member${data.count === 1 ? '' : 's'} in view`);
            } catch (_) {
                setStatus('Network error.');
            }
        }

        function scheduleReload() {
            clearTimeout(reloadTimer);
            reloadTimer = setTimeout(reload, DEBOUNCE_MS);
        }

        function renderPoints(points) {
            markers.clearLayers();
            for (const p of points) {
                const m = L.marker([p.lat, p.lng]);
                const safeName = escapeHtml(p.name || '');
                const safeCity = escapeHtml(p.city || '');
                m.bindPopup(
                    `<div class="members_map_popup">
                        <strong>${safeName}</strong>
                        ${safeCity ? `<br/><span class="text-muted small">${safeCity}</span>` : ''}
                        <br/><a href="/profile/${encodeURIComponent(p.user_id)}">View profile</a>
                    </div>`
                );
                m.addTo(markers);
            }
        }

        function escapeHtml(s) {
            return s.replace(/&/g, '&amp;').replace(/</g, '&lt;')
                    .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function restoreView() {
            try {
                const raw = localStorage.getItem(STORAGE_KEY);
                if (!raw) return null;
                const v = JSON.parse(raw);
                if (typeof v.lat !== 'number' || typeof v.lng !== 'number') return null;
                return v;
            } catch (_) {
                return null;
            }
        }

        map.on('moveend', () => {
            persistView();
            scheduleReload();
        });

        reload();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
