/**
 * Tableau « Disponible maintenant » — vanilla JS, page portail rendue serveur.
 *
 * Deux comportements :
 *  1. Compte à rebours vivant : chaque badge « N min » décrémente ; à 0, la
 *     carte disparaît (la session est expirée côté serveur aussi).
 *  2. Rafraîchissement léger : toutes les 60 s on recharge la liste, sauf si la
 *     personne est en train de saisir son intention (pour ne pas perdre le texte).
 */
(function () {
    'use strict';

    function tick() {
        document.querySelectorAll('#right_now_board [data-minutes-left]').forEach((badge) => {
            let min = parseInt(badge.dataset.minutesLeft, 10);
            if (isNaN(min)) return;
            min -= 1;
            if (min <= 0) {
                const card = badge.closest('.col-md-6');
                if (card) card.remove();
                return;
            }
            badge.dataset.minutesLeft = min;
            badge.textContent = min + ' min';
        });
    }

    function userIsTyping() {
        const el = document.activeElement;
        if (!el) return false;
        if (el.name === 'note' && el.value) return true;
        return el.tagName === 'INPUT' || el.tagName === 'SELECT';
    }

    function refresh() {
        if (userIsTyping()) return;
        fetch('/right-now', { headers: { 'X-Requested-With': 'fetch' } })
            .then((r) => (r.ok ? r.text() : null))
            .then((html) => {
                if (!html) return;
                const doc = new DOMParser().parseFromString(html, 'text/html');
                const fresh = doc.getElementById('right_now_board');
                const cur = document.getElementById('right_now_board');
                if (fresh && cur && !userIsTyping()) {
                    cur.innerHTML = fresh.innerHTML;
                }
            })
            .catch(() => {});
    }

    function init() {
        if (!document.getElementById('right_now_board')) return;
        setInterval(tick, 60000);
        setInterval(refresh, 60000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
