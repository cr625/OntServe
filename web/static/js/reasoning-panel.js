// Public OWL-DL reasoning panel (macros/reasoning_panel.html).
// Calls the read-only Pellet endpoint with explain=true and renders the
// consistency verdict, the entailed statements, and each statement's
// justification (the asserted axiom set Pellet reports as supporting it).
(function () {
    'use strict';

    const btn = document.getElementById('reasoningRunBtn');
    const body = document.getElementById('reasoningPanelBody');
    if (!btn || !body) return;

    const esc = s => String(s)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    const local = iri => String(iri).split('#').pop().split('/').pop();

    function statementLabel(e) {
        if (e.axiom) return e.axiom;
        const verb = e.kind === 'instance' ? 'type' : 'subClassOf';
        return `${local(e.subject)} ${verb} ${local(e.object)}`;
    }

    function justificationHtml(groups) {
        if (!groups || !groups.length) return '';
        return groups.map((lines, i) => `
            <div class="border-start border-3 border-success ps-3 mt-1">
                ${groups.length > 1 ? `<div class="text-muted small">justification ${i + 1}</div>` : ''}
                <code class="d-block small" style="white-space: pre-wrap;">${lines.map(esc).join('\n')}</code>
            </div>`).join('');
    }

    function render(data) {
        let html = '';
        if (data.consistent) {
            html += `
                <div class="alert alert-success py-2 mb-3">
                    <i class="bi bi-check-circle me-1"></i>
                    <strong>Consistent.</strong>
                    ${data.inferred_type_count || 0} inferred type assertion(s),
                    ${data.inferred_subclass_count || 0} inferred subclass relation(s)
                    over the merged graph.
                </div>`;
        } else {
            html += `
                <div class="alert alert-danger py-2 mb-3">
                    <i class="bi bi-x-circle me-1"></i>
                    <strong>Inconsistent.</strong>
                    ${data.error_explanation ? esc(data.error_explanation) : ''}
                </div>`;
            const inc = data.inconsistency_explanation;
            if (inc && inc.explanations && inc.explanations.length) {
                html += `<h6 class="mt-2">Clashing axiom set</h6>${justificationHtml(inc.explanations)}`;
            }
        }

        const explained = data.explanations || [];
        if (explained.length) {
            html += '<h6 class="mb-2">Derived statements and why they hold</h6>';
            explained.forEach(e => {
                html += `
                    <div class="mb-3">
                        <div>
                            <span class="badge bg-success me-1">derived</span>
                            <strong><code>${esc(statementLabel(e))}</code></strong>
                        </div>
                        ${e.error
                            ? `<div class="text-muted small ps-3">justification unavailable (${esc(e.error)})</div>`
                            : justificationHtml(e.explanations)}
                    </div>`;
            });
        } else if (data.consistent) {
            html += `<p class="text-muted small mb-0">
                No non-trivial entailments beyond the asserted statements.</p>`;
        }

        // Entailments past the justification cap: list without justification.
        const explainedKeys = new Set(explained.map(e => `${e.subject}|${e.object}`));
        const rest = []
            .concat((data.inferred_types || []).map(t => ({ s: t.individual, o: t.type, verb: 'type' })))
            .concat((data.inferred_subclasses || []).map(t => ({ s: t.child, o: t.parent, verb: 'subClassOf' })))
            .filter(t => !explainedKeys.has(`${t.s}|${t.o}`));
        if (rest.length) {
            html += `<h6 class="mt-3 mb-1">Further entailments</h6>
                <ul class="small mb-0">${rest.map(t =>
                    `<li><code>${esc(local(t.s))} ${t.verb} ${esc(local(t.o))}</code></li>`).join('')}</ul>`;
        }

        body.innerHTML = html;
    }

    btn.addEventListener('click', function () {
        const original = btn.innerHTML;
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Reasoning…';
        body.innerHTML = `<p class="text-muted small mb-0">
            Running Pellet over the merged graph and computing justifications…
            This takes a few seconds.</p>`;

        fetch(`/editor/api/simple/reasoning/${encodeURIComponent(btn.dataset.ontology)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reasoner_type: 'pellet', explain: true })
        })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    render(data);
                } else {
                    body.innerHTML = `<div class="alert alert-warning py-2 mb-0">
                        Reasoning failed: ${esc(data.error || data.message || 'unknown error')}</div>`;
                }
            })
            .catch(err => {
                body.innerHTML = `<div class="alert alert-warning py-2 mb-0">
                    Request failed: ${esc(err)}</div>`;
            })
            .finally(() => {
                btn.disabled = false;
                btn.innerHTML = original;
            });
    });
})();
