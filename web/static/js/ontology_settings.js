// Ontology settings page: save the metadata form through the JSON API and
// handle the delete confirmation. The form's data-ontology-name attribute
// carries the ontology name; fields are collected generically from the form,
// so a new input only needs a `name` attribute here and handling in the API.
(function () {
    const form = document.getElementById('ontologySettingsForm');
    if (!form) return;
    const ontologyName = form.dataset.ontologyName;

    function showAlert(kind, iconClass, message) {
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-' + kind + ' alert-dismissible fade show mt-3';
        alertDiv.innerHTML = '<i class="bi ' + iconClass + '"></i> ' + message +
            '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
        form.insertBefore(alertDiv, form.firstChild);
    }

    form.addEventListener('submit', function (e) {
        e.preventDefault();

        // Every named field as submitted; checkboxes become booleans (unchecked
        // boxes are absent from FormData, so set them explicitly).
        const data = Object.fromEntries(new FormData(form));
        form.querySelectorAll('input[type=checkbox][name]').forEach(function (cb) {
            data[cb.name] = cb.checked;
        });

        const submitBtn = form.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
        submitBtn.disabled = true;

        fetch('/api/ontology/' + encodeURIComponent(ontologyName) + '/metadata', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        })
            .then(function (response) { return response.json(); })
            .then(function (result) {
                if (!result.success) {
                    throw new Error(result.error || 'Unknown error');
                }
                showAlert('success', 'bi-check-circle', 'Settings saved successfully.');
                if (result.name_changed) {
                    setTimeout(function () {
                        window.location.href = '/ontology/' + encodeURIComponent(data.name) + '/settings';
                    }, 2000);
                }
            })
            .catch(function (error) {
                showAlert('danger', 'bi-exclamation-circle', 'Error: ' + error.message);
            })
            .finally(function () {
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            });
    });

    // Delete confirmation: the button unlocks when the typed name matches.
    const deleteInput = document.getElementById('deleteConfirmInput');
    const deleteBtn = document.getElementById('confirmDeleteBtn');
    if (deleteInput && deleteBtn) {
        deleteInput.addEventListener('input', function () {
            deleteBtn.disabled = this.value !== ontologyName;
        });
        deleteBtn.addEventListener('click', function () {
            fetch('/ontology/' + encodeURIComponent(ontologyName), {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' }
            })
                .then(function (response) { return response.json(); })
                .then(function (result) {
                    if (result.success) {
                        window.location.href = '/';
                    } else {
                        alert('Delete failed: ' + (result.error || 'Unknown error'));
                    }
                })
                .catch(function (error) {
                    alert('Delete failed: ' + error.message);
                });
        });
    }
})();
