/** @odoo-module **/

/**
 * Service portail pour social_calling : présence + fenêtre d'appel entrant.
 *
 * Pourquoi un vrai service Odoo (et plus un IIFE vanilla) :
 *  - L'ancienne approche accédait au bus via `owl.__apps__[0]`, qui n'existe pas
 *    dans cette version d'OWL (le Set des apps est dans window.__OWL_DEVTOOLS__).
 *    Résultat : le code n'atteignait jamais bus_service et ne faisait rien.
 *  - Un service déclaré avec `dependencies: ["bus_service"]` reçoit bus_service
 *    proprement (le frontend public démarre tous les services via startServices).
 *
 * Présence : sur une page portail, rien n'ouvre le websocket par défaut, donc le
 * service natif imStatusService ne reporte jamais la présence (BUS:CONNECT ne se
 * déclenche pas). Or social_calling grise les boutons d'appel selon im_status. On
 * ouvre donc explicitement le bus et on envoie update_presence à la connexion,
 * puis via un heartbeat. Le serveur repasse l'utilisateur 'offline' à la
 * fermeture du websocket, donc im_status reste exact.
 */

import { registry } from "@web/core/registry";

const TOPIC = "social_calling/incoming_call";

// ── Sonnerie (WebAudio, pas de fichier média à charger) ─────────────────────
let audioCtx = null;
let ringTimer = null;

function startRing() {
    try {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        if (!Ctx) return;
        audioCtx = new Ctx();
        const beep = () => {
            if (!audioCtx) return;
            const osc = audioCtx.createOscillator();
            const gain = audioCtx.createGain();
            osc.type = "sine";
            osc.frequency.value = 480;
            gain.gain.setValueAtTime(0.0001, audioCtx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.15, audioCtx.currentTime + 0.05);
            gain.gain.exponentialRampToValueAtTime(0.0001, audioCtx.currentTime + 0.9);
            osc.connect(gain).connect(audioCtx.destination);
            osc.start();
            osc.stop(audioCtx.currentTime + 1);
        };
        beep();
        ringTimer = setInterval(beep, 2500);
    } catch (_) { /* l'autoplay peut être bloqué : on reste silencieux */ }
}

function stopRing() {
    if (ringTimer) { clearInterval(ringTimer); ringTimer = null; }
    if (audioCtx) { try { audioCtx.close(); } catch (_) {} audioCtx = null; }
}

// ── Fenêtre d'appel ─────────────────────────────────────────────────────────
let overlayEl = null;

function esc(s) {
    return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function dismiss() {
    stopRing();
    if (overlayEl) { overlayEl.remove(); overlayEl = null; }
}

function accept(roomUrl) {
    stopRing();
    window.location.href = roomUrl;
}

// Déduplication : marque une session comme déjà traitée (répondue/refusée) pour
// que le rejeu de la notif par le bus (à la reconnexion sur la page Discuss) ne
// fasse pas réapparaître/resonner l'overlay.
function handledKey(sid) { return "sc_call_handled_" + sid; }
function isHandled(sid) {
    try { return sessionStorage.getItem(handledKey(sid)) === "1"; } catch (_) { return false; }
}
function markHandled(sid) {
    try { sessionStorage.setItem(handledKey(sid), "1"); } catch (_) {}
}

function showIncoming(payload) {
    // Jamais d'appel entrant pour une session déjà traitée (anti-rejeu du bus).
    if (isHandled(payload.session_id)) return;

    // Une seule fenêtre à la fois : un nouvel appel remplace l'ancien.
    dismiss();

    const isVideo = payload.call_type === "video";
    overlayEl = document.createElement("div");
    overlayEl.id = "sc_incoming_overlay";
    overlayEl.innerHTML = `
        <div class="sc-card" role="dialog" aria-label="Appel entrant">
            <div class="sc-pulse">${isVideo ? "📹" : "📞"}</div>
            <div class="sc-title">Appel entrant</div>
            <div class="sc-caller">${esc(payload.caller_name)}</div>
            <div class="sc-sub">${isVideo ? "Appel vidéo" : "Appel audio"}</div>
            <div class="sc-actions">
                <button type="button" class="sc-btn sc-decline">Refuser</button>
                <button type="button" class="sc-btn sc-accept">Répondre</button>
            </div>
        </div>`;
    document.body.appendChild(overlayEl);

    overlayEl.querySelector(".sc-accept").addEventListener("click", () => {
        markHandled(payload.session_id);
        accept(payload.room_url);
    });
    overlayEl.querySelector(".sc-decline").addEventListener("click", () => {
        markHandled(payload.session_id);
        // Aucune session serveur à refuser : l'appel vit dans le canal Discuss.
        dismiss();
    });

    startRing();

    // Auto-fermeture après 60 s si l'utilisateur n'agit pas.
    overlayEl.dataset.sid = String(payload.session_id);
    setTimeout(() => {
        if (overlayEl && overlayEl.dataset.sid === String(payload.session_id)) dismiss();
    }, 60_000);
}

// ── Service ─────────────────────────────────────────────────────────────────
const socialCallingService = {
    dependencies: ["bus_service"],
    start(env, { bus_service }) {
        // Présence : indispensable au dégrisage des boutons d'appel.
        const sendPresence = () => {
            try { bus_service.send("update_presence", { inactivity_period: 0 }); } catch (_) {}
        };
        bus_service.addEventListener("BUS:CONNECT", sendPresence);
        bus_service.start();                  // ouvre le websocket (sinon BUS:CONNECT ne vient jamais sur le portail)
        setInterval(sendPresence, 55_000);    // heartbeat (< KEEP_ALIVE)

        // Appels entrants : le serveur _sendone vers callee.partner_id, dont le
        // canal est auto-abonné côté serveur pour l'utilisateur connecté.
        bus_service.subscribe(TOPIC, (payload) => { if (payload) showIncoming(payload); });

        // Marqueur de disponibilité pour les tests E2E (sans effet fonctionnel).
        document.documentElement.dataset.scIncomingReady = "1";
    },
};

registry.category("services").add("social_calling.incoming_call", socialCallingService);
