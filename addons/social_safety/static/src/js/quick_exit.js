/**
 * Sortie rapide — redirige vers un site neutre sans laisser de trace
 * dans l'historique du navigateur (window.location.replace).
 *
 * Déclencheurs :
 *  - Clic sur le bouton #social_quick_exit
 *  - Double-appui sur la touche Échap
 */
(function () {
    'use strict';

    var EXIT_URL = (function () {
        var el = document.getElementById('social_quick_exit');
        return el ? (el.dataset.exitUrl || 'https://www.meteomedia.com/') : 'https://www.meteomedia.com/';
    })();

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

    document.addEventListener('DOMContentLoaded', function () {
        var btn = document.getElementById('social_quick_exit');
        if (btn) {
            btn.addEventListener('click', exit);
        }
    });
})();
