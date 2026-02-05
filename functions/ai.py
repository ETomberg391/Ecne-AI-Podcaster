import requests
import json
import time
import os
import random # Used for retry delay jitter

from .utils import log_to_file, clean_thinking_tags # Import necessary functions from utils

def call_ai_api(prompt, config, tool_name="General", timeout=300, retries=1, base_wait_time=60):
    """
    Generic function to call the OpenAI-compatible API with retry logic.
    - Handles Timeouts and 429 Rate Limit errors with exponential backoff.
    """
    print(f"\nSending {tool_name} request to AI...")
    log_to_file(f"Initiating API Call (Tool: {tool_name})")

    model_config = config.get("selected_model_config")
    if not model_config:
        final_model_key = config.get('final_model_key', 'N/A')
        print(f"Error: Selected model configuration ('{final_model_key}') not found. Cannot call API.")
        log_to_file(f"API Call Error: selected_model_config missing for key '{final_model_key}'.")
        return None, None

    api_key = model_config.get("api_key")
    api_endpoint = model_config.get("api_endpoint")
    if not api_key or not api_endpoint:
        final_model_key = config.get('final_model_key', 'N/A')
        print(f"Error: 'api_key' or 'api_endpoint' missing in config for '{final_model_key}'.")
        log_to_file(f"API Call Error: api_key or api_endpoint missing for model key '{final_model_key}'.")
        return None, None

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    # Get model name - support both 'model' and 'model_name' fields
    model_name = model_config.get("model") or model_config.get("model_name")
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Dynamically add optional parameters from config
    for param in ["temperature", "max_tokens", "top_p"]:
        if param in model_config and model_config[param] is not None:
            # Ensure correct type, e.g., float for temp, int for tokens
            try:
                if param == "temperature" or param == "top_p":
                    payload[param] = float(model_config[param])
                elif param == "max_tokens":
                    payload[param] = int(model_config[param])
            except (ValueError, TypeError):
                 print(f"Warning: Could not convert '{param}' to the correct type. Using default.")
                 log_to_file(f"Config Warning: Could not convert '{param}' value '{model_config[param]}'.")


    if not payload.get("model"):
        print(f"Error: 'model' key is missing in the final payload for config '{config.get('DEFAULT_MODEL_CONFIG')}'.")
        log_to_file("API Call Error: 'model' key missing in payload.")
        return None, None

    log_to_file(f"API Call Details:\nEndpoint: {api_endpoint}\nPayload: {json.dumps(payload, indent=2)}")
    full_api_url = api_endpoint.rstrip('/') + "/chat/completions"

    for attempt in range(retries + 1):
        try:
            response = requests.post(full_api_url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()

            result = response.json()
            log_to_file(f"Raw API Response (Attempt {attempt + 1}):\n{json.dumps(result, indent=2)}")

            if not result.get("choices") or not result["choices"][0].get("message") or not result["choices"][0]["message"].get("content"):
                raise ValueError("Invalid response structure received from API.")

            print(f"{tool_name} response received.")
            message_content = result["choices"][0]["message"]["content"]
            cleaned_message = clean_thinking_tags(message_content)
            return message_content, cleaned_message

        except requests.exceptions.Timeout:
            error_msg = f"API call timed out after {timeout} seconds (Attempt {attempt + 1}/{retries + 1})."
            print(f"\n{tool_name} request failed (Timeout).")
            log_to_file(error_msg)
            if attempt >= retries:
                return None, None  # Final attempt failed

        except requests.exceptions.HTTPError as e:
            error_msg = f"API call failed with HTTP {e.response.status_code} (Attempt {attempt + 1}/{retries + 1}): {e}"
            print(f"\n{tool_name} request failed ({e.response.status_code}).")
            log_to_file(error_msg)
            if e.response.status_code != 429 or attempt >= retries:
                return None, None  # Fail on non-429 errors or if retries are exhausted

        except (requests.exceptions.RequestException, ValueError, KeyError, IndexError) as e:
            error_msg = f"An error occurred during API call or response parsing (Attempt {attempt + 1}/{retries + 1}): {e}"
            print(f"\n{tool_name} request failed.")
            log_to_file(f"{error_msg}\nRaw Response (if available):\n{locals().get('response', 'N/A')}")
            if attempt >= retries:
                return None, None  # Final attempt failed

        # If we are going to retry, calculate wait time and log it
        if attempt < retries:
            wait_time = base_wait_time * (2 ** attempt) + random.uniform(0, 1) # Exponential backoff with jitter
            print(f"Waiting for {wait_time:.2f} seconds before retrying...")
            log_to_file(f"Retrying after {wait_time:.2f} seconds.")
            time.sleep(wait_time)

    return None, None # Should be unreachable, but as a fallback