document.addEventListener('DOMContentLoaded', function() {
    const podcastForm = document.getElementById('report-form'); // Keep ID for now, update variable name
    const generateButton = document.getElementById('generate-button');
    const processStatusDiv = document.getElementById('process-status');
    const stopButton = document.getElementById('stop-button');
    const loadingSpinner = document.getElementById('loading-spinner');
    const timerSpan = document.getElementById('timer');
    const outputDiv = document.getElementById('output').querySelector('pre');
    const resultsDiv = document.getElementById('results');
    const outputLinksDiv = document.getElementById('output-links'); // Updated ID
    const llmModelSelect = document.getElementById('llm-model');

    const referenceDocsDropArea = document.getElementById('reference-docs-drop-area');
    const referenceDocsList = document.getElementById('reference-docs-list');
    const referenceDocsInput = document.getElementById('reference-docs');
    let uploadedReferenceDocs = []; // Store paths of uploaded reference docs

    const directArticlesDropArea = document.getElementById('direct-articles-drop-area');
    const directArticlesFilePath = document.getElementById('direct-articles-file-path');
    const directArticlesInput = document.getElementById('direct-articles');
    let uploadedDirectArticlesFile = null; // Store path of the uploaded file


    // --- Helper Functions for Drag and Drop ---
    function preventDefaults(event) {
        event.preventDefault();
        event.stopPropagation();
    }

    function highlight(element) {
        element.classList.add('highlight');
    }

    function unhighlight(element) {
        element.classList.remove('highlight');
    }

    function handleDrop(event, dropArea, fileInput, fileListElement = null, filePathElement = null, isSingleFile = false) {
        const dt = event.dataTransfer;
        let files = [];

        // For file drop
        files = dt.files;

        if (isSingleFile && files.length > 1) {
             alert("Please drop only one file.");
             filePathElement.textContent = '';
             if (fileListElement) fileListElement.innerHTML = '';
             if (isSingleFile && filePathElement) filePathElement.textContent = '';
             fileInput.value = ''; // Clear the file input
             if (isSingleFile && dropArea === directArticlesDropArea) uploadedDirectArticlesFile = null;
             return;
        }

        if (fileListElement) {
            fileListElement.innerHTML = ''; // Clear previous list for multiple files
        }
        if (filePathElement) {
            filePathElement.textContent = ''; // Clear previous path for single file
        }

        const fileList = [];
        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            fileList.push(file);
            if (fileListElement) {
                const listItem = document.createElement('li');
                listItem.textContent = file.name;
                const removeButton = document.createElement('span');
                removeButton.textContent = 'x';
                removeButton.classList.add('remove-file');
                removeButton.onclick = function() {
                    // Remove from list and potentially from a temporary storage if implemented
                    listItem.remove();
                    // Note: Removing from the visual list doesn't remove from the input's FileList directly.
                    // We'll handle the actual files to upload when the form is submitted.
                    // For now, rely on the input.files or a separate array if needed.
                };
                listItem.appendChild(removeButton);
                fileListElement.appendChild(listItem);
            }
            if (isSingleFile && filePathElement) {
                filePathElement.textContent = `File: ${file.name}`;
            }
        }

        // Assign the dropped files to the corresponding file input element
        fileInput.files = files;

        // Store the file names/paths temporarily. Actual paths will come from backend after upload.
        if (dropArea === referenceDocsDropArea) {
            uploadedReferenceDocs = Array.from(files).map(f => f.name); // Store names for display
        } else if (dropArea === directArticlesDropArea) {
            uploadedDirectArticlesFile = files.length > 0 ? files[0].name : null; // Store name for display
        }

        unhighlight(dropArea);
    }

    // --- Event Listeners for Drag and Drop ---

    // Reference Docs (Multiple Files)
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        referenceDocsDropArea.addEventListener(eventName, preventDefaults, false);
    });
    ['dragenter', 'dragover'].forEach(eventName => {
        referenceDocsDropArea.addEventListener(eventName, () => highlight(referenceDocsDropArea), false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
        referenceDocsDropArea.addEventListener(eventName, () => unhighlight(referenceDocsDropArea), false);
    });
    referenceDocsDropArea.addEventListener('drop', (e) => handleDrop(e, referenceDocsDropArea, referenceDocsInput, referenceDocsList, null, false), false);
    // Allow clicking the drop area to open file dialog
    referenceDocsDropArea.addEventListener('click', () => referenceDocsInput.click());
    referenceDocsInput.addEventListener('change', function() {
         handleDrop({ dataTransfer: { files: this.files } }, referenceDocsDropArea, this, referenceDocsList, null, false);
    });


    // Direct Articles File (Single .txt File)
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        directArticlesDropArea.addEventListener(eventName, preventDefaults, false);
    });
    ['dragenter', 'dragover'].forEach(eventName => {
        directArticlesDropArea.addEventListener(eventName, () => highlight(directArticlesDropArea), false);
    });
    ['dragleave', 'drop'].forEach(eventName => {
        directArticlesDropArea.addEventListener(eventName, () => unhighlight(directArticlesDropArea), false);
    });
    directArticlesDropArea.addEventListener('drop', (e) => handleDrop(e, directArticlesDropArea, directArticlesInput, null, directArticlesFilePath, true), false);
     // Allow clicking the drop area to open file dialog
    directArticlesDropArea.addEventListener('click', () => directArticlesInput.click());
    directArticlesInput.addEventListener('change', function() {
         handleDrop({ dataTransfer: { files: this.files } }, directArticlesDropArea, this, null, directArticlesFilePath, true);
    });


    // --- Load LLM Models for Dropdown ---
    async function loadLlmModels() {
        try {
            const response = await fetch('/'); // Fetch data from the index route
            const text = await response.text(); // Get the HTML content as text
            // We need to parse the HTML to find the data passed by Flask
            // A better approach would be a dedicated endpoint to get models
            // For now, let's assume Flask passes a JS variable or similar
            // Or, we can make a new endpoint /get_llm_models

            // Let's add a new endpoint for this
            const modelsResponse = await fetch('/get_llm_models');
            const modelsData = await modelsResponse.json();

            if (modelsData.llm_models) {
                 llmModelSelect.innerHTML = '<option value="">Select a model</option>'; // Clear existing
                 modelsData.llm_models.forEach(modelKey => {
                      const option = document.createElement('option');
                      option.value = modelKey;
                      option.textContent = modelKey;
                      llmModelSelect.appendChild(option);
                 });
            }

        } catch (error) {
            console.error('Error loading LLM models:', error);
        }
    }

    // Call loadLlmModels when the page loads
    loadLlmModels();


    // --- Handle Form Submission ---
    podcastForm.addEventListener('submit', async function(event) { // Use updated variable name
        event.preventDefault();

        // Disable generate button, show process status, start timer
        generateButton.disabled = true;
        processStatusDiv.style.display = 'flex'; // Use flex to align items
        startTimer();

        const formData = new FormData(podcastForm); // Use updated variable name

        // Append uploaded files to the FormData
        // Note: The file inputs already hold the dropped/selected files due to handleDrop
        // formData.append('reference-docs', referenceDocsInput.files); // This appends FileList, which FormData handles
        // formData.append('direct-articles', directArticlesInput.files[0]); // Append the single file
        // formData.append('reference-docs-folder', referenceDocsFolderInput.files); // Append the FileList for the folder

        // Clear previous output and results
        outputDiv.textContent = '';
        resultsDiv.style.display = 'none';
        outputLinksDiv.innerHTML = ''; // Use updated variable name

        // Send data to backend
        try {
            const response = await fetch('/generate_podcast', { // Updated endpoint
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.status === 'processing') {
                outputDiv.textContent = result.message + '\n';
                // Start streaming output
                streamOutput();
            } else {
                outputDiv.textContent = 'Error: ' + result.message + '\n' + (result.errors || '');
                stopTimer(); // Stop timer on backend error
                displayTotalDuration(); // Display duration on backend error
                resetProcessStatus(); // Reset button/spinner/timer state on backend error
            }

        } catch (error) {
            console.error('Error submitting form:', error);
            outputDiv.textContent = 'An error occurred while submitting the form.';
            stopTimer(); // Stop timer on fetch error
            displayTotalDuration(); // Display duration on fetch error
            resetProcessStatus(); // Reset button/spinner/timer state on fetch error
        }
    });

    // --- Server-Sent Events (SSE) for Real-time Output ---
    function streamOutput() {
        const eventSource = new EventSource('/stream_output');

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);
            if (data.type === 'output') {
                outputDiv.textContent += data.content;
                // Auto-scroll to the bottom
                outputDiv.scrollTop = outputDiv.scrollHeight;
            } else if (data.type === 'complete') {
                outputDiv.textContent += "\n--- Process Complete ---\n";
                resultsDiv.style.display = 'block';
                outputLinksDiv.innerHTML = ''; // Clear previous links, use updated variable name
                if (data.output_files && data.output_files.length > 0) { // Updated data key
                    // Find the script file (ends with .txt) and the audio file (ends with .mp3)
                    let scriptFile = null;
                    let audioFile = null;

                    data.output_files.forEach(file => {
                        // Look for the final script file ending with '_podcast_script.txt'
                        if (file.endsWith('_podcast_script.txt')) {
                            scriptFile = file;
                        } else if (file.endsWith('.mp3')) {
                            audioFile = file;
                        }
                        // Add other file types (.md, .pdf) if needed in the future
                    });

                    if (scriptFile) {
                        const scriptLink = document.createElement('a');
                        // Assuming files are served from /outputs/
                        // Use the full relative path including the timestamped folder
                        scriptLink.href = `/outputs/${scriptFile}`;
                        scriptLink.textContent = `Download Script: ${scriptFile}`;
                        scriptLink.target = '_blank'; // Open in new tab
                        outputLinksDiv.appendChild(scriptLink);
                        outputLinksDiv.appendChild(document.createElement('br'));
                    } else {
                         outputLinksDiv.textContent = "Script file not found.";
                    }

                } else {
                    outputLinksDiv.textContent = "No output files found.";
                }
                eventSource.close(); // Close the connection when complete
                stopTimer(); // Stop the timer on completion
                displayTotalDuration(); // Display total duration
                resetProcessStatus(); // Reset button/spinner/timer state
            } else if (data.type === 'error') {
                 outputDiv.textContent += `\n--- Error: ${data.content} ---\n`;
                 stopTimer(); // Stop the timer on error
                 displayTotalDuration(); // Display total duration
                 resetProcessStatus(); // Reset button/spinner/timer state
            }
        };

        eventSource.onerror = function(event) {
            console.error('SSE Error:', event);
            outputDiv.textContent += '\n--- Connection to output stream closed. ---\n';
            eventSource.close();
            stopTimer(); // Stop the timer on SSE error
            displayTotalDuration(); // Display total duration
            resetProcessStatus(); // Reset button/spinner/timer state
        };
    }

    // --- Timer Logic ---
    let timerInterval;
    let startTime;
    let totalDuration = 0;

    function startTimer() {
        startTime = Date.now();
        timerSpan.textContent = '00:00:00';
        timerInterval = setInterval(updateTimer, 1000);
    }

    function updateTimer() {
        const elapsed = Date.now() - startTime;
        const seconds = Math.floor(elapsed / 1000);
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainingSeconds = seconds % 60;

        const formattedTime = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(remainingSeconds).padStart(2, '0')}`;
        timerSpan.textContent = formattedTime;
        totalDuration = seconds; // Store total duration in seconds
    }

    function stopTimer() {
        clearInterval(timerInterval);
    }

    function displayTotalDuration() {
        const hours = Math.floor(totalDuration / 3600);
        const minutes = Math.floor((totalDuration % 3600) / 60);
        const seconds = totalDuration % 60;
        const formattedDuration = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
        outputDiv.textContent += `\nTotal Duration: ${formattedDuration}\n`;
    }

    function resetProcessStatus() {
        generateButton.disabled = false;
        processStatusDiv.style.display = 'none';
        stopButton.disabled = false; // Reset disabled state
        stopButton.textContent = 'Stop Podcast'; // Reset text
        timerSpan.textContent = '00:00:00'; // Reset timer display
        totalDuration = 0; // Reset total duration
    }


    // --- Handle Stop Button Click ---
    stopButton.addEventListener('click', async function() {
        // Disable stop button while sending stop request
        stopButton.disabled = true;
        stopButton.textContent = 'Stopping...';
        stopTimer(); // Stop the timer immediately on click

        try {
            const response = await fetch('/stop_podcast', { // Updated endpoint
                method: 'POST'
            });
            const result = await response.json();
            outputDiv.textContent += `\n--- ${result.message} ---\n`;
        } catch (error) {
            console.error('Error sending stop signal:', error);
            outputDiv.textContent += '\n--- Error sending stop signal. ---\n';
        } finally {
            resetProcessStatus(); // Reset button/spinner/timer state
        }
    });

});
