/** @odoo-module **/

/**
 * Quand il ne reste qu'une personne dans l'appel.
 *
 * - Appel à deux : le serveur termine la session. Odoo annonce toute session fermée par le
 *   serveur comme une déconnexion (« Disconnected from the call by the server », en
 *   avertissement). Le serveur prévient juste avant quand c'est une fin normale
 *   (`social_calling_discuss/ended_alone`) : on affiche alors un message simple.
 * - Appel de groupe : le serveur demande si on reste (`social_calling_discuss/alone`). Sans
 *   réponse, l'appel se termine après le délai donné, sauf si quelqu'un est revenu.
 */

import { Rtc } from "@mail/discuss/call/common/rtc_service";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { patch } from "@web/core/utils/patch";

const endedAlone = new Set();

registry.category("services").add("social_calling_discuss.call_end_alone", {
    dependencies: ["bus_service", "dialog", "mail.store"],
    start(env, { bus_service, dialog, "mail.store": store }) {
        bus_service.subscribe("social_calling_discuss/ended_alone", ({ sessionId }) => {
            endedAlone.add(sessionId);
        });
        bus_service.subscribe("social_calling_discuss/alone", ({ sessionId, timeout }) => {
            const rtc = store.rtc;
            if (!rtc || rtc.localSession?.id !== sessionId) {
                return;
            }
            const channel = rtc.localChannel;
            const inThisCall = () => rtc.localSession?.id === sessionId;
            const alone = () => inThisCall() && (channel?.rtc_session_ids.length ?? 0) <= 1;
            let watch;
            let deadline;
            const stop = () => {
                clearInterval(watch);
                clearTimeout(deadline);
            };
            const close = dialog.add(
                ConfirmationDialog,
                {
                    title: _t("Vous êtes seul dans l'appel"),
                    body: _t(
                        "Tout le monde est parti. Sans réponse, l'appel se terminera dans %s secondes.",
                        timeout
                    ),
                    confirmLabel: _t("Raccrocher"),
                    confirm: () => {
                        stop();
                        if (inThisCall()) {
                            rtc.leaveCall(channel);
                        }
                    },
                    cancelLabel: _t("Rester"),
                    cancel: stop,
                },
                { onClose: stop }
            );
            // Quelqu'un revient, ou l'appel est fini ailleurs : la question ne se pose plus.
            watch = setInterval(() => {
                if (!alone()) {
                    close();
                }
            }, 1000);
            deadline = setTimeout(() => {
                close();
                if (alone()) {
                    rtc.leaveCall(channel);
                }
            }, timeout * 1000);
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
