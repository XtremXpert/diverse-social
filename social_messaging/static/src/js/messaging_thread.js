/** @odoo-module **/

import { Component, onMounted, onWillStart, useRef, useState, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const ALLOWED_EMOJIS = ["👍", "❤️", "😂", "😮", "😢", "👏"];

function getCsrf() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.getAttribute("content");
    const inp = document.querySelector('input[name="csrf_token"]');
    return inp ? inp.value : "";
}

/**
 * Message bubble — renders text + inline images + attachments + reactions.
 */
export class MessageBubble extends Component {
    static template = "social_messaging.MessageBubble";
    static props = {
        message: Object,
        onReact: Function,
        currentUserId: Number,
    };

    setup() {
        this.state = useState({ pickerOpen: false });
        this.allowedEmojis = ALLOWED_EMOJIS;
    }

    get imageAttachments() {
        return (this.props.message.attachments || []).filter((a) => a.is_image);
    }

    get fileAttachments() {
        return (this.props.message.attachments || []).filter((a) => !a.is_image);
    }

    togglePicker() {
        this.state.pickerOpen = !this.state.pickerOpen;
    }

    onPick(emoji) {
        this.state.pickerOpen = false;
        this.props.onReact(this.props.message.id, emoji);
    }

    hasMyReaction(reaction) {
        return reaction.user_ids.includes(this.props.currentUserId);
    }
}

/**
 * Composer — textarea + file picker + bouton envoyer.
 */
export class MessageComposer extends Component {
    static template = "social_messaging.MessageComposer";
    static props = {
        onSend: Function,
        disabled: { type: Boolean, optional: true },
    };

    setup() {
        this.state = useState({
            text: "",
            files: [],   // [{file, previewUrl}]
            sending: false,
        });
        this.fileInputRef = useRef("fileInput");
        this.textareaRef = useRef("textarea");
    }

    openFilePicker() {
        if (this.fileInputRef.el) this.fileInputRef.el.click();
    }

    onFilesChosen(ev) {
        const files = Array.from(ev.target.files || []);
        for (const f of files) {
            const isImage = (f.type || "").startsWith("image/");
            this.state.files.push({
                file: f,
                name: f.name,
                isImage,
                previewUrl: isImage ? URL.createObjectURL(f) : null,
            });
        }
        // Reset the input so the same file can be re-selected.
        ev.target.value = "";
    }

    removeFile(idx) {
        const entry = this.state.files[idx];
        if (entry && entry.previewUrl) URL.revokeObjectURL(entry.previewUrl);
        this.state.files.splice(idx, 1);
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.submit();
        }
    }

    async submit() {
        const text = (this.state.text || "").trim();
        const files = this.state.files.map((e) => e.file);
        if (!text && !files.length) return;
        this.state.sending = true;
        try {
            const ok = await this.props.onSend(text, files);
            if (ok) {
                this.state.text = "";
                for (const e of this.state.files) {
                    if (e.previewUrl) URL.revokeObjectURL(e.previewUrl);
                }
                this.state.files = [];
                if (this.textareaRef.el) this.textareaRef.el.focus();
            }
        } finally {
            this.state.sending = false;
        }
    }
}

/**
 * Composant racine : MessagingThread.
 */
export class MessagingThread extends Component {
    static template = "social_messaging.MessagingThread";
    static components = { MessageBubble, MessageComposer };
    static props = {
        threadId: Number,
        currentUserId: Number,
    };

    setup() {
        this.busService = useService("bus_service");
        this.state = useState({
            messages: [],
            loading: true,
            error: null,
        });
        this.scrollRef = useRef("scroll");
        this._seenIds = new Set();

        onWillStart(async () => {
            await this.loadInitial();
        });

        onMounted(() => {
            this.scrollToBottom();
            // Listen to bus events broadcast by message._broadcast().
            this.busService.subscribe(
                "social_messaging.update",
                this._onBusUpdate.bind(this),
            );
            this.busService.start();
        });

        // Auto-scroll quand de nouveaux messages arrivent.
        useEffect(
            () => {
                this.scrollToBottom();
            },
            () => [this.state.messages.length],
        );
    }

    async loadInitial() {
        try {
            const data = await this._json(
                `/my/messages/${this.props.threadId}/poll?since_id=0`,
                { method: "GET" },
            );
            if (data.ok) {
                for (const m of data.messages) {
                    this._addMessage(m);
                }
            }
        } catch (e) {
            this.state.error = _t("Unable to load the conversation.");
        } finally {
            this.state.loading = false;
        }
    }

    _addMessage(msg) {
        if (this._seenIds.has(msg.id)) return;
        this._seenIds.add(msg.id);
        this.state.messages.push(msg);
    }

    _replaceMessage(msg) {
        const idx = this.state.messages.findIndex((m) => m.id === msg.id);
        if (idx >= 0) {
            this.state.messages.splice(idx, 1, msg);
        } else {
            this._addMessage(msg);
        }
    }

    async _onBusUpdate(payload) {
        if (!payload || payload.thread_id !== this.props.threadId) return;
        const msgId = payload.message_id;
        if (!msgId) return;
        // Re-fetch the complete message (with up-to-date attachments + reactions).
        try {
            const data = await this._json(
                `/my/messages/${this.props.threadId}/message/${msgId}`,
                { method: "GET" },
            );
            if (data.ok && data.message) {
                this._replaceMessage(data.message);
            }
        } catch (e) {
            // Notif silencieuse : pas critique.
        }
    }

    async sendMessage(text, files) {
        const fd = new FormData();
        if (text) fd.append("content", text);
        fd.append("csrf_token", getCsrf());
        for (const f of files) {
            fd.append("attachments", f, f.name);
        }
        try {
            const data = await this._json(
                `/my/messages/${this.props.threadId}/send`,
                { method: "POST", body: fd },
            );
            if (data.ok && data.message) {
                this._replaceMessage(data.message);
                return true;
            }
            this.state.error = data.error || _t("Send failed");
            return false;
        } catch (e) {
            this.state.error = _t("Network error");
            return false;
        }
    }

    async react(messageId, emoji) {
        const fd = new FormData();
        fd.append("message_id", String(messageId));
        fd.append("emoji", emoji);
        fd.append("csrf_token", getCsrf());
        try {
            const data = await this._json(
                `/my/messages/${this.props.threadId}/react`,
                { method: "POST", body: fd },
            );
            if (data.ok && data.message) {
                this._replaceMessage(data.message);
            }
        } catch (e) {
            // silencieux
        }
    }

    async _json(url, opts) {
        const resp = await fetch(url, { credentials: "same-origin", ...opts });
        return await resp.json();
    }

    scrollToBottom() {
        const el = this.scrollRef.el;
        if (el) el.scrollTop = el.scrollHeight;
    }
}

registry.category("public_components").add("social_messaging.thread", MessagingThread);
