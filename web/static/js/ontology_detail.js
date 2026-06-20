    function viewVersion(versionId) {
        // For now, show an alert with version info
        // In the future, this could open a modal or redirect to a version view
        fetch(`/api/versions/${versionId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert(`Version ${data.version.version_number}\n\n${data.version.change_summary}\n\nCreated: ${data.version.created_at}\nBy: ${data.version.created_by}`);
                }
            })
            .catch(error => console.error('Error:', error));
    }

    function makeVersionCurrent(versionId) {
        if (!confirm('Are you sure you want to make this version the current version? This will replace the current ontology content.')) {
            return;
        }

        fetch(`/api/versions/${versionId}/make-current`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    let message = 'Version successfully made current!';
                    if (data.entities_updated) {
                        message += '\n\nEntities have been re-extracted from the new version content. The visualization will now show updated relationships.';
                    }
                    alert(message);
                    location.reload();
                } else {
                    alert('Failed to make version current: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Failed to make version current');
            });
    }

    function showReasoningDetails(versionId) {
        // Fetch version details and show reasoning information
        fetch(`/api/versions/${versionId}`)
            .then(response => response.json())
            .then(data => {
                if (data.success && data.version.meta_data && data.version.meta_data.reasoning) {
                    const reasoning = data.version.meta_data.reasoning;
                    const inferredRels = reasoning.inferred_relationships || [];

                    let message = `Reasoning Details for Version ${data.version.version_number}\n`;
                    message += `${'='.repeat(50)}\n\n`;
                    message += `Reasoner: ${reasoning.reasoner_type}\n`;
                    message += `Classes: ${reasoning.classes_before} → ${reasoning.classes_after} (+${reasoning.classes_after - reasoning.classes_before})\n`;
                    message += `Properties: ${reasoning.properties_before} → ${reasoning.properties_after} (+${reasoning.properties_after - reasoning.properties_before})\n`;
                    message += `Hierarchical Relationships: ${reasoning.hierarchical_relationships}\n`;

                    if (inferredRels.length > 0) {
                        message += `\nSample Inferred Relationships:\n`;
                        inferredRels.slice(0, 5).forEach(rel => {
                            message += `  • ${rel.child} ${rel.type} ${rel.parent}\n`;
                        });
                        if (inferredRels.length > 5) {
                            message += `  ... and ${inferredRels.length - 5} more\n`;
                        }
                    }

                    alert(message);
                }
            })
            .catch(error => console.error('Error:', error));
    }

    function filterRelationships() {
        const searchTerm = document.getElementById('relationshipSearch').value.toLowerCase();
        const typeFilter = document.getElementById('relationshipTypeFilter').value;
        const rows = document.querySelectorAll('#relationshipsTable .relationship-row');
        let visibleCount = 0;

        rows.forEach(row => {
            const child = row.getAttribute('data-child').toLowerCase();
            const parent = row.getAttribute('data-parent').toLowerCase();
            const type = row.getAttribute('data-type');

            const matchesSearch = child.includes(searchTerm) || parent.includes(searchTerm);
            const matchesType = !typeFilter || type === typeFilter;

            if (matchesSearch && matchesType) {
                row.style.display = '';
                visibleCount++;
            } else {
                row.style.display = 'none';
            }
        });

        document.getElementById('relationshipCount').textContent = `Showing ${visibleCount} relationships`;
    }

    function cleanURI(uri) {
        // Common namespace mappings for ProEthica ontologies
        const namespaces = {
            'http://proethica.org/ontology/intermediate#': 'proethica:',
            'http://proethica.org/ontology/engineering-ethics#': 'ethics:',
            'http://www.w3.org/2002/07/owl#': 'owl:',
            'http://www.w3.org/1999/02/22-rdf-syntax-ns#': 'rdf:',
            'http://www.w3.org/2000/01/rdf-schema#': 'rdfs:',
            'http://purl.obolibrary.org/obo/': 'obo:'
        };

        // First try to match known namespaces
        for (const [namespace, prefix] of Object.entries(namespaces)) {
            if (uri.startsWith(namespace)) {
                return prefix + uri.substring(namespace.length);
            }
        }

        // Extract the fragment after # or the last part after /
        const fragment = uri.split('#').pop() || uri.split('/').pop();
        return fragment || uri;
    }

    function updateURIDisplays() {
        // Clean up class names in the relationships table
        document.querySelectorAll('.clean-uri').forEach(element => {
            const fullUri = element.getAttribute('data-full-uri');
            const cleanName = cleanURI(fullUri);
            element.textContent = cleanName;
        });

        // Update full URIs to show cleaned versions
        document.querySelectorAll('.full-uri').forEach(element => {
            const originalUri = element.textContent;
            const cleanName = cleanURI(originalUri);
            // Show both the clean name and original URI
            element.innerHTML = `<strong>${cleanName}</strong><br><span style="font-size: 0.8em;">${originalUri}</span>`;
        });

        // Update relationship descriptions
        document.querySelectorAll('.relationship-description').forEach(element => {
            const child = element.getAttribute('data-child');
            const parent = element.getAttribute('data-parent');
            const type = element.getAttribute('data-type');

            const cleanChild = cleanURI(child);
            const cleanParent = cleanURI(parent);

            if (type === 'subClassOf') {
                element.textContent = `"${cleanChild}" is a subclass of "${cleanParent}"`;
            } else {
                element.textContent = `Inferred ${type} relationship: ${cleanChild} → ${cleanParent}`;
            }
        });
    }

    // Delete ontology functionality
    function deleteOntology() {
        const ontologyName = window.ONTOLOGY_DETAIL.ontologyName;

        fetch(`/ontology/${ontologyName}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            }
        })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    alert('Ontology deleted successfully!');
                    window.location.href = '/';
                } else {
                    alert('Failed to delete ontology: ' + (data.error || 'Unknown error'));
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('Failed to delete ontology');
            });
    }

    function getCsrfToken() {
        // Get CSRF token from meta tag if available
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // ===== Version Tagging =====

    // Check divergence when the tag modal opens
    const tagModal = document.getElementById('tagVersionModal');
    if (tagModal) {
        tagModal.addEventListener('show.bs.modal', function () {
            const warningEl = document.getElementById('tagDivergenceWarning');
            warningEl.className = 'd-none';
            warningEl.innerHTML = '';

            fetch(`/api/ontology/${window.ONTOLOGY_DETAIL.ontologyName}/version-history?tagged_only=true`)
            .then(r => r.json())
            .then(data => {
                if (!data.success) return;
                // No previous tags -- first tag, no warning needed
                if (!data.versions || data.versions.length === 0) return;

                const pct = data.current_divergence_pct;
                if (pct === null || pct === undefined) return;

                if (pct === 0) {
                    warningEl.className = 'alert alert-warning mb-3';
                    warningEl.innerHTML = '<i class="bi bi-exclamation-triangle"></i> <strong>No changes detected</strong> since the last tagged release. The ontology content is identical. Are you sure you want to create a new tag?';
                } else if (pct < 5) {
                    warningEl.className = 'alert alert-info mb-3';
                    warningEl.innerHTML = '<i class="bi bi-info-circle"></i> Only <strong>' + pct + '%</strong> of entities have changed since the last tag. Consider waiting for more changes before tagging.';
                }
            })
            .catch(() => {});  // Silently fail -- non-blocking check
        });
    }

    function tagVersion() {
        const tag = document.getElementById('versionTagInput').value.trim();
        const summary = document.getElementById('changeSummaryInput').value.trim();
        const errorEl = document.getElementById('tagVersionError');
        const btn = document.getElementById('confirmTagBtn');

        errorEl.classList.add('d-none');

        if (!tag) {
            errorEl.textContent = 'Version tag is required.';
            errorEl.classList.remove('d-none');
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Tagging...';

        fetch(`/api/ontology/${window.ONTOLOGY_DETAIL.ontologyName}/tag-version`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({version_tag: tag, change_summary: summary})
        })
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                const modal = bootstrap.Modal.getInstance(document.getElementById('tagVersionModal'));
                modal.hide();
                loadTaggedReleases();
                location.reload();
            } else {
                errorEl.textContent = data.error || 'Failed to tag version.';
                errorEl.classList.remove('d-none');
                btn.disabled = false;
                btn.innerHTML = '<i class="bi bi-tag"></i> Create Tag';
            }
        })
        .catch(err => {
            errorEl.textContent = 'Network error: ' + err.message;
            errorEl.classList.remove('d-none');
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-tag"></i> Create Tag';
        });
    }

    function loadTaggedReleases() {
        const container = document.getElementById('taggedReleasesTable');
        const divergenceEl = document.getElementById('currentDivergence');

        fetch(`/api/ontology/${window.ONTOLOGY_DETAIL.ontologyName}/version-history?tagged_only=true`)
        .then(r => r.json())
        .then(data => {
            if (!data.success) {
                container.innerHTML = '<div class="text-center text-muted py-3"><small>Failed to load tagged releases.</small></div>';
                return;
            }

            // Show current divergence from latest tag
            if (data.current_divergence_pct !== null && data.current_divergence_pct !== undefined) {
                const pct = data.current_divergence_pct;
                const color = pct === 0 ? 'success' : pct < 10 ? 'info' : pct < 30 ? 'warning' : 'danger';
                divergenceEl.innerHTML = `<span class="badge bg-${color}">Divergence since last tag: ${pct}%</span>`;
            } else {
                divergenceEl.innerHTML = '';
            }

            if (!data.versions || data.versions.length === 0) {
                container.innerHTML = '<div class="text-center text-muted py-3"><small>No tagged releases yet. Use "Tag Version" to create one.</small></div>';
                return;
            }

            let html = '<table class="table table-sm mb-0"><thead><tr>';
            html += '<th>Tag</th><th>Version</th><th>Divergence</th><th>Created</th><th>By</th><th>Summary</th>';
            html += '</tr></thead><tbody>';

            data.versions.forEach(v => {
                const divBadge = v.divergence_pct !== null && v.divergence_pct !== undefined
                    ? `<span class="badge bg-${v.divergence_pct === 0 ? 'success' : v.divergence_pct < 10 ? 'info' : v.divergence_pct < 30 ? 'warning' : 'danger'}">${v.divergence_pct}%</span>`
                    : '<span class="text-muted">--</span>';

                const currentBadge = v.is_current ? ' <span class="badge bg-success">Current</span>' : '';
                const date = v.created_at ? new Date(v.created_at).toLocaleDateString() : '-';
                const summary = v.change_summary ? (v.change_summary.length > 80 ? v.change_summary.substring(0, 80) + '...' : v.change_summary) : '-';

                html += `<tr>`;
                html += `<td><code>${v.version_tag}</code>${currentBadge}</td>`;
                html += `<td>v${v.version_number}</td>`;
                html += `<td>${divBadge}</td>`;
                html += `<td><small>${date}</small></td>`;
                html += `<td><small>${v.created_by || '-'}</small></td>`;
                html += `<td><small>${summary}</small></td>`;
                html += `</tr>`;
            });

            html += '</tbody></table>';
            container.innerHTML = html;
        })
        .catch(err => {
            container.innerHTML = '<div class="text-center text-muted py-3"><small>Error loading tagged releases.</small></div>';
        });
    }

    // Run URI cleanup when the page loads
    document.addEventListener('DOMContentLoaded', function () {
        updateURIDisplays();
        loadTaggedReleases();

        // Enable delete confirmation based on input
        const deleteInput = document.getElementById('deleteConfirmInput');
        const deleteBtn = document.getElementById('confirmDeleteBtn');
        const ontologyName = window.ONTOLOGY_DETAIL.ontologyName;

        if (deleteInput && deleteBtn) {
            deleteInput.addEventListener('input', function () {
                deleteBtn.disabled = this.value !== ontologyName;
            });
        }
    });
