import requests
import json
import time
import os
import random # Used for retry delay jitter

from .utils import log_to_file, clean_thinking_tags # Import necessary functions from utils

def call_ai_api(prompt, config, tool_name="General", timeout=300):
    """Generic function to call the OpenAI-compatible API."""
    print(f"\nSending {tool_name} request to AI...")
    log_to_file(f"Initiating API Call (Tool: {tool_name})")

    # Get the selected model config from the main config object passed into the function
    model_config = config.get("selected_model_config")
    if not model_config:
        # This should ideally not happen due to checks in main(), but handle defensively
        final_model_key = config.get('final_model_key', 'N/A') # Get the key determined in main() for error message
        print(f"Error: Selected model configuration ('{final_model_key}') not found in loaded config passed to call_ai_api. Cannot call API.")
        log_to_file(f"API Call Error: selected_model_config missing for key '{final_model_key}'.")
        return None, None

    # Now get API details from the fetched model_config
    api_key = model_config.get("api_key")
    api_endpoint = model_config.get("api_endpoint")

    if not api_key or not api_endpoint:
        # Use the final_model_key stored in config for the error message
        final_model_key = config.get('final_model_key', 'N/A') # Get the key determined in main()
        print(f"Error: 'api_key' or 'api_endpoint' missing in the selected model configuration ('{final_model_key}') within ai_models.yml")
        log_to_file(f"API Call Error: api_key or api_endpoint missing for model key '{final_model_key}' in its YAML definition.")
        return None, None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # Build payload using parameters from the selected model config
    payload = {
        "model": model_config.get("model"), # Required, validated in load_config
        "messages": [{"role": "user", "content": prompt}],
        # Include other parameters from YAML if they exist
    }
    if "temperature" in model_config:
        payload["temperature"] = float(model_config["temperature"]) # Ensure float
    if "max_tokens" in model_config:
        payload["max_tokens"] = int(model_config["max_tokens"]) # Ensure int
    if "top_p" in model_config:
         payload["top_p"] = float(model_config["top_p"]) # Ensure float
    # Add other potential parameters here (e.g., top_k, stop sequences) if defined in YAML

    # Ensure essential 'model' key exists
    if not payload.get("model"):
         print(f"Error: 'model' key is missing in the final payload construction for config '{config.get('DEFAULT_MODEL_CONFIG')}'.")
         log_to_file("API Call Error: 'model' key missing in payload.")
         return None, None

    log_to_file(f"API Call Details:\nEndpoint: {api_endpoint}\nPayload: {json.dumps(payload, indent=2)}")

    try:
        full_api_url = api_endpoint.rstrip('/') + "/chat/completions"
        response = requests.post(full_api_url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)

        result = response.json()
        log_to_file(f"Raw API Response:\n{json.dumps(result, indent=2)}")

        # Robust content extraction
        if not result.get("choices"):
            raise ValueError("No 'choices' field in API response.")
        if not result["choices"][0].get("message"):
            raise ValueError("No 'message' field in the first choice.")

        message_content = result["choices"][0]["message"].get("content")
        if not message_content:
            raise ValueError("Empty 'content' in the message.")

        print(f"{tool_name} response received.")
        cleaned_message = clean_thinking_tags(message_content)
        # Return raw (for logging) and cleaned (for use)
        return message_content, cleaned_message

    except requests.exceptions.Timeout:
        error_msg = f"Error calling AI API: Timeout after {timeout} seconds."
        print(f"\n{tool_name} request failed (Timeout).")
        log_to_file(error_msg)
        return None, None
    except requests.exceptions.HTTPError as e:
        error_msg = f"Error calling AI API (HTTP {e.response.status_code}): {e}"
        print(f"\n{tool_name} request failed ({e.response.status_code}).")
        log_to_file(error_msg)
        # --- Rate Limit Handling (429) ---
        if e.response.status_code == 429:
            wait_time = 61
            print(f"Rate limit likely hit (429). Waiting for {wait_time} seconds before retrying once...")
            log_to_file(f"Rate limit hit (429). Waiting {wait_time}s and retrying.")
            time.sleep(wait_time)
            print(f"Retrying {tool_name} request...")
            try:
                # Retry the request
                response = requests.post(full_api_url, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status() # Check status of the retry

                result = response.json()
                log_to_file(f"Raw API Response (Retry Attempt):\n{json.dumps(result, indent=2)}")

                # Re-check response structure after retry
                if not result.get("choices"): raise ValueError("No 'choices' field in API response (Retry).")
                if not result["choices"][0].get("message"): raise ValueError("No 'message' field in the first choice (Retry).")
                message_content = result["choices"][0]["message"].get("content")
                if not message_content: raise ValueError("Empty 'content' in the message (Retry).")

                print(f"{tool_name} response received (after retry).")
                cleaned_message = clean_thinking_tags(message_content)
                return message_content, cleaned_message # Success after retry

            except requests.exceptions.RequestException as retry_e:
                error_msg_retry = f"Error calling AI API on retry: {retry_e}"
                print(f"\n{tool_name} request failed on retry.")
                log_to_file(error_msg_retry)
                return None, None # Failed on retry
            except (ValueError, KeyError, IndexError) as retry_parse_e:
                error_msg_retry = f"Error parsing AI API response on retry: {retry_parse_e}"
                print(f"\n{tool_name} response parsing failed on retry.")
                log_to_file(f"{error_msg_retry}\nRaw Response (Retry, if available):\n{result if 'result' in locals() else 'N/A'}")
                return None, None # Failed parsing on retry
            except Exception as retry_fatal_e:
                 error_msg_retry = f"An unexpected error occurred during AI API call retry: {retry_fatal_e}"
                 print(f"\n{tool_name} request failed unexpectedly on retry.")
                 log_to_file(error_msg_retry)
                 return None, None # Failed unexpectedly on retry
        else:
            # If it was a different HTTP error (not 429), fail immediately
            return None, None
    except requests.exceptions.RequestException as e: # Catch other request errors (connection, etc.)
        error_msg = f"Error calling AI API: {e}"
        print(f"\n{tool_name} request failed.")
        log_to_file(error_msg)
        return None, None
    except (ValueError, KeyError, IndexError) as e:
        error_msg = f"Error parsing AI API response: {e}"
        print(f"\n{tool_name} response parsing failed.")
        log_to_file(f"{error_msg}\nRaw Response (if available):\n{result if 'result' in locals() else 'N/A'}")
        return None, None
    except Exception as e:
        error_msg = f"An unexpected error occurred during AI API call: {e}"
        print(f"\n{tool_name} request failed (Unexpected).")
        log_to_file(error_msg)
        return None, None