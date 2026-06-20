    function toggleSourceInput() {
        const sourceType = document.getElementById('source_type').value;
        const urlInput = document.getElementById('url_input');
        const fileInput = document.getElementById('file_input');

        if (sourceType === 'url') {
            urlInput.style.display = 'block';
            fileInput.style.display = 'none';
            document.getElementById('source_url').required = true;
            document.getElementById('ontology_file').required = false;
        } else {
            urlInput.style.display = 'none';
            fileInput.style.display = 'block';
            document.getElementById('source_url').required = false;
            document.getElementById('ontology_file').required = true;
        }
    }

    function fillForm(source, name, description, type = 'url') {
        document.getElementById('source_type').value = type;
        if (type === 'url') {
            document.getElementById('source_url').value = source;
        }
        document.getElementById('name').value = name;
        document.getElementById('description').value = description;
        toggleSourceInput();
    }

    // Enable/disable reasoner type based on reasoning checkbox
    document.getElementById('use_reasoning').addEventListener('change', function () {
        document.getElementById('reasoner_type').disabled = !this.checked;
    });

    // Initialize form state
    document.addEventListener('DOMContentLoaded', function () {
        toggleSourceInput();
    });
