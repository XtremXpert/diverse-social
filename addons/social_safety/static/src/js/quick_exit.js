/**
 * Sortie rapide + camouflage visuel.
 *
 * 1. Quick exit : redirige vers un site neutre sans laisser de trace
 *    dans l'historique du navigateur (window.location.replace).
 *    Déclencheurs :
 *      - Clic sur le bouton #social_quick_exit
 *      - Double-appui sur la touche Échap (< 500 ms)
 *
 * 2. Camouflage : sur les pages portail sensibles (/my/, /profile/, etc.),
 *    swap document.title et le favicon pour qu'un coup d'œil de loin sur
 *    l'onglet ne révèle pas la nature du site. Configurable via
 *    ir.config_parameter (social_safety.camouflage_title / .favicon).
 */
(function () {
    'use strict';

    var btn = function () {
        return document.getElementById('social_quick_exit');
    };

    var getData = function (key, fallback) {
        var el = btn();
        return (el && el.dataset[key]) ? el.dataset[key] : fallback;
    };

    // ── 1. Quick exit ───────────────────────────────────────────────────────

    var EXIT_URL = getData('exitUrl', 'https://www.meteomedia.com/');

    function exit() {
        window.location.replace(EXIT_URL);
    }

    var escCount = 0;
    var escTimer = null;

    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            escCount++;
            clearTimeout(escTimer);
            if (escCount >= 2) {
                exit();
            }
            escTimer = setTimeout(function () { escCount = 0; }, 500);
        }
    });

    // ── 2. Camouflage visuel ────────────────────────────────────────────────
    //
    // Patterns de paths à camoufler. On garde large pour ne pas oublier de
    // nouvelles routes portail. Les pages publiques (/, /web/login,
    // /membership pour l'opt-in) gardent leur branding normal.
    var CAMOUFLAGE_PATHS = /^\/(my|profile|safety|discover|members|groups|governance|gallery|stories|onboarding|messaging|calls|circles|consent|negotiation|vouching|reputation)(\/|$)/;

    function shouldCamouflage() {
        return CAMOUFLAGE_PATHS.test(window.location.pathname);
    }

    function applyCamouflage() {
        if (!shouldCamouflage()) {
            return;
        }
        var title = getData('camouflageTitle', '');
        var favicon = getData('camouflageFavicon', '');

        if (title) {
            document.title = title;
        }
        if (favicon) {
            // Retire les icônes existantes (Odoo en pose plusieurs : icon,
            // shortcut icon, apple-touch-icon) puis pose la nôtre seule.
            var existing = document.querySelectorAll('link[rel~="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]');
            for (var i = 0; i < existing.length; i++) {
                existing[i].parentNode.removeChild(existing[i]);
            }
            var link = document.createElement('link');
            link.rel = 'icon';
            link.href = favicon;
            document.head.appendChild(link);
        }
    }

    // ── Wiring ──────────────────────────────────────────────────────────────

    function wireButton() {
        var el = btn();
        if (el) {
            el.addEventListener('click', exit);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () {
            wireButton();
            applyCamouflage();
        });
    } else {
        wireButton();
        applyCamouflage();
    }
})();
