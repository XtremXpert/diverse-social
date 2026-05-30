/**
 * /social/feed — vanilla JS infinite scroll.
 *
 * Fetches /social/api/feed in batches as the user scrolls. Renders
 * heterogeneous items (post / story / event / event_registration /
 * proposal / gallery) with per-type card templates. Reads + writes
 * /social/api/feed/preferences from a foldable panel. Mark read/unread
 * via /social/api/feed/mark_{read,unread}.
 *
 * Type names + label table mirror social_feed.user_preference.FEED_TYPES —
 * keep in sync.
 */
(function () {
    'use strict';

    const PAGE_SIZE = 20;
    const TYPE_LABELS = {
        post: 'Posts',
        story: 'Stories',
        event: 'Events',
        event_registration: 'Connection RSVPs',
        proposal: 'Proposals',
        gallery: 'Galleries',
    };

    // ── State ────────────────────────────────────────────────────────────────
    let state = {
        offset: 0,
        sort: 'relevance',
        hasMore: true,
        loading: false,
    };

    // ── DOM helpers ──────────────────────────────────────────────────────────
    function $(sel) { return document.querySelector(sel); }
    function el(tag, cls, html) {
        const e = document.createElement(tag);
        if (cls) e.className = cls;
        if (html !== undefined) e.innerHTML = html;
        return e;
    }
    function esc(s) {
        return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
                        .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function fmtDate(iso) {
        if (!iso) return '';
        try {
            const d = new Date(iso);
            return d.toLocaleString();
        } catch (_) { return ''; }
    }
    function timeAgo(iso) {
        if (!iso) return '';
        const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
        if (diff < 60) return 'just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
        return `${Math.floor(diff / 86400)}d`;
    }

    // ── Networking ───────────────────────────────────────────────────────────
    async function fetchFeed(offset, sort) {
        const url = `/social/api/feed?limit=${PAGE_SIZE}&offset=${offset}&sort=${sort}`;
        const r = await fetch(url, { credentials: 'same-origin' });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
    }
    async function jsonRpc(path, params) {
        const r = await fetch(path, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', params: params || {} }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()).result || {};
    }
    async function getPreferences() {
        const r = await fetch('/social/api/feed/preferences', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jsonrpc: '2.0', params: {} }),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return (await r.json()).result || {};
    }

    // ── Card rendering ───────────────────────────────────────────────────────
    function renderCard(item) {
        const card = el('div', 'card mb-3 feed-card');
        card.dataset.type = item.item_type;
        card.dataset.id = item.id;
        if (item.is_read) card.classList.add('feed-card-read');

        const header = el('div', 'card-header d-flex justify-content-between align-items-center py-2');
        header.style.background = '#1a1a2e';
        header.style.color = 'white';
        header.innerHTML = `<span style="font-size:0.85rem;">${typeBadge(item)}</span>
            <span style="font-size:0.75rem; opacity:0.7;">${esc(timeAgo(item.timestamp))}</span>`;
        card.appendChild(header);

        const body = el('div', 'card-body py-3');
        body.innerHTML = renderBody(item);
        card.appendChild(body);

        const footer = el('div', 'card-footer d-flex justify-content-end py-1 bg-white');
        const btn = el('button', 'btn btn-sm btn-link text-decoration-none p-0 feed-mark-btn');
        btn.innerHTML = item.is_read ? '↩️ Mark unread' : '✓ Mark read';
        btn.addEventListener('click', () => toggleRead(card, item));
        footer.appendChild(btn);
        card.appendChild(footer);

        return card;
    }
    function typeBadge(item) {
        const icon = {
            post: '💬', story: '📖', event: '📅', event_registration: '🤝',
            proposal: '🗳️', gallery: '🖼️',
        }[item.item_type] || '•';
        return `${icon} ${esc(TYPE_LABELS[item.item_type] || item.item_type)}`;
    }
    function renderBody(item) {
        switch (item.item_type) {
            case 'post': return `
                <div class="fw-semibold mb-1">${esc(item.author_name)}</div>
                ${item.group_name ? `<div class="text-muted small mb-2">in ${esc(item.group_name)}</div>` : ''}
                <div>${esc(item.content_excerpt || '')}</div>
                <div class="text-muted small mt-2">
                    ❤️ ${item.like_count || 0} · 💬 ${item.comment_count || 0}
                </div>`;
            case 'story': return `
                <div class="fw-semibold mb-1">${esc(item.author_name)}</div>
                <div>${esc(item.name || '')}</div>
                <div class="text-muted small mt-2">
                    👁️ ${item.view_count || 0}
                    ${item.expires_at ? ` · expires ${esc(fmtDate(item.expires_at))}` : ''}
                </div>`;
            case 'event': {
                const conns = (item.connection_attendee_names || []).join(', ');
                return `
                <div class="fw-semibold mb-1">${esc(item.name)}</div>
                <div class="text-muted small">
                    📅 ${esc(fmtDate(item.date_begin))}
                    ${item.organizer_name ? ` · by ${esc(item.organizer_name)}` : ''}
                </div>
                <div class="text-muted small mt-1">
                    👥 ${item.attendee_count || 0} attending
                    ${conns ? ` — incl. ${esc(conns)}` : ''}
                </div>`;
            }
            case 'event_registration': return `
                <div><strong>${esc(item.registrant_name)}</strong> is attending</div>
                <div class="mt-1">${esc(item.event_name)}</div>
                <div class="text-muted small mt-1">📅 ${esc(fmtDate(item.event_date_begin))}</div>`;
            case 'proposal': return `
                <div class="fw-semibold mb-1">${esc(item.title)}</div>
                ${item.author_name ? `<div class="text-muted small">by ${esc(item.author_name)}</div>` : ''}
                <div class="text-muted small mt-2">
                    🗳️ ${item.vote_count || 0} votes
                    ${item.voting_closes_at ? ` · closes ${esc(fmtDate(item.voting_closes_at))}` : ''}
                </div>`;
            case 'gallery': return `
                <div>New photo in <strong>${esc(item.gallery_name)}</strong></div>
                ${item.photo_name ? `<div class="text-muted small">${esc(item.photo_name)}</div>` : ''}
                ${item.submitted_by_name ? `<div class="text-muted small mt-1">by ${esc(item.submitted_by_name)}</div>` : ''}`;
            default:
                return `<pre>${esc(JSON.stringify(item, null, 2))}</pre>`;
        }
    }

    // ── Mark read/unread ─────────────────────────────────────────────────────
    async function toggleRead(card, item) {
        const wasRead = card.classList.contains('feed-card-read');
        const endpoint = wasRead ? '/social/api/feed/mark_unread' : '/social/api/feed/mark_read';
        try {
            const result = await jsonRpc(endpoint, {
                item_type: item.item_type, item_id: item.id,
            });
            if (result.success) {
                card.classList.toggle('feed-card-read');
                const btn = card.querySelector('.feed-mark-btn');
                if (btn) btn.innerHTML = wasRead ? '✓ Mark read' : '↩️ Mark unread';
                item.is_read = !wasRead;
            }
        } catch (_) { /* silent */ }
    }

    // ── Pagination ───────────────────────────────────────────────────────────
    async function loadNextPage() {
        if (state.loading || !state.hasMore) return;
        state.loading = true;
        setStatus('Loading…');
        try {
            const resp = await fetchFeed(state.offset, state.sort);
            if (!resp.success) {
                setStatus('Error loading the feed.');
                return;
            }
            const items = resp.data.items || [];
            const frag = document.createDocumentFragment();
            for (const item of items) frag.appendChild(renderCard(item));
            $('#feed_list').appendChild(frag);
            state.offset += items.length;
            state.hasMore = !!resp.data.has_more;
            setStatus(state.hasMore ? '' : (state.offset === 0 ? 'Nothing to show right now.' : 'You\'re all caught up.'));
        } catch (_) {
            setStatus('Network error.');
        } finally {
            state.loading = false;
        }
    }
    function setStatus(msg) {
        const s = $('#feed_status');
        if (s) s.textContent = msg;
    }
    function resetAndLoad() {
        state.offset = 0;
        state.hasMore = true;
        const list = $('#feed_list');
        if (list) list.innerHTML = '';
        loadNextPage();
    }

    // ── Sort tabs ────────────────────────────────────────────────────────────
    function bindSortTabs() {
        const apply = () => {
            document.querySelectorAll('[data-feed-sort]').forEach(b => {
                if (b.dataset.feedSort === state.sort) {
                    b.classList.add('btn-dark');
                    b.classList.remove('btn-outline-secondary');
                } else {
                    b.classList.remove('btn-dark');
                    b.classList.add('btn-outline-secondary');
                }
            });
        };
        document.querySelectorAll('[data-feed-sort]').forEach(b => {
            b.addEventListener('click', () => {
                state.sort = b.dataset.feedSort;
                apply();
                resetAndLoad();
            });
        });
        apply();
    }

    // ── Preferences panel ────────────────────────────────────────────────────
    function bindPrefsPanel() {
        const toggle = $('#feed_prefs_toggle');
        const panel = $('#feed_prefs_panel');
        if (!toggle || !panel) return;
        toggle.addEventListener('click', async () => {
            const open = panel.style.display !== 'none';
            if (open) {
                panel.style.display = 'none';
                toggle.setAttribute('aria-expanded', 'false');
                return;
            }
            panel.style.display = 'block';
            toggle.setAttribute('aria-expanded', 'true');
            if (!panel.dataset.loaded) {
                await renderPrefsSliders();
                panel.dataset.loaded = '1';
            }
        });
    }

    async function renderPrefsSliders() {
        const container = $('#feed_prefs_sliders');
        if (!container) return;
        let prefs;
        try {
            prefs = await getPreferences();
        } catch (_) {
            container.textContent = 'Could not load preferences.';
            return;
        }
        if (!prefs.success) {
            container.textContent = 'Could not load preferences.';
            return;
        }
        const { boosts = {}, available_types = [], range = { min: 0.1, max: 5.0 } } = prefs.data || {};
        container.innerHTML = '';
        for (const t of available_types) {
            const value = boosts[t] || 1.0;
            const row = el('div', 'mb-2 d-flex align-items-center gap-2');
            row.innerHTML = `
                <label class="me-2" style="min-width:140px;">${esc(TYPE_LABELS[t] || t)}</label>
                <input type="range" min="${range.min}" max="${range.max}" step="0.1"
                       value="${value}" class="form-range flex-grow-1"
                       data-feed-pref-type="${esc(t)}"/>
                <span class="text-muted small" data-feed-pref-label="${esc(t)}"
                      style="min-width:40px; text-align:right;">${value.toFixed(1)}×</span>`;
            container.appendChild(row);
        }
        wirePrefSliders();
    }
    let prefsTimer = null;
    function wirePrefSliders() {
        document.querySelectorAll('[data-feed-pref-type]').forEach(input => {
            input.addEventListener('input', () => {
                const t = input.dataset.feedPrefType;
                const v = parseFloat(input.value);
                const lbl = document.querySelector(`[data-feed-pref-label="${t}"]`);
                if (lbl) lbl.textContent = v.toFixed(1) + '×';
                clearTimeout(prefsTimer);
                prefsTimer = setTimeout(async () => {
                    try {
                        await jsonRpc('/social/api/feed/preferences/set', {
                            item_type: t, boost_factor: v,
                        });
                    } catch (_) { /* silent */ }
                }, 500);
            });
        });
    }

    // ── Infinite scroll sentinel ─────────────────────────────────────────────
    function bindSentinel() {
        const sentinel = $('#feed_sentinel');
        if (!sentinel) return;
        const observer = new IntersectionObserver(entries => {
            for (const e of entries) {
                if (e.isIntersecting) loadNextPage();
            }
        }, { rootMargin: '300px' });
        observer.observe(sentinel);
    }

    // ── Init ─────────────────────────────────────────────────────────────────
    function init() {
        if (!$('#feed_list')) return;
        bindSortTabs();
        bindPrefsPanel();
        bindSentinel();
        loadNextPage();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
