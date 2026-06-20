// Progressive disclosure: expand/collapse clamped prose. Each .clamp-toggle
// button immediately follows the .text-clamp element it controls.
document.querySelectorAll('.clamp-toggle').forEach(btn => {
    const clamped = btn.previousElementSibling;
    if (!clamped || !clamped.classList.contains('text-clamp')) return;
    btn.addEventListener('click', function() {
        const expanded = clamped.classList.toggle('expanded');
        btn.textContent = expanded ? 'Show less' : 'Show more';
    });
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

// Smooth scroll to section with offset for sticky nav
document.querySelectorAll('a[href^="#"]').forEach(link => {
    link.addEventListener('click', function(e) {
        const targetId = this.getAttribute('href').substring(1);
        const targetEl = document.getElementById(targetId);
        if (targetEl) {
            e.preventDefault();
            const offset = 20;
            const targetPosition = targetEl.getBoundingClientRect().top + window.pageYOffset - offset;
            window.scrollTo({ top: targetPosition, behavior: 'smooth' });
        }
    });
});

// Highlight active section in nav on scroll
const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const id = entry.target.id;
            document.querySelectorAll('.section-nav .nav-link').forEach(link => {
                link.classList.remove('active');
                if (link.getAttribute('href') === '#' + id) {
                    link.classList.add('active');
                }
            });
        }
    });
}, { rootMargin: '-20% 0px -70% 0px' });

document.querySelectorAll('.case-section').forEach(section => {
    observer.observe(section);
});
