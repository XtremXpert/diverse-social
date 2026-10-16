/** @odoo-module **/

/**
 * Répondre à un appel depuis une page du site (portail).
 *
 * Sur le site, le Store démarre l'objet Rtc (Rtc.start) avant que les services d'appel ne
 * soient prêts : l'extension « push-to-talk », les sons et les notifications y restent
 * `undefined`, et `joinCall` plante sur `this.pttExtService.subscribe()` (« Répondre » ne fait
 * rien). Le service `discuss.rtc` démarre, lui, après ces dépendances : on les rebranche là.
 */

import { rtcService } from "@mail/discuss/call/common/rtc_service";
import { patch } from "@web/core/utils/patch";

patch(rtcService, {
    start(env, services) {
        const rtc = services["mail.store"].rtc;
        rtc.pttExtService ??= services["discuss.ptt_extension"];
        rtc.soundEffectsService ??= services["mail.sound_effects"];
        rtc.notification ??= services.notification;
        rtc.dialog ??= env.services.dialog;
        return super.start(...arguments);
    },
});
