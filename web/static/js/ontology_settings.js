    function resetForm() {
        document.getElementById('ontologySettingsForm').reset();
    }

    document.getElementById('ontologySettingsForm').addEventListener('submit', function (e) {
        e.preventDefault();

        const formData = new FormData(this);
        const data = {
            name: formData.get('name'),
            base_uri: formData.get('base_uri'),
            description: formData.get('description'),
            ontology_type: formData.get('ontology_type'),
            source_system: formData.get('source_system'),
            is_editable: formData.has('is_editable'),
            is_base: formData.has('is_base'),
            is_stub: formData.has('is_stub')
        };

        // Show loading state
        const submitBtn = this.querySelector('button[type="submit"]');
        const originalText = submitBtn.innerHTML;
        submitBtn.innerHTML = '<i class="bi bi-hourglass-split"></i> Saving...';
        submitBtn.disabled = true;

        fetch('/api/ontology/' + window.ONTOLOGY_SETTINGS.ontologyName + '/metadata', {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    // Show success message
                    const alertDiv = document.createElement('div');
                    alertDiv.className = 'alert alert-success alert-dismissible fade show mt-3';
                    alertDiv.innerHTML = `
                <i class="bi bi-check-circle"></i> Settings saved successfully!
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
                    this.insertBefore(alertDiv, this.firstChild);

                    // If name changed, redirect to new URL
                    if (result.name_changed) {
                        setTimeout(() => {
                            window.location.href = `/ontology/${data.name}/settings`;
                        }, 2000);
                    }
                } else {
                    throw new Error(result.error || 'Unknown error');
                }
            })
            .catch(error => {
                // Show error message
                const alertDiv = document.createElement('div');
                alertDiv.className = 'alert alert-danger alert-dismissible fade show mt-3';
                alertDiv.innerHTML = `
            <i class="bi bi-exclamation-circle"></i> Error: ${error.message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        `;
                this.insertBefore(alertDiv, this.firstChild);
            })
            .finally(() => {
                // Reset button state
                submitBtn.innerHTML = originalText;
                submitBtn.disabled = false;
            });
    });

    // Delete confirmation
    const deleteInput = document.getElementById('deleteConfirmInput');
    const deleteBtn = document.getElementById('confirmDeleteBtn');

    if (deleteInput && deleteBtn) {
        deleteInput.addEventListener('input', function () {
            deleteBtn.disabled = this.value !== window.ONTOLOGY_SETTINGS.ontologyName;
        });
    }

    function confirmDelete() {
        fetch('/ontology/' + window.ONTOLOGY_SETTINGS.ontologyName, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    window.location.href = '/';
                } else {
                    alert('Delete failed: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                alert('Delete failed: ' + error.message);
            });
    }
