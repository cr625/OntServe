(function () {
    const container = document.getElementById('chat-container');
    const form = document.getElementById('query-form');
    const input = document.getElementById('query-input');
    const thinking = document.getElementById('thinking-indicator');
    const placeholder = document.getElementById('placeholder');
    const btnClear = document.getElementById('btn-clear');

    function scrollBottom() {
        container.scrollTop = container.scrollHeight;
    }

    function addMessage(role, content) {
        if (placeholder) placeholder.remove();
        const div = document.createElement('div');
        div.className = 'msg msg-' + role;
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble';
        if (role === 'assistant') {
            bubble.innerHTML = marked.parse(content);
        } else {
            bubble.textContent = content;
        }
        div.appendChild(bubble);
        container.insertBefore(div, thinking);
        scrollBottom();
    }

    form.addEventListener('submit', async function (e) {
        e.preventDefault();
        const msg = input.value.trim();
        if (!msg) return;

        addMessage('user', msg);
        input.value = '';
        input.disabled = true;
        thinking.style.display = 'block';
        scrollBottom();

        try {
            const resp = await fetch(window.WOLFRAM_QUERY.queryUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: msg}),
            });
            const data = await resp.json();
            if (data.success) {
                addMessage('assistant', data.content);
            } else {
                addMessage('assistant', '**Error:** ' + (data.error || 'Unknown error'));
            }
        } catch (err) {
            addMessage('assistant', '**Error:** ' + err.message);
        } finally {
            thinking.style.display = 'none';
            input.disabled = false;
            input.focus();
        }
    });

    btnClear.addEventListener('click', async function () {
        await fetch(window.WOLFRAM_QUERY.clearHistoryUrl, {method: 'POST'});
        // Remove all messages except the thinking indicator
        Array.from(container.querySelectorAll('.msg:not(#thinking-indicator)'))
            .forEach(el => el.remove());
        // Re-add placeholder
        const ph = document.createElement('div');
        ph.id = 'placeholder';
        ph.className = 'text-muted text-center mt-5';
        ph.innerHTML = '<p>Query Wolfram for computations, data lookups, or knowledge questions.</p>'
            + '<p class="small">Responses combine an LLM with Wolfram Language computation.</p>';
        container.insertBefore(ph, thinking);
    });

    scrollBottom();
    input.focus();
})();
