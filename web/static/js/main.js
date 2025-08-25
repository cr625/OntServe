/* OntServe Main JavaScript */

// Global utilities
window.OntServe = {
    // Show notification function
    showNotification: function (message, type = 'info') {
        // Create simple notification
        const notification = document.createElement('div');
        notification.className = `alert alert-${type} position-fixed`;
        notification.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
        notification.innerHTML = `
            <strong>${type === 'success' ? '✅' : type === 'error' ? '❌' : 'ℹ️'}</strong> ${message}
            <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
        `;

        document.body.appendChild(notification);

        // Auto-remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    },

    // Safe delete function for ontologies
    safeDelete: function (ontologyName, confirmText) {
        const userInput = prompt(`To confirm deletion, please type: ${confirmText}`);
        if (userInput === confirmText) {
            return true;
        } else {
            alert('Deletion cancelled - confirmation text did not match.');
            return false;
        }
    },

    // Loading state management
    setLoading: function (element, loading) {
        if (loading) {
            element.classList.add('loading');
            element.disabled = true;
        } else {
            element.classList.remove('loading');
            element.disabled = false;
        }
    }
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function () {
    // Add any initialization code here
    console.log('OntServe interface initialized');

    // Fix Bootstrap tooltips if present
    if (typeof bootstrap !== 'undefined') {
        const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
        tooltipTriggerList.map(function (tooltipTriggerEl) {
            return new bootstrap.Tooltip(tooltipTriggerEl);
        });
    }
});
