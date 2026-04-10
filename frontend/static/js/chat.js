/* Smart Vision Chat Widget */
(function () {
    function renderWidget() {
        if (document.getElementById('chat-widget-root')) return;
        const root = document.createElement('div');
        root.id = 'chat-widget-root';
        root.className = 'chat-widget';
        root.innerHTML = `
            <button type="button" class="chat-toggle" aria-label="Open chat" title="Parking Assistant">
                <i class="fas fa-comments"></i>
            </button>
            <div class="chat-panel" id="chat-panel" role="dialog" aria-label="Parking assistant chat">
                <div class="chat-header">
                    <i class="fas fa-robot"></i>
                    <span>Parking Assistant</span>
                </div>
                <div class="chat-messages" id="chat-messages"></div>
                <form class="chat-form" id="chat-form">
                    <input type="text" id="chat-input" placeholder="Ask about parking..." maxlength="2000" autocomplete="off">
                    <button type="submit" id="chat-send">Send</button>
                </form>
            </div>
        `;
        document.body.appendChild(root);

        const toggle = root.querySelector('.chat-toggle');
        const panel = document.getElementById('chat-panel');
        const messagesEl = document.getElementById('chat-messages');
        const form = document.getElementById('chat-form');
        const input = document.getElementById('chat-input');
        const sendBtn = document.getElementById('chat-send');

        toggle.addEventListener('click', function () {
            panel.classList.toggle('open');
            if (panel.classList.contains('open')) {
                input.focus();
                if (messagesEl.children.length === 0) {
                    appendMessage('Hi! I\'m your parking assistant. Ask me about availability, how to reserve a slot, add a car, or anything else.', 'bot', 'faq');
                }
            }
        });

        form.addEventListener('submit', async function (e) {
            e.preventDefault();
            const text = (input.value || '').trim();
            if (!text) return;
            input.value = '';
            appendMessage(text, 'user');
            sendBtn.disabled = true;
            const loadingEl = appendLoading();
            try {
                const data = await api.chat(text);
                removeLoading(loadingEl);
                appendMessage(data.reply, 'bot', data.source);
            } catch (err) {
                removeLoading(loadingEl);
                const msg = err.message || (err.data && (err.data.detail || err.data.message)) || 'Sorry, I could not respond. Please try again.';
                appendMessage(msg, 'bot', 'error');
            }
            sendBtn.disabled = false;
            input.focus();
        });
    }

    function appendMessage(text, role, source) {
        const messagesEl = document.getElementById('chat-messages');
        if (!messagesEl) return;
        const div = document.createElement('div');
        div.className = 'chat-msg ' + role;
        if (role === 'bot' && source && source !== 'faq') {
            div.innerHTML = escapeHtml(text) + '<div class="source-tag">AI</div>';
        } else {
            div.textContent = text;
        }
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function escapeHtml(s) {
        const div = document.createElement('div');
        div.textContent = s;
        return div.innerHTML;
    }

    function appendLoading() {
        const messagesEl = document.getElementById('chat-messages');
        if (!messagesEl) return null;
        const div = document.createElement('div');
        div.className = 'chat-loading';
        div.textContent = 'Thinking...';
        div.setAttribute('data-chat-loading', '1');
        messagesEl.appendChild(div);
        messagesEl.scrollTop = messagesEl.scrollHeight;
        return div;
    }

    function removeLoading(el) {
        if (el && el.parentNode) el.remove();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', renderWidget);
    } else {
        renderWidget();
    }
})();
