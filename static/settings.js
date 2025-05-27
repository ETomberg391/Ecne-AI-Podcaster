document.addEventListener('DOMContentLoaded', function() {
    const apiKeyForm = document.getElementById('api-keys-form');
    const llmSettingsForm = document.getElementById('llm-settings-form');
    const llmModelSelect = document.getElementById('llm-model-select');
    const llmModelDetails = document.getElementById('llm-model-details');
    const deleteLlmModelButton = document.getElementById('delete-llm-model');

    // --- Load Settings on Page Load ---
    async function loadSettings() {
        try {
            const response = await fetch('/settings'); // Fetch data from the settings route
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
                // Clear existing options except the default
                llmModelSelect.innerHTML = '<option value="">-- Select a model --</option>';
                for (const key in data.llm_settings) {
                    const option = document.createElement('option');
                    option.value = key;
                    option.textContent = key;
                    llmModelSelect.appendChild(option);
                }
            }

        } catch (error) {
            console.error('Error loading settings:', error);
            alert('Failed to load settings.');
        }
    }

    // --- Handle LLM Model Selection Change ---
    llmModelSelect.addEventListener('change', function() {
        const selectedKey = this.value;
        if (selectedKey) {
            // Find the selected model's settings from the loaded data (assuming loadSettings was successful)
             fetch('/settings')
                .then(response => response.json())
                .then(data => {
                    const selectedModelSettings = data.llm_settings ? data.llm_settings[selectedKey] : null;
                    if (selectedModelSettings) {
                        llmModelDetails.style.display = 'block';
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
                })
                .catch(error => {
                    console.error('Error fetching LLM settings for selected model:', error);
                    llmModelDetails.style.display = 'none';
                });

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

    // --- Handle Save LLM Settings Form Submission ---
    llmSettingsForm.addEventListener('submit', async function(event) {
        event.preventDefault();

        const formData = new FormData(llmSettingsForm);
        const llmSettings = {};
        const newModelKey = formData.get('new_llm_key');

        // Load existing settings first to merge changes
        const existingSettingsResponse = await fetch('/settings');
        const existingSettingsData = await existingSettingsResponse.json();
        const currentLlmSettings = existingSettingsData.llm_settings || {};

        // Handle selected model updates
        const selectedKey = llmModelSelect.value;
        if (selectedKey) {
             const updatedModelSettings = {};
             // Collect data from the visible llmModelDetails fields
             llmModelDetails.querySelectorAll('input, textarea').forEach(input => {
                 if (input.name) {
                      let value = input.value;
                      // Attempt to parse JSON for tool_config
                      if (input.name === 'tool_config') {
                           try {
                                value = JSON.parse(value);
                           } catch (e) {
                                console.error("Invalid JSON in Tool Config:", e);
                                alert("Invalid JSON in Tool Config field.");
                                throw new Error("Invalid JSON in Tool Config"); // Stop submission
                           }
                      } else if (input.type === 'number') {
                           value = parseFloat(value);
                           if (isNaN(value)) value = null; // Handle empty number inputs
                      }
                      updatedModelSettings[input.name] = value;
                 }
             });
             currentLlmSettings[selectedKey] = updatedModelSettings;
        }


        // Handle new model addition
        if (newModelKey) {
             const newModelSettings = {};
             // Collect data from the 'Add New LLM Model' fields
             llmSettingsForm.querySelectorAll('input[name^="new_"], textarea[name^="new_"]').forEach(input => {
                 const originalName = input.name.replace('new_', '');
                 if (originalName) {
                      let value = input.value;
                       // Attempt to parse JSON for tool_config
                      if (originalName === 'tool_config') {
                           try {
                                value = JSON.parse(value);
                           } catch (e) {
                                console.error("Invalid JSON in New Tool Config:", e);
                                alert("Invalid JSON in New Tool Config field.");
                                throw new Error("Invalid JSON in New Tool Config"); // Stop submission
                           }
                      } else if (input.type === 'number') {
                           value = parseFloat(value);
                           if (isNaN(value)) value = null; // Handle empty number inputs
                      }
                      newModelSettings[originalName] = value;
                 }
             });
             currentLlmSettings[newModelKey] = newModelSettings;
        }


        try {
            const response = await fetch('/save_settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ llmSettings: currentLlmSettings })
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
    });

    // --- Handle Delete LLM Model Button Click ---
    deleteLlmModelButton.addEventListener('click', async function() {
        const selectedKey = llmModelSelect.value;
        if (!selectedKey || selectedKey === "") {
            alert("Please select an LLM model to delete.");
            return;
        }

        if (confirm(`Are you sure you want to delete the LLM model configuration for "${selectedKey}"?`)) {
            try {
                 // Load existing settings
                const existingSettingsResponse = await fetch('/settings');
                const existingSettingsData = await existingSettingsResponse.json();
                const currentLlmSettings = existingSettingsData.llm_settings || {};

                // Delete the selected key
                if (currentLlmSettings.hasOwnProperty(selectedKey)) {
                    delete currentLlmSettings[selectedKey];

                    // Save the updated settings
                    const response = await fetch('/save_settings', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ llmSettings: currentLlmSettings })
                    });

                    const result = await response.json();
                    if (response.ok) {
                        alert(result.message);
                        llmModelDetails.style.display = 'none'; // Hide details section
                        loadSettings(); // Reload settings to update dropdown
                    } else {
                        alert('Error deleting LLM model: ' + result.message);
                    }
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
});