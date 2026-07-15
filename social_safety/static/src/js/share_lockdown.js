/**
 * Share lockdown — couche JS (best-effort).
 *
 * Retire les balises Open Graph / Twitter card sur les chemins sensibles
 * pour qu'un membre qui colle par accident une URL dans Slack/Discord/
 * Signal ne fasse pas apparaître un aperçu révélateur du site.
 *
 * Le serveur émet déjà un <meta name="robots" content="noindex"> sur ces
 * chemins (voir views/portal_share_lockdown.xml) qui couvre les moteurs de
 * recherche ; ceci gère le cas de l'unfurling des applis de messagerie.
 *
 * Indépendant du bouton de sortie rapide (module social_safety_quick_exit) :
 * la protection anti-partage reste active même sans ce bouton.
 */
(function () {
    'use strict';

    var SENSITIVE_PATHS = /^(?:\/(?:en|fr))?(\/(my|profile|safety|discover|members|groups|governance|gallery|stories|onboarding|messaging|calls|circles|consent|negotiation|vouching|reputation))(\/|$)/;

    function isSensitive() {
        return SENSITIVE_PATHS.test(window.location.pathname);
    }

    function stripShareMeta() {
        if (!isSensitive()) {
            return;
        }
        var selectors = [
            'meta[property^="og:"]',
            'meta[property^="article:"]',
            'meta[name^="twitter:"]',
            'meta[name="description"]',
            'link[rel="canonical"]',
        ];
        for (var i = 0; i < selectors.length; i++) {
            var nodes = document.querySelectorAll(selectors[i]);
            for (var j = 0; j < nodes.length; j++) {
                nodes[j].parentNode.removeChild(nodes[j]);
            }
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', stripShareMeta);
    } else {
        stripShareMeta();
    }
})();
