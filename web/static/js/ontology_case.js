// Case page (ontology_case.html, case_section_page.html).

// Progressive disclosure: expand/collapse clamped prose. Each .clamp-toggle
// button immediately follows the .text-clamp element it controls. Delegated,
// so the sections loaded on demand behave the same way.
document.addEventListener('click', function(e) {
    const btn = e.target.closest('.clamp-toggle');
    if (!btn) return;
    const clamped = btn.previousElementSibling;
    if (!clamped || !clamped.classList.contains('text-clamp')) return;
    const expanded = clamped.classList.toggle('expanded');
    btn.textContent = expanded ? 'Show less' : 'Show more';
});

// Toggle show more/less for individual lists
function toggleMore(sectionId, btn) {
    const hiddenEl = document.getElementById('hidden-' + sectionId);
    if (hiddenEl.style.display === 'none') {
        hiddenEl.style.display = 'block';
        btn.textContent = 'Show less';
    } else {
        hiddenEl.style.display = 'none';
        const count = hiddenEl.querySelectorAll('.entity-card').length;
        btn.textContent = 'Show ' + count + ' more';
    }
}

// Sections configured collapsed load their body on demand. The control is a
// plain link to the section page; with JavaScript the fragment replaces it in
// place, and on a failed request the link is followed.
document.addEventListener('click', function(e) {
    const link = e.target.closest('.deferred-load');
    if (!link) return;
    e.preventDefault();
    const container = link.closest('.deferred-body');
    link.classList.add('disabled');
    link.textContent = 'Loading...';
    fetch(link.dataset.fragment, { headers: { 'Accept': 'text/html' } })
        .then(function(response) {
            if (!response.ok) throw new Error(response.status);
            return response.text();
        })
        .then(function(html) {
            container.innerHTML = html;
            container.classList.remove('deferred-body');
        })
        .catch(function() {
            window.location.href = link.getAttribute('href');
        });
});

// Smooth scroll to in-page anchors with an offset
document.addEventListener('click', function(e) {
    const link = e.target.closest('a[href^="#"]');
    if (!link) return;
    const targetEl = document.getElementById(link.getAttribute('href').substring(1));
    if (!targetEl) return;
    e.preventDefault();
    const top = targetEl.getBoundingClientRect().top + window.pageYOffset - 20;
    window.scrollTo({ top: top, behavior: 'smooth' });
    history.replaceState(null, '', link.getAttribute('href'));
});

// Highlight the section of the sidebar that is in view
const navLinks = document.querySelectorAll('.case-nav .nav-link');
if (navLinks.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (!entry.isIntersecting) return;
            navLinks.forEach(function(link) {
                link.classList.toggle('active', link.getAttribute('href') === '#' + entry.target.id);
            });
        });
    }, { rootMargin: '-20% 0px -70% 0px' });
    document.querySelectorAll('.case-section').forEach(function(section) {
        observer.observe(section);
    });
}
