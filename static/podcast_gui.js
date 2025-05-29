document.addEventListener('DOMContentLoaded', function() {
    const podcastForm = document.getElementById('podcast-form');
    const generateButton = document.getElementById('generate-button');
    const stopButton = document.getElementById('stop-button');
    const resultsDiv = document.getElementById('results');
    const outputLinksDiv = document.getElementById('output-links');

    // Modal elements
    const progressModal = document.getElementById('progress-modal');
    const progressMessage = document.getElementById('progress-message');
    const consoleOutput = document.getElementById('console-output');
    const spinner = progressModal.querySelector('.spinner');

    // Advanced Settings elements
    const collapsibleButton = document.querySelector('.collapsible');
    const advancedSettingsContent = document.querySelector('.content');
    const qualityPresetSelect = document.getElementById('quality_preset');
    const videoResolutionSelect = document.getElementById('video_resolution');
    const videoFpsSelect = document.getElementById('video_fps');
    const videoIntermediatePresetSelect = document.getElementById('video_intermediate_preset');
    const videoIntermediateCrfSelect = document.getElementById('video_intermediate_crf');
    const videoFinalAudioBitrateSelect = document.getElementById('video_final_audio_bitrate');

    let totalSegments = 0;
    let currentSegment = 0;

    // Handle script file input
    const scriptFile = document.getElementById('script_file');

    // --- Advanced Settings Collapsible ---
    collapsibleButton.addEventListener('click', function() {
        this.classList.toggle('active');
        if (advancedSettingsContent.style.maxHeight) {
            advancedSettingsContent.style.maxHeight = null;
        } else {
            advancedSettingsContent.style.maxHeight = advancedSettingsContent.scrollHeight + "px";
        }
    });

    // --- Quality Preset Logic ---
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

    qualityPresetSelect.addEventListener('change', function() {
        const preset = this.value;
        if (preset && qualityPresets[preset]) {
            const settings = qualityPresets[preset];
            videoResolutionSelect.value = settings.video_resolution;
            videoFpsSelect.value = settings.video_fps;
            videoIntermediatePresetSelect.value = settings.video_intermediate_preset;
            videoIntermediateCrfSelect.value = settings.video_intermediate_crf;
            videoFinalAudioBitrateSelect.value = settings.video_final_audio_bitrate;
        } else if (preset === "") {
            // If "Custom" is selected, do not change values, allow manual input
        }
    });

    // --- Handle Form Submission ---
    podcastForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        // Basic validation for script file
        if (!scriptFile.files || scriptFile.files.length === 0) {
            alert('Please upload a script file.');
            return;
        }

        // Disable generate button, show modal, reset progress
        generateButton.disabled = true;
        stopButton.style.display = 'inline-block'; // Show stop button
        progressModal.style.display = 'flex'; // Show modal
        progressMessage.textContent = 'Initializing...';
        consoleOutput.textContent = ''; // Clear previous console output
        spinner.style.display = 'block'; // Show spinner
        resultsDiv.style.display = 'none';
        outputLinksDiv.innerHTML = '';
        totalSegments = 0;
        currentSegment = 0;

        const formData = new FormData(podcastForm);

        // Send data to backend
        try {
            const response = await fetch('/generate_podcast_audio_video', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (response.ok && result.status === 'processing') {
                consoleOutput.textContent += result.message + '\n';
                streamOutput();
            } else {
                consoleOutput.textContent += 'Error: ' + result.message + '\n' + (result.errors || '');
                resetProcessStatus();
            }

        } catch (error) {
            console.error('Error submitting form:', error);
            consoleOutput.textContent += 'An error occurred while submitting the form.';
            resetProcessStatus();
        }
    });

    // --- Server-Sent Events (SSE) for Real-time Output ---
    function streamOutput() {
        const eventSource = new EventSource('/stream_output');

        eventSource.onmessage = function(event) {
            const data = JSON.parse(event.data);

            if (data.type === 'output') {
                consoleOutput.textContent += data.content;
                consoleOutput.scrollTop = consoleOutput.scrollHeight;
            } else if (data.type === 'total_segments') {
                totalSegments = data.count;
                progressMessage.textContent = `Found ${totalSegments} segments. Generating 0 of ${totalSegments} segments...`;
            } else if (data.type === 'segment_progress') {
                currentSegment = data.current;
                progressMessage.textContent = `Generating ${currentSegment} of ${totalSegments} segments...`;
            } else if (data.type === 'gui_active') {
                progressMessage.textContent = data.content;
                spinner.style.display = 'none'; // Hide spinner when GUI is active
            } else if (data.type === 'video_ready') {
                const videoLink = document.createElement('a');
                videoLink.href = `/outputs/${data.path}`;
                videoLink.textContent = `Download Podcast Video: ${data.path.split('/').pop()}`;
                videoLink.target = '_blank';
                outputLinksDiv.appendChild(videoLink);
                outputLinksDiv.appendChild(document.createElement('br'));
            } else if (data.type === 'complete') {
                consoleOutput.textContent += "\n--- Process Complete ---\n";
                progressMessage.textContent = "Podcast generation finished!";
                spinner.style.display = 'none'; // Hide spinner
                resultsDiv.style.display = 'block';
                eventSource.close();
                resetProcessStatus();
            } else if (data.type === 'error') {
                consoleOutput.textContent += `\n--- Error: ${data.content} ---\n`;
                progressMessage.textContent = "Podcast generation failed!";
                spinner.style.display = 'none'; // Hide spinner
                resetProcessStatus();
            }
        };

        eventSource.onerror = function(event) {
            console.error('SSE Error:', event);
            consoleOutput.textContent += '\n--- Connection to output stream closed or error occurred. ---\n';
            progressMessage.textContent = "Connection error or process stopped.";
            spinner.style.display = 'none'; // Hide spinner
            eventSource.close();
            resetProcessStatus();
        };
    }

    function resetProcessStatus() {
        generateButton.disabled = false;
        stopButton.style.display = 'none'; // Hide stop button
        progressModal.style.display = 'none'; // Hide modal
        spinner.style.display = 'none'; // Ensure spinner is hidden
    }

    // --- Handle Stop Button Click ---
    stopButton.addEventListener('click', async function() {
        stopButton.disabled = true;
        stopButton.textContent = 'Stopping...';
        progressMessage.textContent = 'Stopping process...';
        spinner.style.display = 'block'; // Show spinner while stopping

        try {
            const response = await fetch('/stop_podcast_process', {
                method: 'POST'
            });
            const result = await response.json();
            consoleOutput.textContent += `\n--- ${result.message} ---\n`;
        } catch (error) {
            console.error('Error sending stop signal:', error);
            consoleOutput.textContent += '\n--- Error sending stop signal. ---\n';
        } finally {
            resetProcessStatus();
        }
    });
});