/**
 * Widget cloche de notifications pour le portail Diverse.
 * Vanilla JS — aucune dépendance OWL/AMD.
 */
(function () {
    'use strict';

    const API_LIST  = '/social/api/notifications?limit=15';
    const API_READ  = (id) => `/social/api/notifications/${id}/read`;
    const API_ALL   = '/social/api/notifications/read_all';
    const POLL_MS   = 30_000;

    const TYPE_ICONS = {
        connection_request:   '🤝',
        connection_accepted:  '✅',
        post_like:            '❤️',
        post_comment:         '💬',
        comment_reply:        '↩️',
        new_message:          '✉️',
        profile_visit:        '👁️',
        daily_digest:         '📊',
        event_registration:   '📅',
        group_join_request:   '👥',
        group_join_approved:  '✅',
        proposal_voting:      '🗳️',
        story_new:            '📖',
        gallery_photo_approved: '🖼️',
        gallery_photo_rejected: '❌',
        vouching_received:    '⭐',
        circle_added:         '🔵',
    };

    function icon(type) {
        return TYPE_ICONS[type] || '🔔';
    }

    function timeAgo(isoStr) {
        if (!isoStr) return '';
        const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
        if (diff < 60)  return 'À l\'instant';
        if (diff < 3600) return `Il y a ${Math.floor(diff / 60)} min`;
        if (diff < 86400) return `Il y a ${Math.floor(diff / 3600)} h`;
        return `Il y a ${Math.floor(diff / 86400)} j`;
    }

    async function apiFetch(url, method = 'GET') {
        const opts = { method, credentials: 'same-origin' };
        if (method === 'POST') {
            opts.headers = { 'Content-Type': 'application/x-www-form-urlencoded' };
        }
        const r = await fetch(url, opts);
        if (!r.ok) throw new Error(r.statusText);
        return r.json();
    }

    class NotificationBell {
        constructor(container) {
            this.container = container;
            this.badge     = container.querySelector('#sn_badge');
            this.dropdown  = container.querySelector('#sn_dropdown');
            this.list      = container.querySelector('#sn_list');
            this.btnAll    = container.querySelector('#sn_read_all');
            this.unread    = 0;

            container.querySelector('#sn_trigger').addEventListener('click', (e) => {
                e.stopPropagation();
                this.toggle();
            });
            this.btnAll.addEventListener('click', () => this.markAllRead());
            document.addEventListener('click', () => this.close());

            this.load();
            setInterval(() => this.load(), POLL_MS);
        }

        async load() {
            try {
                const data = await apiFetch(API_LIST);
                if (!data.success) return;
                this.unread = data.data.unread_count;
                this.render(data.data.notifications);
                this.updateBadge();
            } catch (_) { /* silencieux si non authentifié */ }
        }

        render(notifs) {
            if (!notifs.length) {
                this.list.innerHTML = '<li class="sn-empty">Aucune notification</li>';
                return;
            }
            this.list.innerHTML = notifs.map(n => `
                <li class="sn-item${n.is_read ? ' sn-read' : ''}"
                    data-id="${n.id}"
                    data-url="${n.url || ''}">
                    <span class="sn-icon">${icon(n.type)}</span>
                    <div class="sn-content">
                        <div class="sn-body">${this._esc(n.body || '')}</div>
                        <div class="sn-time">${timeAgo(n.create_date)}</div>
                    </div>
                    ${!n.is_read ? '<span class="sn-dot"></span>' : ''}
                </li>
            `).join('');
            this.list.querySelectorAll('.sn-item').forEach(el => {
                el.addEventListener('click', () => this.clickNotif(el));
            });
        }

        async clickNotif(el) {
            const id  = parseInt(el.dataset.id, 10);
            const url = el.dataset.url;
            if (!el.classList.contains('sn-read')) {
                try { await apiFetch(API_READ(id), 'POST'); } catch (_) {}
                el.classList.add('sn-read');
                el.querySelector('.sn-dot')?.remove();
                this.unread = Math.max(0, this.unread - 1);
                this.updateBadge();
            }
            if (url) window.location.href = url;
        }

        async markAllRead() {
            try {
                await apiFetch(API_ALL, 'POST');
                this.unread = 0;
                this.updateBadge();
                this.list.querySelectorAll('.sn-item').forEach(el => {
                    el.classList.add('sn-read');
                    el.querySelector('.sn-dot')?.remove();
                });
            } catch (_) {}
        }

        updateBadge() {
            if (this.unread > 0) {
                this.badge.textContent = this.unread > 99 ? '99+' : this.unread;
                this.badge.style.display = 'flex';
            } else {
                this.badge.style.display = 'none';
            }
        }

        toggle() {
            const open = this.dropdown.style.display !== 'none';
            if (open) {
                this.close();
            } else {
                this.dropdown.style.display = 'block';
                this.load();
            }
        }

        close() {
            this.dropdown.style.display = 'none';
        }

        _esc(s) {
            return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }
    }

    // ── Bus Odoo (facultatif) ──────────────────────────────────────────────────
    // Si le service bus est disponible côté portail, on l'utilise en plus du poll.
    function tryConnectBus(bell) {
        if (typeof owl === 'undefined') return;
        try {
            const env = owl.__apps__?.[0]?.env;
            const busService = env?.services?.['bus_service'];
            if (!busService) return;
            busService.addChannel('social_notification');
            busService.addEventListener('notification', ({ detail: notifs }) => {
                for (const n of notifs) {
                    if (n.type === 'social_notification') {
                        bell.unread++;
                        bell.updateBadge();
                    }
                }
            });
        } catch (_) {}
    }

    // ── Init ──────────────────────────────────────────────────────────────────
    // Le bundle web.assets_frontend est chargé en lazy : il s'exécute souvent
    // après l'émission de DOMContentLoaded, donc on initialise immédiatement
    // si le DOM est déjà prêt.
    function init() {
        const container = document.getElementById('social_notif_bell');
        if (!container) return;
        const bell = new NotificationBell(container);
        tryConnectBus(bell);
    }
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
