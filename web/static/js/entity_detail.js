    function wolframLookup() {
        const query = document.getElementById('wolframQuery').value.trim();
        const context = document.getElementById('wolframContext').value.trim();
        const btn = document.getElementById('wolframBtn');
        const responseEl = document.getElementById('wolframResponse');
        const errorEl = document.getElementById('wolframError');

        if (!query) return;

        const message = context ? 'In the context of ' + context + ': ' + query : query;

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Looking up...';
        responseEl.classList.add('d-none');
        errorEl.classList.add('d-none');

        fetch(window.ENTITY_DETAIL.wolframQueryUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({message: message})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                responseEl.innerHTML = (typeof marked !== 'undefined' && marked.parse)
                    ? marked.parse(data.content)
                    : data.content;
                responseEl.classList.remove('d-none');
            } else {
                errorEl.textContent = data.error || 'Lookup failed.';
                errorEl.classList.remove('d-none');
            }
        })
        .catch(err => {
            errorEl.textContent = 'Network error: ' + err.message;
            errorEl.classList.remove('d-none');
        })
        .finally(() => {
            btn.disabled = false;
            btn.innerHTML = 'Look up';
        });
    }

    function toggleEditMode() {
        const display = document.getElementById('displayMode');
        const edit = document.getElementById('editMode');
        const btn = document.getElementById('editToggleBtn');
        if (!edit) return;

        const isEditing = !edit.classList.contains('d-none');
        if (isEditing) {
            edit.classList.add('d-none');
            display.classList.remove('d-none');
            btn.innerHTML = '<i class="bi bi-pencil"></i> Edit';
            btn.classList.remove('btn-secondary');
            btn.classList.add('btn-outline-warning');
        } else {
            edit.classList.remove('d-none');
            display.classList.add('d-none');
            btn.innerHTML = '<i class="bi bi-x-lg"></i> Cancel';
            btn.classList.remove('btn-outline-warning');
            btn.classList.add('btn-secondary');
        }
    }

    function saveEntity() {
        const label = document.getElementById('editLabel').value.trim();
        const comment = document.getElementById('editComment').value.trim();
        const errorEl = document.getElementById('editError');
        const successEl = document.getElementById('editSuccess');

        errorEl.classList.add('d-none');
        successEl.classList.add('d-none');

        fetch(window.ENTITY_DETAIL.entityApiUrl, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({label: label, comment: comment})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                successEl.textContent = 'Entity updated. Content hash: ' + data.content_hash.substring(0, 12) + '...';
                successEl.classList.remove('d-none');
                setTimeout(() => location.reload(), 1200);
            } else {
                errorEl.textContent = data.error || 'Update failed.';
                errorEl.classList.remove('d-none');
            }
        })
        .catch(err => {
            errorEl.textContent = 'Network error: ' + err.message;
            errorEl.classList.remove('d-none');
        });
    }

    // main.js (the global tooltip initializer) is not loaded on the entity page,
    // so the entity page initializes Bootstrap tooltips for its info icons here.
    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (el) {
            new bootstrap.Tooltip(el);
        });
    });
