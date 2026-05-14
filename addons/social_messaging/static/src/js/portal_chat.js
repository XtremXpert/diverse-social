(function () {
    'use strict';

    var threadId = null;
    var lastMessageId = 0;
    var pollInterval = null;
    var POLL_DELAY = 5000;

    function init() {
        var container = document.getElementById('sn_chat_container');
        if (!container) return;

        threadId = parseInt(container.dataset.threadId, 10);
        lastMessageId = parseInt(container.dataset.lastMessageId || '0', 10);

        scrollToBottom();
        bindSendForm();
        startPolling();
    }

    function scrollToBottom() {
        var body = document.getElementById('sn_chat_body');
        if (body) body.scrollTop = body.scrollHeight;
    }

    function bindSendForm() {
        var form = document.getElementById('sn_send_form');
        if (!form) return;
        form.addEventListener('submit', function (e) {
            e.preventDefault();
            sendMessage();
        });

        var input = document.getElementById('sn_message_input');
        if (input) {
            input.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
        }
    }

    function getCsrf() {
        var meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.getAttribute('content');
        var inp = document.querySelector('input[name="csrf_token"]');
        return inp ? inp.value : '';
    }

    function sendMessage() {
        var input = document.getElementById('sn_message_input');
        var btn = document.getElementById('sn_send_btn');
        var content = input ? input.value.trim() : '';
        if (!content) return;

        if (btn) btn.disabled = true;

        var body = new URLSearchParams();
        body.append('content', content);
        body.append('csrf_token', getCsrf());

        fetch('/my/messages/' + threadId + '/send', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: body.toString(),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.ok) {
                appendMessage(data.message);
                lastMessageId = Math.max(lastMessageId, data.message.id);
                if (input) input.value = '';
                scrollToBottom();
            }
        })
        .catch(function () {})
        .finally(function () {
            if (btn) btn.disabled = false;
            if (input) input.focus();
        });
    }

    function startPolling() {
        pollInterval = setInterval(poll, POLL_DELAY);
        document.addEventListener('visibilitychange', function () {
            if (document.hidden) {
                clearInterval(pollInterval);
            } else {
                pollInterval = setInterval(poll, POLL_DELAY);
                poll();
            }
        });
    }

    function poll() {
        fetch('/my/messages/' + threadId + '/poll?since_id=' + lastMessageId, {
            credentials: 'same-origin',
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.ok || !data.messages.length) return;
            data.messages.forEach(function (msg) {
                if (msg.id > lastMessageId) {
                    appendMessage(msg);
                    lastMessageId = msg.id;
                }
            });
            scrollToBottom();
        })
        .catch(function () {});
    }

    function appendMessage(msg) {
        var body = document.getElementById('sn_chat_body');
        if (!body) return;

        var bubble = document.createElement('div');
        bubble.className = 'sn-bubble-wrap ' + (msg.is_mine ? 'sn-mine' : 'sn-theirs');
        bubble.dataset.msgId = msg.id;

        var inner = document.createElement('div');
        inner.className = 'sn-bubble';
        inner.textContent = msg.content;

        var meta = document.createElement('div');
        meta.className = 'sn-bubble-meta';
        meta.textContent = msg.create_date;

        bubble.appendChild(inner);
        bubble.appendChild(meta);
        body.appendChild(bubble);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
