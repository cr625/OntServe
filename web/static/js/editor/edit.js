        // Global variables
        let aceEditor;
        let currentOntologyId = window.EDIT_BOOTSTRAP.ontologyId;
        let currentVersion = window.EDIT_BOOTSTRAP.currentVersion;
        let hasUnsavedChanges = false;

        // Initialize ACE Editor
        document.addEventListener('DOMContentLoaded', function () {
            initializeAceEditor();
            setupEventListeners();
            loadInitialContent();
        });

        function initializeAceEditor() {
            aceEditor = ace.edit("aceEditor");

            // Set theme and language mode (same as ProEthica)
            aceEditor.setTheme("ace/theme/monokai");
            aceEditor.session.setMode("ace/mode/turtle");

            // Enable language tools
            ace.require("ace/ext/language_tools");
            aceEditor.setOptions({
                enableBasicAutocompletion: true,
                enableSnippets: true,
                enableLiveAutocompletion: true,
                fontSize: 14,
                showPrintMargin: false,
                wrap: false
            });

            // Track changes
            aceEditor.session.on('change', function () {
                hasUnsavedChanges = true;
                updateSaveButtonState();
            });

            // Keyboard shortcuts
            aceEditor.commands.addCommand({
                name: 'save',
                bindKey: { win: 'Ctrl-S', mac: 'Command-S' },
                exec: function (editor) {
                    saveOntology();
                }
            });

            aceEditor.commands.addCommand({
                name: 'validate',
                bindKey: { win: 'Ctrl-Shift-V', mac: 'Command-Shift-V' },
                exec: function (editor) {
                    validateOntology();
                }
            });
        }

        function setupEventListeners() {
            document.getElementById('saveBtn').addEventListener('click', saveOntology);
            document.getElementById('validateBtn').addEventListener('click', validateOntology);
            document.getElementById('downloadBtn').addEventListener('click', downloadTTL);
            document.getElementById('confirmSaveBtn').addEventListener('click', confirmSave);

            // Warn before leaving with unsaved changes
            window.addEventListener('beforeunload', function (e) {
                if (hasUnsavedChanges) {
                    e.preventDefault();
                    e.returnValue = '';
                }
            });
        }

        function loadInitialContent() {
            // Content is already loaded in the template
            hasUnsavedChanges = false;
            updateSaveButtonState();
        }

        function loadVersion(version) {
            if (hasUnsavedChanges && !confirm('You have unsaved changes. Load this version anyway?')) {
                return;
            }

            // Update active version in UI
            document.querySelectorAll('.version-item').forEach(item => {
                item.classList.remove('active');
            });
            document.querySelector(`[data-version="${version}"]`).classList.add('active');

            // Load version content
            fetch(`/editor/ontology/${currentOntologyId}/version/${version}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        aceEditor.setValue(data.content, -1);
                        currentVersion = version;
                        hasUnsavedChanges = false;
                        updateSaveButtonState();
                    } else {
                        alert('Error loading version: ' + data.error);
                    }
                })
                .catch(error => {
                    console.error('Error loading version:', error);
                    alert('Error loading version: ' + error.message);
                });
        }

        function validateOntology() {
            const content = aceEditor.getValue();

            document.getElementById('validateBtn').disabled = true;
            document.getElementById('validateBtn').innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Validating...';

            fetch(`/editor/ontology/${currentOntologyId}/validate`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ content: content })
            })
                .then(response => response.json())
                .then(data => {
                    showValidationResults(data.validation);
                })
                .catch(error => {
                    console.error('Validation error:', error);
                    alert('Validation failed: ' + error.message);
                })
                .finally(() => {
                    document.getElementById('validateBtn').disabled = false;
                    document.getElementById('validateBtn').innerHTML = '<i class="fas fa-check-circle me-1"></i>Validate';
                });
        }

        function showValidationResults(validation) {
            const card = document.getElementById('validationCard');
            const results = document.getElementById('validationResults');

            let html = '';

            if (validation.valid) {
                html = '<div class="alert alert-success"><i class="fas fa-check-circle me-2"></i>Ontology is valid!</div>';
            } else {
                html = '<div class="alert alert-danger"><i class="fas fa-exclamation-triangle me-2"></i>Validation failed</div>';
            }

            if (validation.errors && validation.errors.length > 0) {
                html += '<h6 class="text-danger">Errors:</h6><ul class="list-unstyled">';
                validation.errors.forEach(error => {
                    html += `<li class="text-danger"><i class="fas fa-times me-1"></i>${error}</li>`;
                });
                html += '</ul>';
            }

            if (validation.warnings && validation.warnings.length > 0) {
                html += '<h6 class="text-warning">Warnings:</h6><ul class="list-unstyled">';
                validation.warnings.forEach(warning => {
                    html += `<li class="text-warning"><i class="fas fa-exclamation-triangle me-1"></i>${warning}</li>`;
                });
                html += '</ul>';
            }

            results.innerHTML = html;
            card.style.display = 'block';

            // Scroll to validation results
            card.scrollIntoView({ behavior: 'smooth' });
        }

        function hideValidation() {
            document.getElementById('validationCard').style.display = 'none';
        }

        function saveOntology() {
            const modal = new bootstrap.Modal(document.getElementById('saveVersionModal'));
            modal.show();
        }

        function confirmSave() {
            const content = aceEditor.getValue();
            const commitMessage = document.getElementById('commitMessage').value.trim();
            const extractEntities = document.getElementById('extractEntitiesCheck').checked;

            if (!commitMessage) {
                alert('Please enter a commit message');
                return;
            }

            document.getElementById('confirmSaveBtn').disabled = true;
            document.getElementById('confirmSaveBtn').innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Saving...';

            fetch(`/editor/ontology/${currentOntologyId}/save`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    content: content,
                    commit_message: commitMessage,
                    extract_entities: extractEntities
                })
            })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        hasUnsavedChanges = false;
                        updateSaveButtonState();

                        // Close modal and show success
                        bootstrap.Modal.getInstance(document.getElementById('saveVersionModal')).hide();

                        // Refresh page to show new version
                        setTimeout(() => {
                            location.reload();
                        }, 1000);

                        // Show success message
                        showAlert('success', 'Ontology saved successfully!');
                    } else {
                        alert('Save failed: ' + data.error);
                        if (data.validation) {
                            showValidationResults(data.validation);
                        }
                    }
                })
                .catch(error => {
                    console.error('Save error:', error);
                    alert('Save failed: ' + error.message);
                })
                .finally(() => {
                    document.getElementById('confirmSaveBtn').disabled = false;
                    document.getElementById('confirmSaveBtn').innerHTML = '<i class="fas fa-save me-1"></i>Save Version';
                });
        }

        function downloadTTL() {
            const content = aceEditor.getValue();
            const blob = new Blob([content], { type: 'text/turtle' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${currentOntologyId}.ttl`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }

        function extractEntities() {
            if (confirm('Force re-sync entities from TTL? (Entities auto-sync on startup)')) {
                fetch(`/editor/api/extract-entities/${currentOntologyId}`, { method: 'POST' })
                    .then(response => response.json())
                    .then(data => {
                        if (data.success) {
                            showAlert('success', `Re-synced ${data.total_entities} entities`);
                            // Update statistics
                            updateStats(data.entity_counts);
                        } else {
                            alert('Error extracting entities: ' + data.error);
                        }
                    })
                    .catch(error => {
                        alert('Error extracting entities: ' + error.message);
                    });
            }
        }

        function formatTTL() {
            // Simple TTL formatting - could be enhanced
            const content = aceEditor.getValue();
            const formatted = content.replace(/\s+/g, ' ').replace(/\s*\.\s*/g, ' .\n').replace(/\s*;\s*/g, ' ;\n    ');
            aceEditor.setValue(formatted, -1);
        }

        function findReplace() {
            aceEditor.execCommand('find');
        }

        function toggleWordWrap() {
            const session = aceEditor.getSession();
            session.setUseWrapMode(!session.getUseWrapMode());
        }

        function toggleTheme() {
            const currentTheme = aceEditor.getTheme();
            const newTheme = currentTheme.includes('monokai') ? 'ace/theme/github' : 'ace/theme/monokai';
            aceEditor.setTheme(newTheme);
        }

        function showKeyboardShortcuts() {
            const modal = new bootstrap.Modal(document.getElementById('shortcutsModal'));
            modal.show();
        }

        function updateSaveButtonState() {
            const saveBtn = document.getElementById('saveBtn');
            if (hasUnsavedChanges) {
                saveBtn.classList.remove('btn-success');
                saveBtn.classList.add('btn-warning');
                saveBtn.innerHTML = '<i class="fas fa-save me-1"></i>Save*';
            } else {
                saveBtn.classList.remove('btn-warning');
                saveBtn.classList.add('btn-success');
                saveBtn.innerHTML = '<i class="fas fa-save me-1"></i>Save';
            }
        }

        function updateStats(entityCounts) {
            if (entityCounts) {
                document.getElementById('classCount').textContent = entityCounts.class || 0;
                document.getElementById('propertyCount').textContent = entityCounts.property || 0;
            }
        }

        function showAlert(type, message) {
            const alert = document.createElement('div');
            alert.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
            alert.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
            alert.innerHTML = `
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            `;
            document.body.appendChild(alert);

            setTimeout(() => {
                if (alert.parentNode) {
                    alert.parentNode.removeChild(alert);
                }
            }, 5000);
        }
    
