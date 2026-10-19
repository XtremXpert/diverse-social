/** @odoo-module **/

/**
 * Appel terminé par le serveur parce qu'il ne restait qu'une personne.
 *
 * Odoo annonce toute session fermée par le serveur comme une déconnexion (« Disconnected from
 * the call by the server », en avertissement). Le serveur prévient juste avant quand c'est une
 * fin normale (`social_calling_discuss/ended_alone`) : on affiche alors un message simple.
 */

import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

const endedAlone = new Set();

registry.category("services").add("social_calling_discuss.call_end_alone", {
    dependencies: ["bus_service"],
    start(env, { bus_service }) {
        bus_service.subscribe("social_calling_discuss/ended_alone", ({ sessionId }) => {
            endedAlone.add(sessionId);
        });
    },
});

patch(Rtc.prototype, {
    notifyServerDisconnect() {
        if (endedAlone.delete(this.localSession?.id)) {
            this.notification?.add(_t("Appel terminé : il ne restait que vous."), { type: "info" });
            return;
        }
        return super.notifyServerDisconnect(...arguments);
    },
});
