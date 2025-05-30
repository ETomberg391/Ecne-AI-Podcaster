document.addEventListener('DOMContentLoaded', function() {
    // Common elements
    const generateScriptButton = document.getElementById('generate-script-button');
    const generatePodcastButton = document.getElementById('generate-podcast-button');
    const stopScriptButton = document.getElementById('stop-script-button');
    const closeScriptModalButton = document.getElementById('close-script-modal-button'); // New
    const stopPodcastButton = document.getElementById('stop-podcast-button');

    // Modals and output areas
    const scriptProgressModal = document.getElementById('script-progress-modal');
    const scriptProgressMessage = document.getElementById('script-progress-message');
    const scriptConsoleOutput = document.getElementById('script-console-output');
    const scriptSpinner = scriptProgressModal ? scriptProgressModal.querySelector('.spinner') : null;
    const scriptResultsDiv = document.getElementById('script-results');
    const scriptOutputLinksDiv = document.getElementById('script-output-links');
    const scriptTimerSpan = document.getElementById('script-timer');

    const podcastProgressModal = document.getElementById('podcast-progress-modal');
    const podcastProgressMessage = document.getElementById('podcast-progress-message');
    const podcastConsoleOutput = document.getElementById('podcast-console-output');
    const podcastSpinner = podcastProgressModal ? podcastProgressModal.querySelector('.spinner') : null;
    const podcastResultsDiv = document.getElementById('podcast-results');
    const podcastOutputLinksDiv = document.getElementById('podcast-output-links');

    let scriptTimerInterval;
    let scriptStartTime;
    let scriptTotalDuration = 0;
    let scriptProcessCompletedSuccessfully = false; // New flag

    let podcastTotalSegments = 0;
    let podcastCurrentSegment = 0;

    // --- Helper Functions for Drag and Drop (from script.js) ---
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

        files = dt.files;

        if (isSingleFile && files.length > 1) {
             alert("Please drop only one file.");
             if (filePathElement) filePathElement.textContent = '';
             if (fileListElement) fileListElement.innerHTML = '';
             fileInput.value = '';
             return;
        }

        if (fileListElement) {
            fileListElement.innerHTML = '';
        }
        if (filePathElement) {
            filePathElement.textContent = '';
        }

        for (let i = 0; i < files.length; i++) {
            const file = files[i];
            if (fileListElement) {
                const listItem = document.createElement('li');
                listItem.textContent = file.name;
                const removeButton = document.createElement('span');
                removeButton.textContent = 'x';
                removeButton.classList.add('remove-file');
                removeButton.onclick = function() {
                    listItem.remove();
                    // This doesn't remove from fileInput.files directly.
                    // For actual form submission, we'll reconstruct FormData.
                };
                listItem.appendChild(removeButton);
                fileListElement.appendChild(listItem);
            }
            if (isSingleFile && filePathElement) {
                filePathElement.textContent = `File: ${file.name}`;
            }
        }
        fileInput.files = files; // Assign the dropped files to the input
        unhighlight(dropArea);
    }

    // --- Script Builder Specifics (from script.js) ---
    const scriptForm = document.getElementById('script-form');
    if (scriptForm) {
        const referenceDocsDropArea = document.getElementById('reference-docs-drop-area');
        const referenceDocsList = document.getElementById('reference-docs-list');
        const referenceDocsInput = document.getElementById('reference-docs');

        const directArticlesDropArea = document.getElementById('direct-articles-drop-area');
        const directArticlesFilePath = document.getElementById('direct-articles-file-path');
        const directArticlesInput = document.getElementById('direct-articles');

        // Event Listeners for Drag and Drop
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            if (referenceDocsDropArea) referenceDocsDropArea.addEventListener(eventName, preventDefaults, false);
            if (directArticlesDropArea) directArticlesDropArea.addEventListener(eventName, preventDefaults, false);
        });
        ['dragenter', 'dragover'].forEach(eventName => {
            if (referenceDocsDropArea) referenceDocsDropArea.addEventListener(eventName, () => highlight(referenceDocsDropArea), false);
            if (directArticlesDropArea) directArticlesDropArea.addEventListener(eventName, () => highlight(directArticlesDropArea), false);
        });
        ['dragleave', 'drop'].forEach(eventName => {
            if (referenceDocsDropArea) referenceDocsDropArea.addEventListener(eventName, () => unhighlight(referenceDocsDropArea), false);
            if (directArticlesDropArea) directArticlesDropArea.addEventListener(eventName, () => unhighlight(directArticlesDropArea), false);
        });

        if (referenceDocsDropArea) referenceDocsDropArea.addEventListener('drop', (e) => handleDrop(e, referenceDocsDropArea, referenceDocsInput, referenceDocsList, null, false), false);
        if (referenceDocsDropArea) referenceDocsDropArea.addEventListener('click', () => referenceDocsInput.click());
        if (referenceDocsInput) referenceDocsInput.addEventListener('change', function() {
             handleDrop({ dataTransfer: { files: this.files } }, referenceDocsDropArea, this, referenceDocsList, null, false);
        });

        if (directArticlesDropArea) directArticlesDropArea.addEventListener('drop', (e) => handleDrop(e, directArticlesDropArea, directArticlesInput, null, directArticlesFilePath, true), false);
        if (directArticlesDropArea) directArticlesDropArea.addEventListener('click', () => directArticlesInput.click());
        if (directArticlesInput) directArticlesInput.addEventListener('change', function() {
             handleDrop({ dataTransfer: { files: this.files } }, directArticlesDropArea, this, null, directArticlesFilePath, true);
        });

        // Load LLM Models for Dropdown
        const llmModelSelect = document.getElementById('llm-model');
        async function loadLlmModels() {
            if (!llmModelSelect) return;
            try {
                const modelsResponse = await fetch('/get_llm_models');
                const modelsData = await modelsResponse.json();

                if (modelsData.llm_models) {
                     llmModelSelect.innerHTML = '<option value="">Select a model</option>';
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
        loadLlmModels();

        // Handle Script Form Submission
        scriptForm.addEventListener('submit', async function(event) {
            event.preventDefault();

            if (generateScriptButton) generateScriptButton.disabled = true;
            if (stopScriptButton) stopScriptButton.style.display = 'inline-block';
            if (closeScriptModalButton) closeScriptModalButton.style.display = 'none'; // Ensure OK button is hidden at start
            if (scriptProgressModal) scriptProgressModal.style.display = 'flex';
            if (scriptProgressMessage) scriptProgressMessage.textContent = 'Initializing...';
            if (scriptConsoleOutput) scriptConsoleOutput.textContent = '';
            if (scriptSpinner) scriptSpinner.style.display = 'block';
            if (scriptResultsDiv) scriptResultsDiv.style.display = 'none';
            if (scriptOutputLinksDiv) scriptOutputLinksDiv.innerHTML = '';

            scriptProcessCompletedSuccessfully = false; // Reset flag at start of new process
            startScriptTimer();

            const formData = new FormData(scriptForm);

            try {
                const response = await fetch('/generate_script', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (response.ok && result.status === 'processing') {
                    if (scriptConsoleOutput) scriptConsoleOutput.textContent += result.message + '\n';
                    streamOutput('script_builder');
                } else {
                    if (scriptConsoleOutput) scriptConsoleOutput.textContent += 'Error: ' + result.message + '\n' + (result.errors || '');
                    stopScriptTimer();
                    if (scriptTimerSpan) scriptTimerSpan.textContent = formatDuration(scriptTotalDuration);
                    if (stopScriptButton) stopScriptButton.style.display = 'none';
                    if (closeScriptModalButton) closeScriptModalButton.style.display = 'inline-block';
                }
            } catch (error) {
                console.error('Error submitting script form:', error);
                if (scriptConsoleOutput) scriptConsoleOutput.textContent += 'An error occurred while submitting the script form.';
                stopScriptTimer();
                if (scriptTimerSpan) scriptTimerSpan.textContent = formatDuration(scriptTotalDuration);
                if (stopScriptButton) stopScriptButton.style.display = 'none';
                if (closeScriptModalButton) closeScriptModalButton.style.display = 'inline-block';
            }
        });

        // Handle Script Stop Button Click
        if (stopScriptButton) {
            stopScriptButton.addEventListener('click', async function() {
                stopScriptButton.disabled = true;
                stopScriptButton.textContent = 'Stopping...';
                if (scriptProgressMessage) scriptProgressMessage.textContent = 'Stopping process...';
                if (scriptSpinner) scriptSpinner.style.display = 'block';
                stopScriptTimer();

                try {
                    const response = await fetch('/stop_process', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ type: 'script_builder' })
                    });
                    const result = await response.json();
                    if (scriptConsoleOutput) scriptConsoleOutput.textContent += `\n--- ${result.message} ---\n`;
                } catch (error) {
                    console.error('Error sending stop signal for script:', error);
                    if (scriptConsoleOutput) scriptConsoleOutput.textContent += '\n--- Error sending stop signal for script. ---\n';
                } finally {
                    stopScriptTimer();
                    if (scriptTimerSpan) scriptTimerSpan.textContent = formatDuration(scriptTotalDuration);
                    if (stopScriptButton) stopScriptButton.style.display = 'none';
                    if (closeScriptModalButton) closeScriptModalButton.style.display = 'inline-block';
                }
            });
        }
    }

    // --- Podcast Builder Specifics (from podcast_gui.js) ---
    const podcastForm = document.getElementById('podcast-form');
    if (podcastForm) {
        const scriptSelect = document.getElementById('script_select');
        const scriptFile = document.getElementById('script_file');
        const scriptFileGroup = document.getElementById('script_file_group');
        const collapsibleButton = document.querySelector('.collapsible');
        const advancedSettingsContent = document.querySelector('.content');
        const qualityPresetSelect = document.getElementById('quality_preset');
        const videoResolutionSelect = document.getElementById('video_resolution');
        const videoFpsSelect = document.getElementById('video_fps');
        const videoIntermediatePresetSelect = document.getElementById('video_intermediate_preset');
        const videoIntermediateCrfSelect = document.getElementById('video_intermediate_crf');
        const videoFinalAudioBitrateSelect = document.getElementById('video_final_audio_bitrate');

        // Load Available Scripts for Dropdown
        async function loadAvailableScripts() {
            if (!scriptSelect) return;
            try {
                const response = await fetch('/get_available_scripts');
                const data = await response.json();
                
                // Clear existing options
                scriptSelect.innerHTML = '';
                
                // Add default option
                const defaultOption = document.createElement('option');
                defaultOption.value = '';
                defaultOption.textContent = '-- Select a script --';
                scriptSelect.appendChild(defaultOption);
                
                // Add script options
                if (data.scripts && data.scripts.length > 0) {
                    data.scripts.forEach(script => {
                        const option = document.createElement('option');
                        option.value = script.path;
                        option.textContent = `${script.filename} (${script.modified})`;
                        scriptSelect.appendChild(option);
                    });
                }
                
                // Add "Custom" option at the end
                const customOption = document.createElement('option');
                customOption.value = 'custom';
                customOption.textContent = 'Custom (Upload File)';
                scriptSelect.appendChild(customOption);
                
            } catch (error) {
                console.error('Error loading available scripts:', error);
                scriptSelect.innerHTML = '<option value="">Error loading scripts</option>';
            }
        }

        // Handle Script Selection Change
        if (scriptSelect) {
            scriptSelect.addEventListener('change', function() {
                const selectedValue = this.value;
                if (selectedValue === 'custom') {
                    // Show file upload input
                    if (scriptFileGroup) scriptFileGroup.style.display = 'block';
                    if (scriptFile) scriptFile.required = true;
                } else {
                    // Hide file upload input
                    if (scriptFileGroup) scriptFileGroup.style.display = 'none';
                    if (scriptFile) {
                        scriptFile.required = false;
                        scriptFile.value = ''; // Clear any selected file
                    }
                }
            });
        }

        // Load scripts on page load
        loadAvailableScripts();

        // Advanced Settings Collapsible
        if (collapsibleButton) {
            collapsibleButton.addEventListener('click', function() {
                this.classList.toggle('active');
                if (advancedSettingsContent.style.maxHeight) {
                    advancedSettingsContent.style.maxHeight = null;
                } else {
                    advancedSettingsContent.style.maxHeight = advancedSettingsContent.scrollHeight + "px";
                }
            });
        }

        // Quality Preset Logic
        const qualityPresets = {
            "low": {
                video_resolution: "1280x720",
                video_fps: "24",
                video_intermediate_preset: "ultrafast",
                video_intermediate_crf: "28",
                video_final_audio_bitrate: "96k"
            },
            "medium": {
                video_resolution: "1920x1080",
                video_fps: "30",
                video_intermediate_preset: "medium",
                video_intermediate_crf: "23",
                video_final_audio_bitrate: "192k"
            },
            "high": {
                video_resolution: "3840x2160",
                video_fps: "60",
                video_intermediate_preset: "slow",
                video_intermediate_crf: "18",
                video_final_audio_bitrate: "320k"
            }
        };

        if (qualityPresetSelect) {
            qualityPresetSelect.addEventListener('change', function() {
                const preset = this.value;
                if (preset && qualityPresets[preset]) {
                    const settings = qualityPresets[preset];
                    if (videoResolutionSelect) videoResolutionSelect.value = settings.video_resolution;
                    if (videoFpsSelect) videoFpsSelect.value = settings.video_fps;
                    if (videoIntermediatePresetSelect) videoIntermediatePresetSelect.value = settings.video_intermediate_preset;
                    if (videoIntermediateCrfSelect) videoIntermediateCrfSelect.value = settings.video_intermediate_crf;
                    if (videoFinalAudioBitrateSelect) videoFinalAudioBitrateSelect.value = settings.video_final_audio_bitrate;
                } else if (preset === "") {
                    // If "Custom" is selected, do not change values, allow manual input
                }
            });
        }

        // Handle Podcast Form Submission
        podcastForm.addEventListener('submit', async function(event) {
            event.preventDefault();

            // Check if we have either a selected script or uploaded file
            const selectedScript = scriptSelect ? scriptSelect.value : '';
            const hasUploadedFile = scriptFile && scriptFile.files && scriptFile.files.length > 0;
            
            if (selectedScript === 'custom' && !hasUploadedFile) {
                alert('Please upload a script file when "Custom" is selected.');
                return;
            } else if (!selectedScript && !hasUploadedFile) {
                alert('Please select a script from the dropdown or choose "Custom" to upload a file.');
                return;
            } else if (selectedScript && selectedScript !== 'custom' && selectedScript !== '') {
                // Using a predefined script, no file upload needed
                // We'll handle this in the backend
            }

            if (generatePodcastButton) generatePodcastButton.disabled = true;
            if (stopPodcastButton) stopPodcastButton.style.display = 'inline-block';
            if (podcastProgressModal) podcastProgressModal.style.display = 'flex';
            if (podcastProgressMessage) podcastProgressMessage.textContent = 'Initializing...';
            if (podcastConsoleOutput) podcastConsoleOutput.textContent = '';
            if (podcastSpinner) podcastSpinner.style.display = 'block';
            if (podcastResultsDiv) podcastResultsDiv.style.display = 'none';
            if (podcastOutputLinksDiv) podcastOutputLinksDiv.innerHTML = '';
            podcastTotalSegments = 0;
            podcastCurrentSegment = 0;

            const formData = new FormData(podcastForm);

            try {
                const response = await fetch('/generate_podcast_video', {
                    method: 'POST',
                    body: formData
                });

                const result = await response.json();

                if (response.ok && result.status === 'processing') {
                    if (podcastConsoleOutput) podcastConsoleOutput.textContent += result.message + '\n';
                    streamOutput('podcast_builder');
                } else {
                    if (podcastConsoleOutput) podcastConsoleOutput.textContent += 'Error: ' + result.message + '\n' + (result.errors || '');
                    resetPodcastProcessStatus();
                }
            } catch (error) {
                console.error('Error submitting podcast form:', error);
                if (podcastConsoleOutput) podcastConsoleOutput.textContent += 'An error occurred while submitting the podcast form.';
                resetPodcastProcessStatus();
            }
        });

        // Handle Podcast Stop Button Click
        if (stopPodcastButton) {
            stopPodcastButton.addEventListener('click', async function() {
                stopPodcastButton.disabled = true;
                stopPodcastButton.textContent = 'Stopping...';
                if (podcastProgressMessage) podcastProgressMessage.textContent = 'Stopping process...';
                if (podcastSpinner) podcastSpinner.style.display = 'block';

                try {
                    const response = await fetch('/stop_process', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ type: 'podcast_builder' })
                    });
                    const result = await response.json();
                    if (podcastConsoleOutput) podcastConsoleOutput.textContent += `\n--- ${result.message} ---\n`;
                } catch (error) {
                    console.error('Error sending stop signal for podcast:', error);
                    if (podcastConsoleOutput) podcastConsoleOutput.textContent += '\n--- Error sending stop signal for podcast. ---\n';
                } finally {
                    resetPodcastProcessStatus();
                }
            });
        }
    }

    // --- General Stream Output Function ---
    function streamOutput(processType) {
        const eventSource = new EventSource(`/stream_output?type=${processType}`);
        let consoleOutputElement, progressMessageElement, spinnerElement, resultsDivElement, outputLinksDivElement;

        if (processType === 'script_builder') {
            consoleOutputElement = scriptConsoleOutput;
            progressMessageElement = scriptProgressMessage;
            spinnerElement = scriptSpinner;
            resultsDivElement = scriptResultsDiv;
            outputLinksDivElement = scriptOutputLinksDiv;
        } else if (processType === 'podcast_builder') {
            consoleOutputElement = podcastConsoleOutput;
            progressMessageElement = podcastProgressMessage;
            spinnerElement = podcastSpinner;
            resultsDivElement = podcastResultsDiv;
            outputLinksDivElement = podcastOutputLinksDiv;
        } else {
            console.error('Unknown process type for streaming:', processType);
            eventSource.close();
            return;
        }

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);

            if (data.type === 'output') {
                if (consoleOutputElement) {
                    consoleOutputElement.textContent += data.content;
                    consoleOutputElement.scrollTop = consoleOutputElement.scrollHeight;
                }
            } else if (data.type === 'total_segments' && processType === 'podcast_builder') {
                podcastTotalSegments = data.count;
                if (progressMessageElement) progressMessageElement.textContent = `Found ${podcastTotalSegments} dialogue segments. Starting generation...`;
            } else if (data.type === 'segment_progress' && processType === 'podcast_builder') {
                podcastCurrentSegment = data.current;
                const percentage = Math.round((podcastCurrentSegment / podcastTotalSegments) * 100);
                if (progressMessageElement) {
                    progressMessageElement.innerHTML = `
                        Processing segment ${podcastCurrentSegment} of ${podcastTotalSegments} (${percentage}%)
                        <div style="width: 100%; background-color: #f0f0f0; border-radius: 5px; margin-top: 5px;">
                            <div style="width: ${percentage}%; background-color: #007bff; height: 20px; border-radius: 5px; transition: width 0.3s ease;"></div>
                        </div>
                    `;
                }
            } else if (data.type === 'processing_update' && processType === 'podcast_builder') {
                if (progressMessageElement) progressMessageElement.textContent = data.message;
            } else if (data.type === 'gui_active' && processType === 'podcast_builder') {
                if (progressMessageElement) progressMessageElement.textContent = data.content;
                if (spinnerElement) spinnerElement.style.display = 'none';
            } else if (data.type === 'video_ready' && processType === 'podcast_builder') {
                const videoLink = document.createElement('a');
                videoLink.href = `/outputs/${data.path}`;
                videoLink.textContent = `Download Podcast Video: ${data.path.split('/').pop()}`;
                videoLink.target = '_blank';
                if (outputLinksDivElement) {
                    outputLinksDivElement.appendChild(videoLink);
                    outputLinksDivElement.appendChild(document.createElement('br'));
                }
            } else if (data.type === 'complete') {
                if (processType === 'script_builder') {
                    scriptProcessCompletedSuccessfully = true; // Set flag FIRST
                }

                if (consoleOutputElement) consoleOutputElement.textContent += "\n--- Process Complete ---\n";
                if (progressMessageElement) progressMessageElement.textContent = `${processType.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())} finished!`;
                if (spinnerElement) spinnerElement.style.display = 'none';
                if (resultsDivElement) resultsDivElement.style.display = 'block'; // Show the results div
                if (outputLinksDivElement) outputLinksDivElement.innerHTML = '';

                if (processType === 'script_builder') {
                    stopScriptTimer();
                    if (data.total_duration !== undefined && scriptTimerSpan) {
                        scriptTotalDuration = data.total_duration;
                        scriptTimerSpan.textContent = formatDuration(scriptTotalDuration);
                    } else if (scriptTimerSpan) {
                        scriptTimerSpan.textContent = formatDuration(scriptTotalDuration); // Fallback to calculated duration
                    }

                    if (data.output_files && data.output_files.length > 0) {
                        if (progressMessageElement) progressMessageElement.textContent = `Success! Script finished.`;
                        data.output_files.forEach(filePath => {
                            const fileName = filePath.split('/').pop();
                            const fileLink = document.createElement('a');
                            fileLink.href = `/outputs/${filePath}`;
                            fileLink.target = '_blank';
                            
                            // Determine the display label based on file type
                            if (fileName.endsWith('_podcast_script.txt')) {
                                fileLink.textContent = `Final Script: ${fileName}`;
                            } else if (fileName.endsWith('_report.txt')) {
                                fileLink.textContent = `Generated Report: ${fileName}`;
                            } else {
                                fileLink.textContent = `Download: ${fileName}`;
                            }
                            
                            if (outputLinksDivElement) {
                                outputLinksDivElement.appendChild(fileLink);
                                outputLinksDivElement.appendChild(document.createElement('br'));
                            }
                        });
                    } else {
                        if (progressMessageElement) progressMessageElement.textContent = "Process Complete. No output files found.";
                        if (outputLinksDivElement) outputLinksDivElement.textContent = "No output files found.";
                    }
                    if (stopScriptButton) stopScriptButton.style.display = 'none';
                    if (closeScriptModalButton) closeScriptModalButton.style.display = 'inline-block';
                } else if (processType === 'podcast_builder') {
                    if (data.output_files && data.output_files.length > 0) {
                        if (progressMessageElement) progressMessageElement.textContent = `Success! Podcast generated.`;
                        data.output_files.forEach(filePath => {
                            const fileName = filePath.split('/').pop();
                            const fileLink = document.createElement('a');
                            fileLink.href = `/outputs/${filePath}`;
                            fileLink.target = '_blank';
                            
                            // Label podcast files appropriately
                            if (fileName.endsWith('.mp4')) {
                                fileLink.textContent = `Download Podcast Video: ${fileName}`;
                            } else {
                                fileLink.textContent = `Download: ${fileName}`;
                            }
                            
                            if (outputLinksDivElement) {
                                outputLinksDivElement.appendChild(fileLink);
                                outputLinksDivElement.appendChild(document.createElement('br'));
                            }
                        });
                    } else {
                        if (progressMessageElement) progressMessageElement.textContent = "Podcast generation complete. No output files found.";
                        if (outputLinksDivElement) outputLinksDivElement.textContent = "No output files found.";
                    }
                    resetPodcastProcessStatus();
                }
                eventSource.close();
            } else if (data.type === 'error') {
                stopScriptTimer();
                if (scriptTimerSpan) scriptTimerSpan.textContent = formatDuration(scriptTotalDuration);

                if (consoleOutputElement) consoleOutputElement.textContent += `\n--- Error: ${data.content} ---\n`;
                if (progressMessageElement) progressMessageElement.textContent = `${processType.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())} failed!`;
                if (spinnerElement) spinnerElement.style.display = 'none';
                if (processType === 'script_builder') {
                    if (stopScriptButton) stopScriptButton.style.display = 'none';
                    if (closeScriptModalButton) closeScriptModalButton.style.display = 'inline-block';
                } else if (processType === 'podcast_builder') {
                    resetPodcastProcessStatus();
                }
            }
        };

        eventSource.onerror = function(event) {
            console.error('SSE Error:', event);
            // Only display error message if the process was NOT successfully completed
            if (processType === 'script_builder' && !scriptProcessCompletedSuccessfully) {
                if (consoleOutputElement) consoleOutputElement.textContent += '\n--- Connection to output stream closed or error occurred. ---\n';
                if (progressMessageElement) progressMessageElement.textContent = "Connection error or process stopped.";
                if (spinnerElement) spinnerElement.style.display = 'none';
                if (stopScriptButton) stopScriptButton.style.display = 'none';
                if (closeScriptModalButton) closeScriptModalButton.style.display = 'inline-block';
                stopScriptTimer();
                if (scriptTimerSpan) scriptTimerSpan.textContent = formatDuration(scriptTotalDuration);
            } else if (processType === 'podcast_builder') {
                resetPodcastProcessStatus();
            }
            eventSource.onerror = null; // Prevent infinite loop on error
            eventSource.close();
        };
    }

    // Handle Close Script Modal Button Click
    if (closeScriptModalButton) {
        closeScriptModalButton.addEventListener('click', function() {
            resetScriptProcessStatus(); // This will hide the modal
        });
    }

    // --- Script Timer Logic ---
    function formatDuration(totalSeconds) {
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    function startScriptTimer() {
        scriptStartTime = Date.now();
        if (scriptTimerSpan) scriptTimerSpan.textContent = '00:00:00';
        scriptTimerInterval = setInterval(updateScriptTimer, 1000);
    }

    function updateScriptTimer() {
        const elapsed = Date.now() - scriptStartTime;
        scriptTotalDuration = Math.floor(elapsed / 1000);
        if (scriptTimerSpan) scriptTimerSpan.textContent = formatDuration(scriptTotalDuration);
    }

    function stopScriptTimer() {
        clearInterval(scriptTimerInterval);
    }

    // --- Reset Process Status Functions ---
    function resetScriptProcessStatus() {
        if (generateScriptButton) generateScriptButton.disabled = false;
        if (stopScriptButton) {
            stopScriptButton.style.display = 'none';
            stopScriptButton.disabled = false;
            stopScriptButton.textContent = 'Stop Script Generation';
        }
        if (closeScriptModalButton) { // Ensure OK button is hidden when modal is reset
            closeScriptModalButton.style.display = 'none';
        }
        if (scriptProgressModal) scriptProgressModal.style.display = 'none';
        if (scriptSpinner) scriptSpinner.style.display = 'none';
        if (scriptTimerSpan) scriptTimerSpan.textContent = '00:00:00'; // Reset timer display when modal closes
        scriptTotalDuration = 0;
    }

    function resetPodcastProcessStatus() {
        if (generatePodcastButton) generatePodcastButton.disabled = false;
        if (stopPodcastButton) {
            stopPodcastButton.style.display = 'none';
            stopPodcastButton.disabled = false;
            stopPodcastButton.textContent = 'Stop Podcast Generation';
        }
        if (podcastProgressModal) podcastProgressModal.style.display = 'none';
        if (podcastSpinner) podcastSpinner.style.display = 'none';
    }

    // --- Settings Page Specifics (from settings.js) ---
    const apiKeyForm = document.getElementById('api-keys-form');
    const llmSettingsForm = document.getElementById('llm-settings-form');
    const llmModelSelect = document.getElementById('llm-model-select');
    const llmModelDetails = document.getElementById('llm-model-details');
    const updateLlmModelButton = document.getElementById('update-llm-model'); // New button
    const deleteLlmModelButton = document.getElementById('delete-llm-model');

    if (apiKeyForm && llmSettingsForm && llmModelSelect && llmModelDetails && updateLlmModelButton && deleteLlmModelButton) {
        // --- Load Settings on Page Load ---
        async function loadSettings() {
            try {
                const response = await fetch('/get_settings'); // Fetch data from the new JSON endpoint
                const data = await response.json();

                // Populate API Keys form
                if (data.api_keys) {
                    for (const key in data.api_keys) {
                        const input = document.getElementById(key.toLowerCase()); // Assuming input IDs match lowercase env var names
                        if (input) {
                            input.value = data.api_keys[key];
                        }
                    }
                }

                // Populate LLM Models dropdown
                if (data.llm_settings) {
                    llmModelSelect.innerHTML = '<option value="">-- Select a model --</option>'; // Clear existing options except the default
                    const modelKeys = Object.keys(data.llm_settings);
                    modelKeys.forEach(modelKey => {
                        const option = document.createElement('option');
                        option.value = modelKey;
                        option.textContent = modelKey;
                        llmModelSelect.appendChild(option);
                    });

                    // Automatically select the first model if available and trigger change event
                    if (modelKeys.length > 0) {
                        llmModelSelect.value = modelKeys[0];
                        llmModelSelect.dispatchEvent(new Event('change'));
                    }
                }

            } catch (error) {
                console.error('Error loading settings:', error);
                alert('Failed to load settings.');
            }
        }

        // --- Handle LLM Model Selection Change ---
        llmModelSelect.addEventListener('change', async function() {
            const selectedKey = this.value;
            if (selectedKey) {
                try {
                    const response = await fetch('/get_settings');
                    const data = await response.json();
                    const selectedModelSettings = data.llm_settings ? data.llm_settings[selectedKey] : null;

                    if (selectedModelSettings) {
                        llmModelDetails.style.display = 'block';
                        // Clear all input fields in the details section before populating
                        llmModelDetails.querySelectorAll('input, textarea').forEach(input => {
                            input.value = '';
                        });

                        // Populate LLM model details form
                        for (const key in selectedModelSettings) {
                            const input = llmModelDetails.querySelector(`[name="${key}"]`);
                            if (input) {
                                if (key === 'tool_config' && typeof selectedModelSettings[key] === 'object') {
                                     input.value = JSON.stringify(selectedModelSettings[key], null, 2);
                                } else {
                                     input.value = selectedModelSettings[key];
                                }
                            }
                        }
                         // Set the model name input as readonly
                         const modelNameInput = llmModelDetails.querySelector('[name="model"]');
                         if (modelNameInput) {
                             modelNameInput.setAttribute('readonly', 'true');
                         }

                    } else {
                        llmModelDetails.style.display = 'none';
                    }
                } catch (error) {
                    console.error('Error fetching LLM settings for selected model:', error);
                    llmModelDetails.style.display = 'none';
                }

            } else {
                llmModelDetails.style.display = 'none';
            }
        });


        // --- Handle Save API Keys Form Submission ---
        apiKeyForm.addEventListener('submit', async function(event) {
            event.preventDefault();

            const formData = new FormData(apiKeyForm);
            const apiKeysData = {};
            formData.forEach((value, key) => {
                apiKeysData[key] = value;
            });

            try {
                const response = await fetch('/save_settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ apiKeys: apiKeysData })
                });

                const result = await response.json();
                if (response.ok) {
                    alert(result.message);
                } else {
                    alert('Error saving API keys: ' + result.message);
                }
            } catch (error) {
                console.error('Error saving API keys:', error);
                alert('Failed to save API keys.');
            }
        });
        // --- Helper function to save LLM settings ---
        async function saveLlmSettings(llmSettingsToSave) {
            try {
                const response = await fetch('/save_settings', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ llmSettings: llmSettingsToSave })
                });

                const result = await response.json();
                if (response.ok) {
                    alert(result.message);
                    loadSettings(); // Reload settings to update dropdown
                } else {
                    alert('Error saving LLM settings: ' + result.message);
                }
            } catch (error) {
                console.error('Error saving LLM settings:', error);
                // Check if the error was due to invalid JSON parsing
                if (error.message !== "Invalid JSON in Tool Config") {
                     alert('Failed to save LLM settings.');
                }
            }
        }

        // --- Handle Save LLM Settings Form Submission (for new model) ---
        llmSettingsForm.addEventListener('submit', async function(event) {
            event.preventDefault();

            const formData = new FormData(llmSettingsForm);
            const newModelKey = formData.get('new_llm_key');

            if (!newModelKey) {
                alert("Please provide a 'New Model Key' to add a new LLM model.");
                return;
            }

            // Load existing settings first to merge changes
            const existingSettingsResponse = await fetch('/get_settings');
            const existingSettingsData = await existingSettingsResponse.json();
            const currentLlmSettings = existingSettingsData.llm_settings || {};

            if (currentLlmSettings.hasOwnProperty(newModelKey)) {
                alert(`Model key "${newModelKey}" already exists. Please use a different key or update the existing model.`);
                return;
            }

            const newModelSettings = {};
            llmSettingsForm.querySelectorAll('input[name^="new_"], textarea[name^="new_"]').forEach(input => {
                const originalName = input.name.replace('new_', '');
                if (originalName && originalName !== 'llm_key') { // Exclude the new_llm_key itself
                    let value = input.value;
                    if (originalName === 'tool_config') {
                        try {
                            value = JSON.parse(value);
                        } catch (e) {
                            console.error("Invalid JSON in New Tool Config:", e);
                            alert("Invalid JSON in New Tool Config field.");
                            throw new Error("Invalid JSON in New Tool Config");
                        }
                    } else if (input.type === 'number') {
                        value = parseFloat(value);
                        if (isNaN(value)) value = null;
                    }
                    newModelSettings[originalName] = value;
                }
            });
            currentLlmSettings[newModelKey] = newModelSettings;

            await saveLlmSettings(currentLlmSettings);
        });

        // --- Handle Update LLM Model Button Click ---
        updateLlmModelButton.addEventListener('click', async function() {
            const selectedKey = llmModelSelect.value;
            if (!selectedKey || selectedKey === "") {
                alert("Please select an LLM model to update.");
                return;
            }

            // Load existing settings
            const existingSettingsResponse = await fetch('/get_settings');
            const existingSettingsData = await existingSettingsResponse.json();
            const currentLlmSettings = existingSettingsData.llm_settings || {};

            if (!currentLlmSettings.hasOwnProperty(selectedKey)) {
                alert(`LLM model configuration for "${selectedKey}" not found.`);
                return;
            }

            const updatedModelSettings = {};
            llmModelDetails.querySelectorAll('input, textarea').forEach(input => {
                if (input.name) {
                    let value = input.value;
                    if (input.name === 'tool_config') {
                        try {
                            value = JSON.parse(value);
                        } catch (e) {
                            console.error("Invalid JSON in Tool Config:", e);
                            alert("Invalid JSON in Tool Config field.");
                            throw new Error("Invalid JSON in Tool Config");
                        }
                    } else if (input.type === 'number') {
                        value = parseFloat(value);
                        if (isNaN(value)) value = null;
                    }
                    updatedModelSettings[input.name] = value;
                }
            });
            currentLlmSettings[selectedKey] = updatedModelSettings;

            await saveLlmSettings(currentLlmSettings);
        });

        // --- Handle Delete LLM Model Button Click ---
        deleteLlmModelButton.addEventListener('click', async function() {
            const selectedKey = llmModelSelect.value;
            if (!selectedKey || selectedKey === "") {
                alert("Please select an LLM model to delete.");
                return;
            }
            if (confirm(`Are you sure you want to delete the LLM model configuration for "${selectedKey}"? This action cannot be undone.`)) {
                try {
                    const existingSettingsResponse = await fetch('/get_settings');
                    const existingSettingsData = await existingSettingsResponse.json();
                    const currentLlmSettings = existingSettingsData.llm_settings || {};

                    if (currentLlmSettings.hasOwnProperty(selectedKey)) {
                        delete currentLlmSettings[selectedKey];
                        await saveLlmSettings(currentLlmSettings);
                        llmModelDetails.style.display = 'none';
                    } else {
                        alert(`LLM model configuration for "${selectedKey}" not found.`);
                    }
                } catch (error) {
                    console.error('Error deleting LLM model:', error);
                    alert('Failed to delete LLM model.');
                }
            }
        });

        // Initial load of settings when the page loads
        loadSettings();
    }
});