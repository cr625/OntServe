// Public OWL-DL reasoning panel (macros/reasoning_panel.html).
// Calls the read-only Pellet endpoint with explain=true and scope=local:
// reasoning runs over the full merged graph, but only entailments whose
// subject is declared in THIS ontology's content are reported, each with
// its justification (the asserted axiom set Pellet reports as supporting
// it). Stack-level entailments never recur here; see
// .claude/plans/contextual-reasoning-panel.md for the attribution rule.
(function () {
    'use strict';

    const btn = document.getElementById('reasoningRunBtn');
    const body = document.getElementById('reasoningPanelBody');
    if (!btn || !body) return;

    const info = document.getElementById('reasoningInfoIcon');
    if (info && window.bootstrap && bootstrap.Popover) {
        new bootstrap.Popover(info);
    }

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
            <div class="border-start border-3 border-success ps-3 mt-1" style="min-width: 0;">
                ${groups.length > 1 ? `<div class="text-muted small">justification ${i + 1}</div>` : ''}
                <code class="d-block small" style="white-space: pre-wrap; overflow-wrap: anywhere;">${lines.map(esc).join('\n')}</code>
            </div>`).join('');
    }

    // The constraints present for this run (reasoning_tools.reasoning_checks),
    // rendered as data: which disjointness axioms the merged graph carries,
    // which characteristic-bearing properties the ontology asserts pairs for,
    // and how many domain- or range-constrained properties it uses.
    function checksHtml(c) {
        if (!c) return '';
        const axioms = c.disjointness_axioms || [];
        const chars = c.characteristic_properties || [];
        const drCount = c.domain_range_property_count || 0;
        const drUses = (c.domain_range_properties || []).reduce((n, p) => n + (p.uses || 0), 0);
        const plural = (n, one, many) => (n === 1 ? one : many);
        const axiomItems = axioms.map(d => `
            <li><code>${esc(d.kind)}</code> ${(d.members || []).map(m => esc(local(m))).join(', ')}</li>`).join('');
        const charItems = chars.map(p => `
            <li><code>${esc(local(p.property))}</code> (${(p.characteristics || []).map(esc).join(', ')}):
                ${p.pairs_examined} ${plural(p.pairs_examined, 'pair', 'pairs')} examined</li>`).join('');
        const drItems = (c.domain_range_properties || []).map(p => `
            <li><code>${esc(local(p.property))}</code>${p.domain && p.domain.length ? ` domain ${p.domain.map(d => esc(local(d))).join(' | ')}` : ''}${p.range && p.range.length ? ` range ${p.range.map(r => esc(local(r))).join(' | ')}` : ''}: ${p.uses} ${plural(p.uses, 'use', 'uses')}</li>`).join('');
        return `
            <details class="small mb-3">
                <summary class="text-muted" style="cursor:pointer;">
                    Checks applied: ${axioms.length} disjointness ${plural(axioms.length, 'axiom', 'axioms')},
                    ${c.pairs_examined || 0} property ${plural(c.pairs_examined || 0, 'pair', 'pairs')} under declared characteristics,
                    ${drCount} domain- or range-constrained ${plural(drCount, 'property', 'properties')} used
                </summary>
                ${axiomItems ? `<div class="mt-2 fw-semibold">Disjointness axioms present in the merged graph</div><ul class="mb-2" style="overflow-wrap: anywhere;">${axiomItems}</ul>` : '<div class="mt-2 text-muted">No disjointness axioms in the merged graph.</div>'}
                ${charItems ? `<div class="fw-semibold">Property characteristics checked</div><ul class="mb-2" style="overflow-wrap: anywhere;">${charItems}</ul>` : '<div class="text-muted">No pairs asserted for a characteristic-bearing property.</div>'}
                ${drItems ? `<div class="fw-semibold">Domain and range constraints (${drUses} ${plural(drUses, 'use', 'uses')})</div><ul class="mb-0" style="overflow-wrap: anywhere;">${drItems}</ul>` : '<div class="text-muted">No domain- or range-constrained property used.</div>'}
            </details>`;
    }

    function render(data) {
        let html = '';
        if (data.consistent) {
            html += `
                <div class="alert alert-success py-2 mb-3">
                    <i class="bi bi-check-circle me-1"></i>
                    <strong>Consistent.</strong>
                    ${(data.nothing_entities || []).length} disjointness violation(s),
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

        html += checksHtml(data.checks);

        const explained = data.explanations || [];
        if (explained.length) {
            html += '<h6 class="mb-2">Derived statements and why they hold</h6>';
            explained.forEach(e => {
                html += `
                    <div class="mb-3" style="min-width: 0;">
                        <div style="overflow-wrap: anywhere;">
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
                No statements about this ontology's entities are derivable beyond
                what is asserted.</p>`;
        }

        // Entailments past the justification cap: list without justification.
        const explainedKeys = new Set(explained.map(e => `${e.subject}|${e.object}`));
        const rest = []
            .concat((data.inferred_types || []).map(t => ({ s: t.individual, o: t.type, verb: 'type' })))
            .concat((data.inferred_subclasses || []).map(t => ({ s: t.child, o: t.parent, verb: 'subClassOf' })))
            .filter(t => !explainedKeys.has(`${t.s}|${t.o}`));
        if (rest.length) {
            html += `<h6 class="mt-3 mb-1">Further entailments</h6>
                <ul class="small mb-0" style="overflow-wrap: anywhere;">${rest.map(t =>
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
            body: JSON.stringify({ reasoner_type: 'pellet', explain: true, scope: 'local' })
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
