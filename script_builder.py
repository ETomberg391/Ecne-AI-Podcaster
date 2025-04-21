import os
import datetime
import json
import re
import requests
import time
import random
import argparse
import yaml
import urllib.parse
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from newspaper import Article, ArticleException # Using newspaper4k for better web scraping
import PyPDF2 # Renamed from pypdf - assuming PyPDF2 is intended or needs update
import docx
# Removed PRAW import, adding Selenium imports
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# --- Constants & Configuration ---

# User agents for requests/scraping
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
]

# Global variable for archive directory (set in main)
run_archive_dir = None
SCRIPT_DIR = os.path.dirname(__file__) # Get the directory the script is in
LLM_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "settings/llm_settings")) # Define LLM_DIR

# --- Utility Functions ---

def log_to_file(content):
    """Helper to write detailed logs to the run-specific archive directory."""
    global run_archive_dir
    if run_archive_dir:
        log_file = os.path.join(run_archive_dir, f"ai_podcast_run_{datetime.datetime.now().strftime('%Y%m%d')}.log")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"\n[{datetime.datetime.now().isoformat()}] {content}\n")
        except IOError as e:
            print(f"Warning: Could not write to log file {log_file}: {e}")
            # Silently fail if we can't write logs after warning

def load_config():
    """Loads configuration from .env file."""
    load_dotenv()
    config = {
        # API endpoint and key are now loaded from ai_models.yml based on selection
        "google_api_key": os.getenv("GOOGLE_API_KEY"),
        "google_cse_id": os.getenv("GOOGLE_CSE_ID"),
        "brave_api_key": os.getenv("BRAVE_API_KEY"),
        # Reddit keys are loaded but unused in current scraping logic
        "reddit_client_id": os.getenv("REDDIT_CLIENT_ID"),
        "reddit_client_secret": os.getenv("REDDIT_CLIENT_SECRET"),
        "reddit_user_agent": os.getenv("REDDIT_USER_AGENT"),
    }

    # --- Load Model Configurations ---
    models_config_path = os.path.join(LLM_DIR, 'ai_models.yml')
    try:
        with open(models_config_path, 'r', encoding='utf-8') as f:
            models_config = yaml.safe_load(f)
        if not models_config or not isinstance(models_config, dict):
             raise ValueError("ai_models.yml is empty or not a valid dictionary.")
        print(f"Loaded model configurations from {models_config_path}")
    except FileNotFoundError:
        print(f"Error: Model configuration file not found at {models_config_path}")
        exit(1)
    except (yaml.YAMLError, ValueError) as e:
        print(f"Error parsing model configuration file {models_config_path}: {e}")
        exit(1)

    # NOTE: Model selection logic moved to main() after args parsing
    # --- End Model Configuration Loading ---
    # Basic validation
    # Check search APIs
    google_ok = config.get("google_api_key") and config.get("google_cse_id")
    brave_ok = config.get("brave_api_key")
    if not google_ok and not brave_ok:
         print("Warning: Neither Google (API Key + CSE ID) nor Brave API Key are set. Web search will fail.")
    # Check Reddit API creds
    reddit_ok = all(config.get(k) for k in ["reddit_client_id", "reddit_client_secret", "reddit_user_agent"])
    if not reddit_ok:
        print("Warning: Reddit credentials (client_id, client_secret, user_agent) missing in .env. Reddit scraping via PRAW will fail.")

    print("Configuration loaded.")
    # Return both basic config and the loaded models dictionary
    return config, models_config

def load_character_profile(filepath):
    """Loads character profile from a YAML file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            profile = yaml.safe_load(f)
            # Ensure podcast name is loaded if present
            if 'podcast_name' not in profile:
                 print(f"Warning: 'podcast_name' not found in profile {filepath}. Using default.")
                 profile.setdefault('podcast_name', 'Podcast') # Default if missing
            print(f"Loaded character profile from {filepath}")
            return profile
    except FileNotFoundError:
        print(f"Error: Character profile file not found at {filepath}")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {filepath}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred loading {filepath}: {e}")
        return None

def clean_thinking_tags(text):
    """Recursively remove all content within <think>...</think> tags."""
    if text is None: return ""
    prev_text = ""
    current_text = str(text) # Ensure it's a string
    # Keep cleaning until no more changes are made (handles nested tags)
    while prev_text != current_text:
        prev_text = current_text
        current_text = re.sub(r'<think>.*?</think>', '', prev_text, flags=re.IGNORECASE | re.DOTALL)
    return current_text.strip()

def parse_ai_tool_response(response_text, tool_tag):
    """
    Parses content within the *last* occurrence of specific <toolTag>...</toolTag> markers
    after cleaning thinking tags.
    """
    cleaned_text = clean_thinking_tags(response_text)
    if not cleaned_text: return ""

    # Find the last opening tag (case-insensitive)
    open_tag = f'<{tool_tag}>'
    close_tag = f'</{tool_tag}>'
    last_open_tag_index = cleaned_text.lower().rfind(open_tag.lower()) # Case-insensitive find

    if last_open_tag_index != -1:
        # Find the first closing tag *after* the last opening tag (case-insensitive)
        # Search starting from the position after the last open tag
        search_start_index = last_open_tag_index + len(open_tag)
        first_close_tag_index_after_last_open = cleaned_text.lower().find(close_tag.lower(), search_start_index) # Case-insensitive find

        if first_close_tag_index_after_last_open != -1:
            # Extract content between the tags
            start_content_index = last_open_tag_index + len(open_tag)
            content = cleaned_text[start_content_index:first_close_tag_index_after_last_open]
            return content.strip()
        else:
            # Found opening tag but no corresponding closing tag afterwards
            log_msg = f"Warning: Found last '<{tool_tag}>' but no subsequent '</{tool_tag}>'. Returning full cleaned response."
            print(f"\n{log_msg}")
            log_to_file(f"{log_msg}\nResponse was:\n{cleaned_text}")
            return cleaned_text # Fallback
    else:
        # No opening tag found at all
        log_msg = f"Warning: Tool tag '<{tool_tag}>' not found in AI response. Returning full cleaned response."
        print(f"\n{log_msg}")
        log_to_file(f"{log_msg}\nResponse was:\n{cleaned_text}")
        return cleaned_text # Fallback

# --- AI Interaction ---

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

# --- Argument Parsing ---

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Generate an AI podcast episode.")

    # --- Load model keys dynamically for choices ---
    available_model_keys = []
    models_config_path = os.path.join(LLM_DIR, 'ai_models.yml')

    try:
        with open(models_config_path, 'r', encoding='utf-8') as f:
            models_config = yaml.safe_load(f)
        if models_config and isinstance(models_config, dict):
            available_model_keys = list(models_config.keys())
        else:
            print(f"Warning: Could not load valid model keys from {models_config_path}. --llm-model argument might fail.")
    except Exception as e:
        print(f"Warning: Error loading {models_config_path} for arg parsing: {e}. --llm-model argument might fail.")
    # --- End model key loading ---

    # --- Define Arguments ---
    # Core
    # Made keywords not required, will validate later based on --no-search
    parser.add_argument("--keywords", type=str, default=None, help="Comma-separated keywords/phrases for searching (required unless --no-search is used).")
    parser.add_argument("--topic", type=str, required=True, help="The main topic phrase for the podcast episode.")
    # AI Model Selection
    parser.add_argument("--llm-model", type=str, default=None, choices=available_model_keys if available_model_keys else None,
                        help="Specify the LLM configuration key from ai_models.yml to use (overrides .env setting).")
    # Search & Scraping
    parser.add_argument("--api", choices=['google', 'brave'], default='google', help="Preferred search API ('google' or 'brave').")
    parser.add_argument("--from_date", type=str, default=None, help="Start date for search (YYYY-MM-DD).")
    parser.add_argument("--to_date", type=str, default=None, help="End date for search (YYYY-MM-DD).")
    parser.add_argument("--max-web-results", type=int, default=3, help="Max results per website source domain.")
    parser.add_argument("--max-reddit-results", type=int, default=5, help="Max *posts* to scrape per subreddit source.")
    parser.add_argument("--max-reddit-comments", type=int, default=5, help="Max *comments* to scrape per Reddit post.")
    parser.add_argument("--per-keyword-results", type=int, default=None, help="Web results per keyword (defaults to max-web-results).")
    parser.add_argument("--combine-keywords", action="store_true", help="Treat keywords as one search query (legacy).")
    # Output & Content
    parser.add_argument("--report", action="store_true", help="Generate a written report in addition to the script.")
    parser.add_argument("--score-threshold", type=int, default=5, help="Minimum summary score (0-10) to include in script.")
    parser.add_argument("--guidance", type=str, default=None, help="Additional guidance/instructions string for the LLM prompts.")
    parser.add_argument("--direct-articles", type=str, default=None, help="Path to a text file containing a list of article URLs (one per line) to scrape directly.")
    parser.add_argument("--no-search", action="store_true", help="Skip AI source discovery and web search APIs. Requires --direct-articles to be set.")
    # parser.add_argument("--sources", type=str, default=None, help="Comma-separated list of sources to use instead of AI discovery.")
    parser.add_argument("--reference-docs", type=str, default=None, help="Comma-separated paths to text files containing reference information.")
    parser.add_argument("--reference-docs-summarize", action="store_true", help="Summarize and score reference docs before including them.")
    parser.add_argument("--reference-docs-folder", type=str, default=None, help="Path to a folder containing reference documents (txt, pdf, docx).")

    args = parser.parse_args()

    # Set default for per_keyword_results
    if args.per_keyword_results is None:
        args.per_keyword_results = args.max_web_results

    # Process keywords only if provided
    search_queries = [] # Initialize default
    if args.keywords:
        if args.combine_keywords:
            raw_keywords = [k.strip() for k in args.keywords.split(',') if k.strip()]
            if not raw_keywords: raise ValueError("Please provide at least one keyword if using --keywords.")
            search_queries = [" ".join(raw_keywords)]
            print("Keywords combined into a single search query.")
        else:
            search_queries = [k.strip() for k in args.keywords.split(',') if k.strip()]
            if not search_queries: raise ValueError("Please provide at least one keyword/phrase if using --keywords.")
            print(f"Processing {len(search_queries)} separate search queries.")
    elif not args.no_search: # Keywords are required if we ARE doing a search
         parser.error("--keywords is required unless --no-search is specified.")

    # Validate dates
    def validate_date(date_str):
        if date_str is None: return None
        try:
            datetime.datetime.strptime(date_str, '%Y-%m-%d')
            return date_str
        except ValueError:
            raise ValueError(f"Invalid date format '{date_str}'. Use YYYY-MM-DD.")

    args.from_date = validate_date(args.from_date)
    args.to_date = validate_date(args.to_date)

    args.search_queries = search_queries # Store the processed list (or empty list) back into args
    print(f"Args: {vars(args)}")
    print(f"Parsed Args: {vars(args)}") # Keep print statement

    # Validation: --no-search requires --direct-articles OR reference docs/folder
    # Modified this validation slightly: If --no-search is used, *some* form of input context is needed.
    if args.no_search and not args.direct_articles and not args.reference_docs and not args.reference_docs_folder:
        parser.error("--no-search requires at least one of --direct-articles, --reference-docs, or --reference-docs-folder to be specified.")

    # Validation: Keywords are required if search is active
    if not args.no_search and not args.keywords:
         # This check is now done during keyword processing above, but double-checking here is safe.
         # parser.error("--keywords is required unless --no-search is specified.")
         # Re-checking the logic, the check during processing is sufficient. Removing redundant check here.
         pass # Validation moved to keyword processing block

    return args

# --- Research Phase ---

def discover_sources(keywords_list, config):
    """Uses AI to discover relevant websites and subreddits."""
    print("\nDiscovering sources via AI...")
    # Use the first keyword/phrase for simplicity, or combine them
    discovery_keyword_str = " | ".join(keywords_list)
    print(f"Using keywords for discovery: '{discovery_keyword_str}'")

    prompt = (
        f"Based on the keywords '{discovery_keyword_str}', suggest relevant information sources. "
        f"Include specific websites (news sites, reputable blogs, official project sites) and relevant subreddits. "
        f"Prioritize sources known for reliable, detailed information on this topic.\n"
        f"Format your response strictly within <toolWebsites> tags, listing each source URL or subreddit name (e.g., 'r/technology' or 'techcrunch.com') on a new line.\n"
        f"Example:\n<toolWebsites>\ntechcrunch.com\nwired.com\nexampleblog.net/relevant-section\nr/artificial\nr/machinelearning\n</toolWebsites>"
    )

    raw_response, cleaned_response = call_ai_api(prompt, config, tool_name="SourceDiscovery")

    if not cleaned_response:
        log_to_file("Error: No response received from AI API for source discovery.")
        return []

    sources_str = parse_ai_tool_response(cleaned_response, "toolWebsites")

    if not sources_str or sources_str == cleaned_response: # Parsing failed or tag missing
        log_to_file("Error: Could not parse <toolWebsites> tag in source discovery response.")
        return []

    # Remove trailing parenthetical explanations before validation
    sources_list_raw = [line.strip() for line in sources_str.split('\n') if line.strip()]
    sources_list = []
    for line in sources_list_raw:
        # Remove ' (explanation...)' from the end of the line
        cleaned_line = re.sub(r'\s*\(.*\)\s*$', '', line).strip()
        if cleaned_line and ('.' in cleaned_line or cleaned_line.startswith('r/')): # Basic validation on cleaned line
            sources_list.append(cleaned_line)

    if not sources_list:
        log_to_file(f"Warning: No valid sources extracted after parsing.\nParsed content: {sources_str}")
        return []

    print(f"Discovered {len(sources_list)} potential sources.")
    # --- Add Source Validation ---
    validated_sources = []
    print("Validating sources...")
    for source in sources_list:
        is_valid = False
        print(f"  - Checking: {source}...", end="")
        try:
            if source.startswith('r/'): # Assume subreddit exists if AI suggested
                is_valid = True
                print(" OK (Subreddit)")
            else: # Check website accessibility
                # Prepend http:// if no scheme exists
                url_to_check = source if source.startswith(('http://', 'https://')) else f'http://{source}'
                # Use HEAD request for efficiency
                response = requests.head(url_to_check, headers={'User-Agent': random.choice(USER_AGENTS)}, timeout=10, allow_redirects=True)
                if response.status_code < 400: # OK or Redirect
                    is_valid = True
                    print(f" OK (Status: {response.status_code})")
                else:
                    print(f" Failed (Status: {response.status_code})")
        except requests.exceptions.RequestException as e:
             print(f" Failed (Error: {e})")
        except Exception as e:
            print(f" Failed (Unexpected Error: {e})")

        if is_valid:
            validated_sources.append(source)
        time.sleep(0.5) # Small delay between checks

    print(f"Validated {len(validated_sources)} sources: {validated_sources}")
    return validated_sources


# --- Search API Functions ---

def search_google_api(query, config, num_results, from_date=None, to_date=None):
    """Performs search using Google Custom Search API."""
    urls = []
    api_key = config.get("google_api_key")
    cse_id = config.get("google_cse_id")
    if not api_key or not cse_id:
        log_to_file("Google API search skipped: API Key or CSE ID missing.")
        return None # Indicate skipped/failed

    search_url = "https://www.googleapis.com/customsearch/v1"
    effective_query = query
    if from_date: effective_query += f" after:{from_date}"
    if to_date: effective_query += f" before:{to_date}"

    print(f"  - Searching Google API: '{effective_query}' (Num: {num_results})")
    log_to_file(f"Google API Search: Query='{effective_query}', Num={num_results}")

    params = {'key': api_key, 'cx': cse_id, 'q': effective_query, 'num': min(num_results, 10)} # Google max 10 per req

    try:
        response = requests.get(search_url, params=params, timeout=20)
        response.raise_for_status()
        search_data = response.json()

        if 'items' in search_data:
            urls = [item['link'] for item in search_data['items'] if 'link' in item]
            print(f"    - Google Found: {len(urls)} results.")
            log_to_file(f"Google API Success: Found {len(urls)} URLs.")
        else:
            print("    - Google Found: 0 results.")
            log_to_file("Google API Success: No items found in response.")

        # Check for quota error explicitly
        if 'error' in search_data and search_data['error'].get('code') == 429:
             print("    - !! Google API Quota limit likely reached !!")
             log_to_file("Google API Error: Quota limit reached (429 in response body).")
             return 'quota_error'
        return urls

    except requests.exceptions.HTTPError as e:
        print(f"    - Error calling Google API: {e}")
        log_to_file(f"Google API HTTP Error: {e}")
        if e.response.status_code == 429:
            print("    - !! Google API Quota limit likely reached (HTTP 429) !!")
            log_to_file("Google API Error: Quota limit reached (HTTP 429).")
            return 'quota_error'
        return None # General HTTP error
    except requests.exceptions.RequestException as e:
        print(f"    - Error calling Google API: {e}")
        log_to_file(f"Google API Request Error: {e}")
        return None
    except Exception as e:
        print(f"    - Unexpected error during Google API search: {e}")
        log_to_file(f"Google API Unexpected Error: {e}")
        return None
    finally:
        time.sleep(random.uniform(1, 2)) # Delay

def search_brave_api(query, config, num_results, from_date=None, to_date=None):
    """Performs search using Brave Search API."""
    urls = []
    api_key = config.get("brave_api_key")
    if not api_key:
        log_to_file("Brave API search skipped: API Key missing.")
        return None

    search_url = "https://api.search.brave.com/res/v1/web/search"
    headers = {"Accept": "application/json", "Accept-Encoding": "gzip", "X-Subscription-Token": api_key}
    effective_query = query
    freshness_param = None

    # Brave uses 'freshness=pd:YYYYMMDD,YYYYMMDD'
    if from_date:
        try:
            from_dt = datetime.datetime.strptime(from_date, '%Y-%m-%d')
            freshness_start = from_dt.strftime('%Y%m%d')
            freshness_end = ""
            if to_date:
                to_dt = datetime.datetime.strptime(to_date, '%Y-%m-%d')
                freshness_end = to_dt.strftime('%Y%m%d')
            freshness_param = f"pd:{freshness_start},{freshness_end}"
        except ValueError:
            print(f"  - Warning: Invalid date format for Brave freshness '{from_date}' or '{to_date}'. Skipping date filter.")
            log_to_file(f"Brave API Warning: Invalid date format '{from_date}'/'{to_date}' for freshness.")

    print(f"  - Searching Brave API: '{effective_query}' (Num: {num_results})")
    log_to_file(f"Brave API Search: Query='{effective_query}', Num={num_results}, Freshness='{freshness_param}'")

    params = {'q': effective_query, 'count': num_results}
    if freshness_param: params['freshness'] = freshness_param

    try:
        response = requests.get(search_url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        search_data = response.json()

        if 'web' in search_data and 'results' in search_data['web']:
            urls = [item['url'] for item in search_data['web']['results'] if 'url' in item]
            print(f"    - Brave Found: {len(urls)} results.")
            log_to_file(f"Brave API Success: Found {len(urls)} URLs.")
        else:
            print("    - Brave Found: 0 results.")
            log_to_file(f"Brave API Success: No web/results found in response. Structure: {search_data.keys()}")
        return urls

    except requests.exceptions.HTTPError as e:
        print(f"    - Error calling Brave API: {e}")
        log_to_file(f"Brave API HTTP Error: {e}")
        if e.response.status_code == 429:
             print("    - !! Brave API Quota limit likely reached (HTTP 429) !!")
             log_to_file("Brave API Error: Quota limit reached (HTTP 429).")
             return 'quota_error'
        return None
    except requests.exceptions.RequestException as e:
        print(f"    - Error calling Brave API: {e}")
        log_to_file(f"Brave API Request Error: {e}")
        return None
    except Exception as e:
        print(f"    - Unexpected error during Brave API search: {e}")
        log_to_file(f"Brave API Unexpected Error: {e}")
        return None
    finally:
        time.sleep(random.uniform(1, 2)) # Delay

# --- Content Scraping ---

def scrape_website_url(url):
    """Scrapes content from a single website URL using newspaper4k."""
    print(f"      - Scraping URL (Newspaper4k): {url}")
    log_to_file(f"Scraping website URL: {url}")
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        article = Article(url, request_headers=headers, fetch_images=False)
        article.download()
        # Handle potential download errors before parsing
        if article.download_state != 2: # 2 means success
             raise ArticleException(f"Download failed with state {article.download_state}")
        article.parse()

        title = article.title
        text = article.text
        publish_date = article.publish_date

        if text and len(text) > 150: # Basic quality check
            content = f"Source URL: {url}\n"
            if title: content += f"Title: {title}\n"
            if publish_date: content += f"Published: {publish_date.strftime('%Y-%m-%d') if publish_date else 'N/A'}\n"
            content += f"\nBody:\n{text}"
            print(f"        - Success: Scraped content ({len(text)} chars).")
            log_to_file(f"Website scrape success: {url} ({len(text)} chars)")
            return content.strip()
        elif text:
            print("        - Warning: Scraped text seems too short, skipping.")
            log_to_file(f"Website scrape warning (too short): {url} ({len(text)} chars)")
            return None
        else:
            print("        - Warning: Newspaper4k found no text.")
            log_to_file(f"Website scrape warning (no text): {url}")
            return None

    except ArticleException as e: # Assuming newspaper4k still uses ArticleException
        print(f"        - Error (Newspaper4k) scraping {url}: {e}")
        log_to_file(f"Website scrape ArticleException: {url} - {e}")
        return None
    except requests.exceptions.RequestException as e:
         print(f"        - Error (Request) fetching {url}: {e}")
         log_to_file(f"Website scrape RequestException: {url} - {e}")
         return None
    except Exception as e:
        print(f"        - Unexpected error scraping {url}: {e}")
        log_to_file(f"Website scrape Unexpected Error: {url} - {e}")
        return None
    finally:
        time.sleep(random.uniform(1.5, 3)) # Delay between website scrapes

# Removed scrape_reddit_source function (replaced by Selenium logic below)

def scrape_content(sources_or_urls, args, config): # Rename input for clarity
    """
    Scrapes content from discovered/provided sources or direct URLs.
    If args.no_search is True, sources_or_urls is expected to be a list of URLs.
    Otherwise, it can be a mix of source identifiers (domains, subreddits) and direct URLs.
    """
    print(f"\nStarting content scraping phase...")
    scraped_texts = []
    seen_urls_global = set() # Avoid scraping the exact same URL multiple times

    # --- Iterate Through Sources/URLs ---
    for i, item in enumerate(sources_or_urls, 1): # Use item and start from 1
        print(f"\nProcessing item {i}/{len(sources_or_urls)}: {item}")
        source_texts_count = 0 # Reset count for each item/source processed
        # source_scrape_limit will be set based on item type below

        # --- Determine Item Type ---
        # Treat reddit links separately even if they start with http
        is_reddit_source = item.startswith('r/') or 'reddit.com/r/' in item
        # Check for standard web URL, excluding reddit domains explicitly handled above
        is_direct_url = item.startswith(('http://', 'https://')) and not is_reddit_source
        # Assumed domain/source if not URL/Reddit
        is_website_source = not is_direct_url and not is_reddit_source

        # --- Start of main try block for processing an item ---
        try:
            # --- Handle Direct URLs ---
            if is_direct_url:
                print(f"  - Processing as Direct URL: {item}")
                log_to_file(f"Processing Direct URL: {item}")
                if item in seen_urls_global:
                    print(f"      - Skipping already scraped URL (globally): {item}")
                    continue # Skip to next item in sources_or_urls

                scraped_text = scrape_website_url(item) # Directly scrape the URL
                if scraped_text:
                    scraped_texts.append(scraped_text)
                    seen_urls_global.add(item) # Mark as scraped globally
                    source_texts_count += 1 # Increment count for this item
                # scrape_website_url handles its own logging/printing

            # --- Handle Reddit Sources (Selenium) ---
            elif is_reddit_source:
                if args.no_search:
                     print(f"  - Warning: Skipping Reddit source '{item}' because --no-search is active.")
                     log_to_file(f"Scraping Warning: Skipped Reddit source {item} due to --no-search.")
                     continue # Skip to next item

                source_scrape_limit = args.max_reddit_results
                subreddit_name = item.replace('r/', '').split('/')[0] # Extract name from item
                if not subreddit_name:
                    print(f"  - Warning: Could not extract subreddit name from '{item}'. Skipping.")
                    log_to_file(f"Scraping Warning: Invalid subreddit source format '{item}'")
                    continue # Skip to next item

                # --- Start Selenium Logic for Reddit ---
                print(f"  - Processing Reddit source '{subreddit_name}' using Selenium/old.reddit.com...")
                log_to_file(f"Initiating Selenium scrape for r/{subreddit_name}")
                driver = None
                all_post_links_for_subreddit = set()
                reddit_texts = [] # Store texts scraped from this source

                # --- Start try-finally for Selenium driver ---
                try:
                    options = webdriver.ChromeOptions()
                    options.add_argument('--headless'); options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
                    options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
                    # TODO: Make chromedriver path configurable if needed via .env or args
                    driver = webdriver.Chrome(options=options)
                    wait = WebDriverWait(driver, 20) # Consider making timeout configurable
                    print("    - Selenium WebDriver initialized.")

                    # --- Perform Search for Each Keyword Query ---
                    for query_idx, search_query in enumerate(args.search_queries):
                        print(f"      - Searching subreddit '{subreddit_name}' for query {query_idx+1}/{len(args.search_queries)}: '{search_query}'")
                        try:
                            encoded_query = urllib.parse.quote_plus(search_query)
                            # Using old.reddit.com for potentially simpler structure
                            search_url = f"https://old.reddit.com/r/{subreddit_name}/search?q={encoded_query}&restrict_sr=on&sort=relevance&t=all"
                            print(f"        - Navigating to search URL: {search_url}")
                            driver.get(search_url)
                            time.sleep(random.uniform(2, 4)) # Allow page to load

                            print("        - Waiting for search results...")
                            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.search-result-link, div.search-result"))) # General result container
                            link_elements = driver.find_elements(By.CSS_SELECTOR, "a.search-title") # Titles usually link to posts
                            print(f"        - Found {len(link_elements)} potential result links for this query.")

                            count = 0
                            for link_element in link_elements:
                                href = link_element.get_attribute('href')
                                # Ensure it's a comments link and not already seen
                                if href and '/comments/' in href and href not in all_post_links_for_subreddit:
                                     all_post_links_for_subreddit.add(href)
                                     count += 1
                            print(f"        - Added {count} new unique post links.")

                        except TimeoutException:
                            print(f"        - Timeout waiting for search results for query: '{search_query}'")
                            log_to_file(f"Selenium Timeout waiting for search results: r/{subreddit_name}, Query: '{search_query}'")
                        except Exception as search_e:
                            print(f"        - Error extracting search results for query '{search_query}': {search_e}")
                            log_to_file(f"Selenium Error extracting search results: r/{subreddit_name}, Query: '{search_query}': {search_e}")

                        time.sleep(random.uniform(1, 2)) # Delay between searches

                    # --- Scrape Collected Post Links ---
                    unique_post_links = list(all_post_links_for_subreddit)
                    print(f"    - Total unique post links found across all queries for '{subreddit_name}': {len(unique_post_links)}")
                    links_to_scrape = unique_post_links[:source_scrape_limit] # Apply limit on *posts* to scrape
                    print(f"    - Scraping top {len(links_to_scrape)} posts based on --max-reddit-results={source_scrape_limit}")

                    if not links_to_scrape:
                        print("    - No post links found to scrape for this subreddit.")

                    for post_url in links_to_scrape:
                        if post_url in seen_urls_global:
                            print(f"      - Skipping already scraped URL (globally): {post_url}")
                            continue
                        # Check limit *for this source* again (safe redundancy)
                        if source_texts_count >= source_scrape_limit:
                            print(f"      - Reached post scrape limit ({source_scrape_limit}) for subreddit {subreddit_name}.")
                            break # Stop scraping more posts for this subreddit

                        print(f"      - Navigating to post: {post_url}")
                        try:
                            driver.get(post_url)
                            time.sleep(random.uniform(2, 4)) # Allow comments to load

                            post_title = "N/A"; post_body = ""; comment_texts = []
                            # Extract Title (using old.reddit selector)
                            try:
                                title_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "p.title a.title")))
                                post_title = title_element.text.strip()
                            except (TimeoutException, NoSuchElementException): print("        - Warning: Could not find post title.")

                            # Extract Body (using old.reddit selector)
                            try:
                                body_elements = driver.find_elements(By.CSS_SELECTOR, "div.expando div.md")
                                if body_elements: post_body = body_elements[0].text.strip()
                            except NoSuchElementException: pass
                            except Exception as body_e: print(f"        - Warning: Error extracting post body: {body_e}")

                            # Extract Comments (using old.reddit selector)
                            try:
                                comment_elements = driver.find_elements(By.CSS_SELECTOR, "div.commentarea .comment .md p")
                                print(f"        - Found {len(comment_elements)} comment paragraphs. Scraping top {args.max_reddit_comments}.")
                                for comment_element in comment_elements[:args.max_reddit_comments]: # Use args limit here
                                    comment_text = comment_element.text.strip()
                                    if comment_text: # Avoid empty paragraphs
                                        comment_texts.append(comment_text)
                            except NoSuchElementException: pass
                            except Exception as comment_e: print(f"        - Warning: Error extracting comments: {comment_e}")

                            # Combine content
                            # Extract permalink from post_url for logging/reference
                            permalink = post_url # Use post_url as permalink for old reddit
                            full_content = f"Source: Reddit (r/{subreddit_name})\nPermalink: {permalink}\nTitle: {post_title}\n\nBody:\n{post_body}\n\nComments:\n" + "\n---\n".join(comment_texts)
                            content_length = len(full_content)
                            min_length = 150 # Minimum chars to be considered valid content

                            if content_length > min_length:
                                reddit_texts.append(full_content.strip()) # Add to this source's list
                                seen_urls_global.add(post_url) # Mark as scraped globally
                                source_texts_count += 1 # Increment count for this source
                                print(f"        - Success: Scraped content from post ({content_length} chars).")
                                log_to_file(f"Selenium scrape success: {post_url} ({content_length} chars)")
                            else:
                                print(f"        - Warning: Scraped content ({content_length} chars) seems too short (min {min_length}). Skipping post.")
                                log_to_file(f"Selenium scrape warning (too short): {post_url} ({content_length} chars)")

                        except TimeoutException:
                            print(f"      - Timeout loading post page: {post_url}")
                            log_to_file(f"Selenium Timeout loading post page: {post_url}")
                        except Exception as post_e:
                            print(f"      - Error processing post page {post_url}: {post_e}")
                            log_to_file(f"Selenium Error processing post page {post_url}: {post_e}")
                        finally:
                             time.sleep(random.uniform(1.5, 3)) # Delay between posts

                # --- End Selenium Logic try ---
                except Exception as selenium_e:
                    print(f"    - An error occurred during Selenium processing for {item}: {selenium_e}") # Use item
                    log_to_file(f"Selenium Error processing source {item}: {selenium_e}") # Use item
                finally:
                    # --- Start Selenium finally block ---
                    if driver:
                        print("    - Quitting Selenium WebDriver.")
                        driver.quit()
                    # --- End Selenium finally block ---

                scraped_texts.extend(reddit_texts) # Add texts from this source to the main list
                # Note: source_texts_count was incremented inside the post loop above

            # --- Handle Website Sources (Search API + Newspaper4k) ---
            elif is_website_source:
                if args.no_search:
                    print(f"  - Warning: Skipping website source '{item}' because --no-search is active.")
                    log_to_file(f"Scraping Warning: Skipped website source {item} due to --no-search.")
                    continue # Skip to next item

                source_scrape_limit = args.max_web_results
                domain = urllib.parse.urlparse(item).netloc or item # Extract domain from item
                print(f"  - Processing website source (will search within): {domain}")
                log_to_file(f"Processing website source: {domain} (Original: {item})") # Use item
                urls_to_scrape_for_domain = set()

                # Determine search targets and API call limits
                search_targets = args.search_queries if not args.combine_keywords else [args.search_queries[0]]
                results_limit_per_api_call = args.per_keyword_results if not args.combine_keywords else args.max_web_results

                # --- Search APIs for each target query ---
                for query_idx, search_query in enumerate(search_targets):
                    # Construct query for API (site: modifier)
                    current_query_for_api = f"site:{domain} {search_query}"
                    print(f"    - Searching web APIs for query {query_idx+1}/{len(search_targets)}: '{current_query_for_api}' (Limit: {results_limit_per_api_call})")

                    api_results = None
                    primary_api = args.api
                    fallback_api = 'brave' if primary_api == 'google' else 'google'

                    # Attempt Primary API
                    print(f"      - Attempting primary API: {primary_api}")
                    if primary_api == 'google':
                        api_results = search_google_api(current_query_for_api, config, results_limit_per_api_call, args.from_date, args.to_date)
                    else: # brave
                        api_results = search_brave_api(current_query_for_api, config, results_limit_per_api_call, args.from_date, args.to_date)

                    # Handle Primary API Failure/Quota
                    if api_results == 'quota_error':
                        print(f"      - Primary API '{primary_api}' quota limit hit.")
                        api_results = None # Reset to trigger fallback
                    elif api_results is None:
                         print(f"      - Primary API '{primary_api}' failed or returned no results.")

                    # Attempt Fallback API
                    if api_results is None:
                        print(f"      - Attempting fallback API: {fallback_api}")
                        if fallback_api == 'google':
                            api_results = search_google_api(current_query_for_api, config, results_limit_per_api_call, args.from_date, args.to_date)
                        else: # brave
                            api_results = search_brave_api(current_query_for_api, config, results_limit_per_api_call, args.from_date, args.to_date)

                        if api_results == 'quota_error':
                            print(f"      - Fallback API '{fallback_api}' also hit quota limit.")
                            api_results = None
                        elif api_results is None:
                             print(f"      - Fallback API '{fallback_api}' failed or returned no results.")

                    # Add successfully found URLs
                    if isinstance(api_results, list):
                        added_count = 0
                        for url in api_results:
                            if url not in urls_to_scrape_for_domain and url not in seen_urls_global:
                                urls_to_scrape_for_domain.add(url)
                                added_count += 1
                        print(f"      - Added {added_count} new unique URLs from this API search.")
                        log_to_file(f"API Search Success: Added {added_count} URLs for query '{current_query_for_api}'")
                    else:
                        print(f"      - No URLs obtained from APIs for this query.")
                        log_to_file(f"API Search Failed/Empty for query '{current_query_for_api}'")

                    time.sleep(random.uniform(1, 2)) # Delay between API calls for different queries

                # --- Scrape Content from Aggregated URLs for this Domain ---
                unique_urls_list = list(urls_to_scrape_for_domain)
                print(f"    - Total unique URLs found for domain '{domain}': {len(unique_urls_list)}")
                urls_to_process = unique_urls_list[:source_scrape_limit] # Apply overall limit
                print(f"    - Attempting to scrape top {len(urls_to_process)} URLs...")

                for url in urls_to_process:
                    if url in seen_urls_global:
                        print(f"      - Skipping already scraped URL (globally): {url}")
                        continue
                    if source_texts_count >= source_scrape_limit:
                         print(f"      - Reached scrape limit ({source_scrape_limit}) for web source {domain}.")
                         break # Stop scraping more URLs for this domain

                    scraped_text = scrape_website_url(url)
                    if scraped_text:
                        scraped_texts.append(scraped_text)
                        seen_urls_global.add(url) # Mark as scraped globally
                        source_texts_count += 1
                    # scrape_website_url handles its own logging/printing
            # --- End of Website Source Logic ---

            else: # This case should ideally not be reached if logic above is correct
                print(f"  - Warning: Could not determine type for item: {item}. Skipping.")
                log_to_file(f"Scraping Warning: Unknown item type: {item}")

        # --- End of main try block, start of except block ---
        except Exception as item_e: # Changed variable name
            print(f"Error processing item '{item}': {item_e}") # Use item
            log_to_file(f"Scraping Error: Unexpected error processing item '{item}': {item_e}") # Use item
        # --- End of except block ---

        # Log completion for the current item (URL, Reddit source, or Website source) - Indented inside the loop
        print(f"  - Finished processing item: {item}. Scraped {source_texts_count} piece(s) for this item.")

        # --- Delay Before Next Item --- - Indented inside the loop
        if i < len(sources_or_urls): # Check against total items
            delay = random.uniform(3, 6)
            print(f"--- Delaying for {delay:.2f} seconds before next item ---")
            time.sleep(delay)

    # --- End of Loop Through Items --- - Indented outside the loop
    print(f"\nFinished scraping. Total unique content pieces gathered: {len(scraped_texts)}")
    log_to_file(f"Scraping phase complete. Gathered {len(scraped_texts)} content pieces.")
    return scraped_texts
def summarize_content(scraped_texts, reference_docs, topic, config, args):
    """
    Uses AI to summarize scraped content and optionally reference documents,
    assigning a relevance score to each.
    """
    content_to_process = []
    # Add scraped texts with a type identifier
    for idx, text in enumerate(scraped_texts):
        content_to_process.append({"type": "scraped", "content": text, "source_index": idx + 1})

    # Add reference docs if summarization is requested
    if args.reference_docs_summarize and reference_docs:
        print(f"Including {len(reference_docs)} reference documents in summarization.")
        log_to_file(f"Including {len(reference_docs)} reference documents in summarization.")
        for doc in reference_docs:
             content_to_process.append({"type": "reference", "content": doc["content"], "path": doc["path"]})
    elif reference_docs:
         print(f"Skipping summarization for {len(reference_docs)} reference documents as --reference-docs-summarize is not set.")
         log_to_file(f"Skipping summarization for {len(reference_docs)} reference documents.")

    total_pieces = len(content_to_process)
    if total_pieces == 0:
        print("\nWarning: No content (scraped or reference for summarization) available to summarize.")
        log_to_file("Summarization Warning: No content found to process.")
        return [] # Return empty list if nothing to do

    print(f"\nSummarizing {total_pieces} content piece(s)...")
    log_to_file(f"Starting summarization for {total_pieces} piece(s). Topic: {topic}")
    summaries_with_scores = []
    successful_summaries = 0

    for i, item in enumerate(content_to_process, 1):
        text = item["content"]
        item_type = item["type"]
        item_source_id = item.get("path", f"Scraped_{item.get('source_index', i)}") # Use path for ref docs, index for scraped

        if len(text) < 100: # Increased minimum length
            print(f"\rSkipping summary for short text piece {i}/{total_pieces} ({item_source_id}).", end='', flush=True)
            log_to_file(f"Summary {i}/{total_pieces} ({item_source_id}) skipped (too short: {len(text)} chars).")
            continue

        # Show progress
        print(f"\rSummarizing & Scoring {i}/{total_pieces} ({item_type}) (Completed: {successful_summaries})", end='', flush=True)

        # Limit text size sent to AI if necessary (check API limits)
        max_summary_input_chars = 150000 # Example limit, adjust as needed
        truncated_text = text[:max_summary_input_chars]
        if len(text) > max_summary_input_chars:
            log_to_file(f"Warning: Summary {i} ({item_source_id}) input text truncated to {max_summary_input_chars} chars.")

        guidance_text = f"\n**Additional Guidance:** {args.guidance}\n" if args.guidance else ""
        prompt = (
            f"Please provide a concise yet comprehensive summary of the following text. Focus on the key information, main arguments, findings, and any specific data points (statistics, percentages, benchmark results, dates, names) relevant to the main topic.\n"
            f"**Main Topic:** {topic}{guidance_text}\n"
            f"**Text to Summarize:**\n---\n{truncated_text}\n---\n\n"
            f"**Instructions:**\n"
            f"1. Format your summary *only* within <toolScrapeSummary> tags.\n"
            f"2. After the summary tag, provide a relevance score (integer 0-10) indicating how relevant the *summary* is to the Main Topic ('{topic}') and adheres to any Additional Guidance provided. Enclose the score *only* in <summaryScore> tags.\n\n"
            f"**Example Response Structure:**\n"
            f"<toolScrapeSummary>This is a concise summary preserving key details like a 95% accuracy rate achieved in 2023 according to Dr. Smith.</toolScrapeSummary>\n"
            f"<summaryScore>8</summaryScore>"
        )

        raw_response, cleaned_response = call_ai_api(prompt, config, tool_name=f"Summary_{i}_{item_type}", timeout=3000) # Shorter timeout, added type

        summary = "Error: Summarization Failed"
        score = -1 # Default score
        summary_details = {"type": item_type, "source_id": item_source_id} # Store type and source id

        if cleaned_response:
            parsed_summary = parse_ai_tool_response(cleaned_response, "toolScrapeSummary")
            # Check if parsing returned the whole response (tag missing)
            if parsed_summary == cleaned_response and '<toolScrapeSummary>' not in cleaned_response:
                 log_to_file(f"Error: Summary {i} ({item_source_id}) parsing failed - <toolScrapeSummary> tag missing.")
                 summary = f"Error: Could not parse summary {i} ({item_source_id}) (<toolScrapeSummary> tag missing)"
            elif not parsed_summary:
                 log_to_file(f"Error: Summary {i} ({item_source_id}) parsing failed - No content found in <toolScrapeSummary> tag.")
                 summary = f"Error: Could not parse summary {i} ({item_source_id}) (empty tag)"
            else:
                 summary = parsed_summary # Use parsed summary

            # Extract score robustly
            score_match = re.search(r'<summaryScore>(\d{1,2})</summaryScore>', cleaned_response, re.IGNORECASE)
            if score_match:
                try:
                    parsed_score = int(score_match.group(1))
                    if 0 <= parsed_score <= 10:
                        score = parsed_score
                        successful_summaries += 1 # Count success only if score is valid
                    else:
                        log_to_file(f"Warning: Summary {i} ({item_source_id}) score '{parsed_score}' out of range (0-10). Using -1.")
                except ValueError:
                    log_to_file(f"Warning: Could not parse summary {i} ({item_source_id}) score '{score_match.group(1)}'. Using -1.")
            else:
                 log_to_file(f"Warning: Could not find/parse <summaryScore> tag for summary {i} ({item_source_id}). Using -1.")

        else: # API call itself failed
            log_to_file(f"Error: API call failed for Summary_{i} ({item_source_id})")
            summary = f"Error: Could not summarize text piece {i} ({item_source_id}) (API call failed)"

        # Add summary and score along with type and source identifier
        summary_details.update({'summary': summary, 'score': score})
        summaries_with_scores.append(summary_details)

        # Save the summary text to archive regardless of score validity
        if run_archive_dir:
            # Create a more descriptive filename
            safe_source_id = re.sub(r'[\\/*?:"<>|]', "_", str(item_source_id)) # Sanitize filename chars
            summary_filename = os.path.join(run_archive_dir, f"summary_{i}_{item_type}_{safe_source_id[:50]}.txt") # Truncate long paths
            try:
                with open(summary_filename, 'w', encoding='utf-8') as sf:
                    sf.write(f"Source: {item_source_id}\nType: {item_type}\nScore: {score}\n\n{summary}")
            except IOError as e:
                log_to_file(f"Warning: Could not save summary {i} ({item_source_id}) to file {summary_filename}: {e}")

    # Final status update
    print(f"\rSummarization & Scoring complete. Generated {successful_summaries}/{total_pieces} summaries successfully (with valid scores).")
    log_to_file(f"Summarization phase complete. Successful summaries (with score): {successful_summaries}/{total_pieces}")
    return summaries_with_scores


# --- Script Generation & Refinement ---

def format_script_generation_prompt(summaries_with_scores, reference_docs_content, topic, host_profile, guest_profile, args):
    """Formats the detailed prompt for the initial script generation AI call, including summaries and/or full reference docs."""

    # --- Process Summaries (Scraped + Reference if Summarized) ---
    score_threshold = args.score_threshold # Use the threshold from args
    valid_summaries = [s for s in summaries_with_scores if s['score'] >= 0 and not s['summary'].startswith("Error:")]
    print(f"\nFiltering {len(valid_summaries)} valid summaries with score >= {score_threshold}...")
    filtered_summaries = [s for s in valid_summaries if s['score'] >= score_threshold]
    num_summaries_used = 0
    combined_summaries_text = "No summaries met the score threshold or were generated."

    # Fallback if threshold is too high
    if not filtered_summaries and valid_summaries:
        print(f"Warning: No summaries met score threshold >= {score_threshold}. Using all valid summaries.")
        log_to_file(f"Script Gen Warning: No summaries >= {score_threshold}. Using all {len(valid_summaries)} valid summaries.")
        top_summaries = sorted(valid_summaries, key=lambda x: x['score'], reverse=True)
    elif filtered_summaries:
        top_summaries = sorted(filtered_summaries, key=lambda x: x['score'], reverse=True)
    else:
        top_summaries = [] # No valid summaries at all

    if top_summaries:
        num_summaries_used = len(top_summaries)
        print(f"Using {num_summaries_used} summaries for script generation.")
        log_to_file(f"Script Gen: Using {num_summaries_used} summaries (Threshold: {score_threshold}).")
        # Format summaries for the prompt, including source info
        combined_summaries_text = "\n\n".join([
             f"Summary {i+1} (Source: {s['source_id']}, Type: {s['type']}, Score: {s['score']}):\n{s['summary']}"
             for i, s in enumerate(top_summaries)
        ])
    else:
        print("Warning: No summaries will be included in the script generation prompt.")
        log_to_file("Script Gen Warning: No summaries included in prompt.")

    # --- Process Full Reference Documents (If Not Summarized) ---
    full_reference_docs_text = ""
    num_ref_docs_used = 0
    if reference_docs_content and not args.reference_docs_summarize:
        num_ref_docs_used = len(reference_docs_content)
        print(f"Including {num_ref_docs_used} full reference documents directly in the prompt.")
        log_to_file(f"Script Gen: Including {num_ref_docs_used} full reference documents.")
        full_reference_docs_text = "\n\n---\n\n".join([
            f"Reference Document (Path: {doc['path']}):\n{doc['content']}"
            for doc in reference_docs_content
        ])
        # Add a header for clarity in the prompt
        full_reference_docs_text = f"**Full Reference Documents (Use for context):**\n---\n{full_reference_docs_text}\n---"

    # Check if we have *any* content to generate from
    if num_summaries_used == 0 and num_ref_docs_used == 0:
         print("Error: No summaries met the threshold and no reference documents provided/processed. Cannot generate script.")
         log_to_file("Script Gen Error: No summaries or reference documents available for context.")
         return None, 0, 0 # Indicate error


    # Load podcast name from host profile
    podcast_name = host_profile.get('podcast_name', 'Podcast') # Default if missing

    # Prepare character profiles as strings
    host_details = yaml.dump(host_profile, default_flow_style=False, sort_keys=False)
    guest_details = yaml.dump(guest_profile, default_flow_style=False, sort_keys=False)

    # --- Construct the Prompt ---
    # (Using the detailed prompt from main.py, slightly adjusted)
    guidance_text = f"\n**Additional Guidance:** {args.guidance}\n" if args.guidance else ""
    prompt = (
        f"You are an AI scriptwriter for the podcast '{podcast_name}'. Your task is to create a natural, engaging podcast script with a '{host_profile.get('vibe', 'chill but informal')}' vibe about the specific topic: '{topic}'.{guidance_text}\n"
        f"**Characters:**\n\n"
        f"--- HOST PROFILE ---\n{host_details}\n--------------------\n\n"
        f"--- GUEST PROFILE ---\n{guest_details}\n---------------------\n\n"
        f"**Podcast Topic:** {topic}\n"
        f"{guidance_text}\n" # Add guidance here as well for clarity
        f"**Task:**\n"
        f"Generate a comprehensive and extended podcast script based *thoroughly* on the provided context (summaries and/or full reference documents), following these strict rules:\n"
        f"1. **Human-like & Extended Conversation:** Make the dialogue sound like a real, flowing, and in-depth conversation. Aim to extend the discussion naturally by exploring nuances within the provided context. Inject subtle emotions like curiosity (Host), enthusiasm (Guest), surprise, or thoughtfulness where appropriate based on the content. Avoid robotic question-answer cycles.\n"
        f"2. **Emotional Nuance:** Host should express genuine interest and occasionally react with phrases like 'Wow, that's really interesting!' or 'I never thought about it that way.' Guest should convey passion for the topic, perhaps expressing excitement about a breakthrough or thoughtful concern about implications.\n"
        f"3. **Comprehensive Analysis & Synthesis:** Analyze **ALL** provided summaries (prioritizing higher scores) AND any full reference documents exhaustively. Find connections, contrasts, related themes, and specific details (especially statistics or benchmarks). Integrate information from all sources (summaries and full documents) into a coherent discussion about the main '{topic}'. Don't just list facts; weave the information together.\n"
        f"4. **Coverage & Flow:** Cover the most relevant points (indicated by summary score or presence in reference docs) comprehensively. Create natural, smooth transitions between different topics or aspects derived from the context.\n"
        f"5. **Character Adherence:** Strictly match the personalities, speaking styles, and interaction patterns defined in the profiles.\n"
        f"6. **Proactive Host Role:** Host guides the conversation, introduces the main topic '{topic}' and the podcast name '{podcast_name}' in the intro, connects topics, and expresses the listener's perspective. **Crucially, the Host should actively look for opportunities to ask insightful follow-up questions after the Guest responds, potentially drawing more details from other relevant summaries. The Host MUST also ask for clarification if the Guest provides a complex, technical, or potentially confusing answer.**\n"
        f"7. **Informative Guest Role:** Guest provides expert information, explains complex ideas clearly, links related concepts, and responds thoughtfully to the host's initial and follow-up questions.\n\n"
        f"**Content Organization:**\n"
        f"   - Intro: Host introduces podcast ('{podcast_name}'), topic ('{topic}'), and guest. Asks for high-level overview based on the overall context.\n"
        f"   - Body: Discuss key aspects from the summaries (prioritizing high scores) and reference documents. Use Host's follow-up questions and clarifications to delve deeper. Ensure Guest defines technical terms. Transition smoothly between sub-topics derived from all context.\n"
        f"   - Outro: Host briefly summarizes key takeaways and thanks the guest. (A specific sign-off will be added in the refinement step).\n\n"
        f"**CRITICAL FORMATTING RULES (OUTPUT MUST FOLLOW EXACTLY):**\n"
        f"1. **OUTPUT TAG:** You MUST enclose the *entire* podcast script dialogue within a single pair of `<scriptCast>` tags.\n"
        f"2. **DIALOGUE FORMAT:** Inside the `<scriptCast>` tag, each line of dialogue MUST start with either 'Host: ' or 'Guest: ', followed by their speech.\n"
        f"3. **NO EXTRA TEXT:** ONLY include the dialogue lines (starting with 'Host: ' or 'Guest: ') inside the `<scriptCast>` tags. **ABSOLUTELY NO** other text, introductory phrases, explanations, thinking tags (`<think>...</think>`), or stage directions (like `[laughs]`) should be present anywhere in the final output, especially not outside the `<scriptCast>` tags.\n\n"
        f"**Example of CORRECT Output Format:**\n"
        f"<scriptCast>\n"
        f"Host: Welcome back to {podcast_name}, everyone! Today, we're diving into the fascinating topic of '{topic}'. {guest_profile.get('name', 'Guest')}, thanks for joining us. Could you give us the high-level view?\n"
        f"Guest: Absolutely, {host_profile.get('name', 'Host')}! Great to be here. At its core, {topic} is about...\n"
        f"Host: That makes sense. You mentioned [detail from summary], could you expand on that?\n"
        f"Guest: Certainly. That relates to...\n"
        f"Host: Okay, so if I understand correctly, [paraphrases complex point]?\n"
        f"Guest: Exactly!\n"
        f"Host: Fantastic insights, {guest_profile.get('name', 'Guest')}. Thanks for breaking that down.\n"
        f"</scriptCast>\n\n"
        f"**Context for Script Generation:**\n\n"
        f"--- Summaries (Prioritize higher scores) ---\n{combined_summaries_text}\n---\n\n"
        f"{full_reference_docs_text}\n\n" # This will be empty if no full docs were used
        f"Remember: The entire output MUST be ONLY the dialogue script (with 'Host:'/'Guest:' labels) enclosed in a single `<scriptCast>` tag. NO OTHER TEXT OR TAGS outside of this single tag pair."
    )
    # Return counts for both summaries and full reference docs used
    return prompt, num_summaries_used, num_ref_docs_used


def format_refinement_prompt(initial_script_text, topic, host_profile, guest_profile):
    """Formats the prompt for the script refinement AI call."""

    podcast_name = host_profile.get('podcast_name', 'Podcast')
    host_details = yaml.dump(host_profile, default_flow_style=False, sort_keys=False)
    guest_details = yaml.dump(guest_profile, default_flow_style=False, sort_keys=False)

    # Mandatory Host Outro Line (incorporating profile names)
    host_name = host_profile.get('name', 'your host')
    outro_line = f"Host: Thank you for joining us! I'm {host_name}, and this has been {podcast_name}. Until next time!"

    prompt = (
        f"You are an AI script editor for the podcast '{podcast_name}'. Your task is to refine the provided podcast script to make it sound more natural and human-like, based on the character profiles, and to prepare it for Text-to-Speech (TTS) by expanding abbreviations and numbers.\n\n"
        f"**Characters:**\n\n"
        f"--- HOST PROFILE ---\n{host_details}\n--------------------\n\n"
        f"--- GUEST PROFILE ---\n{guest_details}\n---------------------\n\n"
        f"**Podcast Topic:** {topic}\n\n"
        f"**Task:**\n"
        f"Review and refine the following podcast script. Apply these specific changes:\n"
        f"1. **Enhance Natural Dialogue:** Adjust phrasing, add minor interjections (like 'uh-huh', 'right', 'interesting', 'you know'), smooth transitions, and ensure the conversation flows naturally according to the host and guest personalities. Maintain the '{host_profile.get('vibe', 'chill but informal')}' vibe.\n"
        f"2. **TTS Prep - Expand Abbreviations:** Find common abbreviations (e.g., 'AI', 'LLM', 'API', 'CPU', 'GPU', 'etc.') and expand them appropriately for speech (e.g., 'Artificial Intelligence' or 'A.I.', 'L.L.M.', 'A.P.I.'). Use context; spell out the first time if helpful.\n"
        f"3. **TTS Prep - Expand Numbers/Currency/Symbols:** Convert numerical figures, percentages, currency amounts, and common symbols into words suitable for speech. Examples:\n"
        f"   - '$40' -> 'forty dollars'\n"
        f"   - '0.45' -> 'point four five' or 'forty-five cents'\n"
        f"   - '$45B' / $45bn -> 'forty-five billion dollars'\n"
        f"   - '50%' -> 'fifty percent'\n"
        f"   - '2024' -> 'twenty twenty-four' (year) or 'two thousand twenty-four'\n"
        f"   - '#' -> 'number' or 'hash'\n"
        f"   - '@' -> 'at'\n"
        f"   - '&' -> 'and'\n"
        f"4. **TTS Prep - Handle Asterisks/Emphasis:** Replace text emphasized with asterisks (e.g., *important* or **critical**) with phrasing that conveys emphasis verbally, or remove the asterisks if emphasis isn't crucial for TTS.\n"
        f"5. **Maintain Structure:** Keep the original 'Host: ' and 'Guest: ' labels for each line.\n"
        f"6. **Character Consistency:** Ensure the refined dialogue still perfectly matches the character profiles.\n"
        f"7. **Mandatory Host Outro:** Ensure the *very last line* of the script is spoken by the Host and is EXACTLY: '{outro_line}'\n\n"
        f"**Original Script to Refine:**\n---\n{initial_script_text}\n---\n\n"
        f"**CRITICAL FORMATTING RULES (OUTPUT MUST FOLLOW EXACTLY):**\n"
        f"1. **OUTPUT TAG:** You MUST enclose the *entire* refined podcast script dialogue within a single pair of `<scriptCast>` tags.\n"
        f"2. **DIALOGUE FORMAT:** Inside the `<scriptCast>` tag, each line of dialogue MUST start with either 'Host: ' or 'Guest: ', followed by their speech.\n"
        f"3. **NO EXTRA TEXT:** ONLY include the dialogue lines (starting with 'Host: ' or 'Guest: ') inside the `<scriptCast>` tags. **ABSOLUTELY NO** other text, introductory phrases, explanations, or thinking tags (`<think>...</think>`) should be present anywhere in the final output.\n\n"
        f"**Example of CORRECT Refined Output Format:**\n"
        f"<scriptCast>\n"
        f"Host: Welcome back to {podcast_name}, everyone! Today, we're diving into the fascinating topic of '{topic}'. {guest_profile.get('name', 'Guest')}, thanks for joining us. Could you give us the, you know, the high-level view?\n"
        f"Guest: Absolutely, {host_profile.get('name', 'Host')}! Great to be here. Right, so at its core, {topic} is about...\n"
        f"Host: Interesting. You mentioned achieving, uh, ninety-five percent accuracy? Could you expand on that?\n"
        f"Guest: Certainly. That relates to the model we developed back in twenty twenty-three...\n"
        f"Host: Okay, so if I understand correctly, you're saying it cost forty million dollars?\n"
        f"Guest: Exactly! A significant investment.\n"
        f"{outro_line}\n" # Ensure example includes the outro
        f"</scriptCast>\n\n"
        f"Remember: The entire output MUST be ONLY the refined dialogue script (with 'Host:'/'Guest:' labels) enclosed in a single `<scriptCast>` tag, ending with the specific Host outro line."
    )
    return prompt


def generate_and_refine_script(summaries_with_scores, reference_docs_content, topic, host_profile, guest_profile, config, args):
    """Generates, refines, and saves the podcast script."""
    global run_archive_dir
    print("\nGenerating and refining podcast script...")
    log_to_file("Starting script generation and refinement phase.")

    # --- Initial Generation ---
    # Pass reference_docs_content to the formatting function
    initial_prompt, num_summaries, num_ref_docs = format_script_generation_prompt(summaries_with_scores, reference_docs_content, topic, host_profile, guest_profile, args)
    if not initial_prompt: return None # Error occurred in formatting

    # Save initial prompt
    if run_archive_dir:
        prompt_filename = os.path.join(run_archive_dir, "script_initial_prompt.txt")
        try:
            with open(prompt_filename, 'w', encoding='utf-8') as pf: pf.write(initial_prompt)
            log_to_file(f"Saved initial script prompt to {prompt_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save initial script prompt: {e}")

    print("Calling AI for initial script generation...")
    raw_initial_response, cleaned_initial_response = call_ai_api(initial_prompt, config, tool_name="ScriptGeneration_Initial", timeout=3000) # Longer timeout

    # Save initial raw response
    if run_archive_dir and raw_initial_response:
        raw_resp_filename = os.path.join(run_archive_dir, "script_initial_response_raw.txt")
        try:
            with open(raw_resp_filename, 'w', encoding='utf-8') as rf: rf.write(raw_initial_response)
            log_to_file(f"Saved initial script raw response to {raw_resp_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save initial script raw response: {e}")

    if not cleaned_initial_response:
        print("\nError: Failed to generate initial script (empty cleaned response).")
        log_to_file("Script Gen Error: Initial generation failed (empty cleaned response).")
        return None

    initial_script_text = parse_ai_tool_response(cleaned_initial_response, "scriptCast")

    if not initial_script_text or initial_script_text == cleaned_initial_response:
        print("\nError: Could not parse <scriptCast> tag in initial script response.")
        log_to_file(f"Script Gen Error: Failed to parse <scriptCast> tag in initial response.\nResponse was:\n{cleaned_initial_response}")
        # Save the failed parsed output for debugging
        if run_archive_dir:
            failed_script_path = os.path.join(run_archive_dir, "script_initial_FAILED_PARSE.txt")
            try:
                with open(failed_script_path, 'w', encoding='utf-8') as fsf: fsf.write(cleaned_initial_response)
            except IOError: pass
        return None

    # Basic validation
    if not re.search(r'^(Host|Guest):', initial_script_text, re.MULTILINE):
         print("\nWarning: Initial script content doesn't seem to contain 'Host:' or 'Guest:' labels.")
         log_to_file("Script Gen Warning: Initial script missing Host:/Guest: labels.")
         # Proceed to refinement, maybe it can fix it?

    line_count = initial_script_text.count('\n') + 1
    print(f"Generated initial script with {line_count} lines.")
    log_to_file(f"Script Gen: Initial script generated ({line_count} lines).")
    # Save initial script before refinement
    if run_archive_dir:
         initial_script_path = os.path.join(run_archive_dir, "script_initial_GENERATED.txt")
         try:
             with open(initial_script_path, 'w', encoding='utf-8') as isf: isf.write(initial_script_text)
             log_to_file(f"Saved initial generated script to {initial_script_path}")
         except IOError as e: log_to_file(f"Warning: Could not save initial generated script: {e}")


    # --- Refinement Step ---
    refinement_prompt = format_refinement_prompt(initial_script_text, topic, host_profile, guest_profile)

    # Save refinement prompt
    if run_archive_dir:
        prompt_filename = os.path.join(run_archive_dir, "script_refinement_prompt.txt")
        try:
            with open(prompt_filename, 'w', encoding='utf-8') as pf: pf.write(refinement_prompt)
            log_to_file(f"Saved refinement script prompt to {prompt_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save refinement script prompt: {e}")

    print("Calling AI for script refinement...")
    raw_refined_response, cleaned_refined_response = call_ai_api(refinement_prompt, config, tool_name="ScriptRefinement", timeout=300)

    # Save refinement raw response
    if run_archive_dir and raw_refined_response:
        raw_resp_filename = os.path.join(run_archive_dir, "script_refinement_response_raw.txt")
        try:
            with open(raw_resp_filename, 'w', encoding='utf-8') as rf: rf.write(raw_refined_response)
            log_to_file(f"Saved refinement script raw response to {raw_resp_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save refinement script raw response: {e}")

    if not cleaned_refined_response:
        print("\nWarning: Failed to refine script (empty cleaned response). Using initial script.")
        log_to_file("Script Refinement Warning: Refinement failed (empty cleaned response). Using initial script.")
        final_script_text = initial_script_text # Fallback to initial
    else:
        refined_script_text = parse_ai_tool_response(cleaned_refined_response, "scriptCast")

        if not refined_script_text or refined_script_text == cleaned_refined_response:
            print("\nWarning: Could not parse <scriptCast> tag in refinement response. Using initial script.")
            log_to_file(f"Script Refinement Warning: Failed to parse <scriptCast> tag in refinement response. Using initial script.\nResponse was:\n{cleaned_refined_response}")
            final_script_text = initial_script_text # Fallback to initial
             # Save the failed refinement output for debugging
            if run_archive_dir:
                failed_script_path = os.path.join(run_archive_dir, "script_refinement_FAILED_PARSE.txt")
                try:
                    with open(failed_script_path, 'w', encoding='utf-8') as fsf: fsf.write(cleaned_refined_response)
                except IOError: pass
        else:
             # Basic validation
            if not re.search(r'^(Host|Guest):', refined_script_text, re.MULTILINE):
                 print("\nWarning: Refined script content missing 'Host:'/'Guest:' labels. Using initial script.")
                 log_to_file("Script Refinement Warning: Refined script missing Host:/Guest: labels. Using initial script.")
                 final_script_text = initial_script_text # Fallback
            else:
                 print("Script refinement successful.")
                 log_to_file("Script Refinement: Success.")
                 final_script_text = refined_script_text # Use refined script

    # --- Save Final Script ---
    final_script_filename = "podcast_script_final.txt" # Default name
    final_script_filepath = os.path.join(run_archive_dir, final_script_filename) if run_archive_dir else final_script_filename

    try:
        with open(final_script_filepath, 'w', encoding='utf-8') as sf:
            sf.write(final_script_text)
        print(f"Saved final script to {final_script_filepath}")
        log_to_file(f"Final script saved to {final_script_filepath}")
        return final_script_filepath
    except IOError as e:
        print(f"\nError: Could not save final script to {final_script_filepath}: {e}")
        log_to_file(f"Script Saving Error: Failed to save final script to {final_script_filepath}: {e}")
        # Try saving to CWD as fallback ONLY if archive failed
        if run_archive_dir:
            try:
                cwd_filename = final_script_filename
                with open(cwd_filename, 'w', encoding='utf-8') as sf_cwd:
                    sf_cwd.write(final_script_text)
                print(f"Saved final script to {cwd_filename} (in CWD as fallback)")
                log_to_file(f"Final script saved to CWD fallback: {cwd_filename}")
                return cwd_filename
            except IOError as e_cwd:
                print(f"\nError: Could not save final script to CWD fallback path either: {e_cwd}")
                log_to_file(f"Script Saving Error: Failed to save final script to CWD fallback: {e_cwd}")
                return None # Saving failed completely
        else:
             return None # Saving failed (no archive dir to begin with)


# --- Report Generation ---

def generate_report(summaries_with_scores, reference_docs_content, topic, config, args):
    """Uses AI to generate a written report/paper based on summaries and optionally full reference docs."""
    global run_archive_dir
    print("\nGenerating report via AI...")
    log_to_file(f"Starting report generation. Topic: {topic}")

    # --- Process Summaries ---
    # Use all valid summaries (which might include summarized ref docs), sorted by score
    valid_summaries = [s for s in summaries_with_scores if s['score'] >= 0 and not s['summary'].startswith("Error:")]
    num_summaries_used = 0
    combined_summaries_text = "No valid summaries were generated or met the criteria."

    if valid_summaries:
        top_summaries = sorted(valid_summaries, key=lambda x: x['score'], reverse=True)
        num_summaries_used = len(top_summaries)
        print(f"Using {num_summaries_used} summaries for report generation.")
        log_to_file(f"Report Gen: Using {num_summaries_used} valid summaries.")
        combined_summaries_text = "\n\n".join([
            # Include source info in the report prompt context as well
            f"Summary {i+1} (Source: {s['source_id']}, Type: {s['type']}, Score: {s['score']}):\n{s['summary']}"
            for i, s in enumerate(top_summaries)
        ])
    else:
         print("Warning: No valid summaries available for report generation.")
         log_to_file("Report Gen Warning: No valid summaries found.")
         # We might still proceed if full reference docs are available

    # --- Process Full Reference Documents (If Not Summarized) ---
    full_reference_docs_text = ""
    num_ref_docs_used = 0
    if reference_docs_content and not args.reference_docs_summarize:
        num_ref_docs_used = len(reference_docs_content)
        print(f"Including {num_ref_docs_used} full reference documents directly in the report prompt.")
        log_to_file(f"Report Gen: Including {num_ref_docs_used} full reference documents.")
        full_reference_docs_text = "\n\n---\n\n".join([
            f"Reference Document (Path: {doc['path']}):\n{doc['content']}"
            for doc in reference_docs_content
        ])
        # Add a header for clarity in the prompt
        full_reference_docs_text = f"**Full Reference Documents (Use for context):**\n---\n{full_reference_docs_text}\n---"

    # Check if we have *any* content to generate from
    if num_summaries_used == 0 and num_ref_docs_used == 0:
         print("Error: No summaries or reference documents available to generate report.")
         log_to_file("Report Gen Error: No summaries or reference documents available for context.")
         return None # Cannot generate report without context

    guidance_text = f"\n**Additional Guidance:** {args.guidance}\n" if args.guidance else ""
    prompt = (
        f"You are an AI assistant tasked with writing a well-structured, informative research paper/report on the topic: '{topic}'.{guidance_text}\n"
        f"**Topic:** {topic}\n"
        f"{guidance_text}\n" # Add guidance here as well for clarity
        f"**Task:**\n"
        f"Generate a comprehensive report based *thoroughly* on the provided context (summaries and/or full reference documents). Synthesize the information, identify key themes, arguments, evidence, and supporting details (including specific statistics, names, dates, or benchmarks mentioned). Structure the report logically with an introduction (defining the topic and scope), body paragraphs (each exploring a specific facet or theme derived from the context, citing evidence implicitly), and a conclusion (summarizing key findings and potential implications or future directions). Maintain an objective, formal, and informative tone suitable for a research report.\n\n"
        f"**Context for Report Generation (Analyze ALL):**\n\n"
        f"--- Summaries (Analyze these first) ---\n{combined_summaries_text}\n---\n\n"
        f"{full_reference_docs_text}\n\n" # This will be empty if no full docs were used
        f"**CRITICAL FORMATTING RULES (OUTPUT MUST FOLLOW EXACTLY):**\n"
        f"1. **OUTPUT TAG:** You MUST enclose the *entire* report content within a single pair of `<reportGenerate>` tags.\n"
        f"2. **CONTENT:** The content should be well-written, coherent, and directly based on the provided summaries.\n"
        f"3. **NO EXTRA TEXT:** ONLY include the report text inside the `<reportGenerate>` tags. **ABSOLUTELY NO** other text, introductory phrases, explanations, or thinking tags (`<think>...</think>`) should be present anywhere in the final output.\n\n"
        f"Remember: The entire output MUST be ONLY the report text enclosed in a single `<reportGenerate>` tag."
    )

    # Save report prompt
    if run_archive_dir:
        prompt_filename = os.path.join(run_archive_dir, "report_prompt.txt")
        try:
            with open(prompt_filename, 'w', encoding='utf-8') as pf: pf.write(prompt)
            log_to_file(f"Saved report prompt to {prompt_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save report prompt: {e}")

    # Call AI
    raw_response, cleaned_response = call_ai_api(prompt, config, tool_name="ReportGeneration", timeout=3000)

    # Save raw response
    if run_archive_dir and raw_response:
        raw_resp_filename = os.path.join(run_archive_dir, "report_response_raw.txt")
        try:
            with open(raw_resp_filename, 'w', encoding='utf-8') as rf: rf.write(raw_response)
            log_to_file(f"Saved report raw response to {raw_resp_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save report raw response: {e}")

    if not cleaned_response:
        print("\nError: Failed to generate report from AI (empty cleaned response).")
        log_to_file("Report Gen Error: Failed (empty cleaned response).")
        return None

    # Parse the response - Find last <reportGenerate> tag after cleaning <think> tags
    cleaned_text_for_report = clean_thinking_tags(cleaned_response)
    report_text = None
    if cleaned_text_for_report:
        last_opening_tag_index = cleaned_text_for_report.rfind('<reportGenerate>')
        if last_opening_tag_index != -1:
            closing_tag_index = cleaned_text_for_report.find('</reportGenerate>', last_opening_tag_index)
            if closing_tag_index != -1:
                start_content = last_opening_tag_index + len('<reportGenerate>')
                report_text = cleaned_text_for_report[start_content:closing_tag_index].strip()

    if not report_text: # Check if parsing failed or resulted in empty string
        print("\nError: Could not parse valid <reportGenerate> content from the AI response.")
        log_to_file(f"Report Gen Error: Failed to parse <reportGenerate> tag or content was empty.\nCleaned Response was:\n{cleaned_text_for_report}")
        # Save the failed report output for debugging
        if run_archive_dir:
            failed_report_path = os.path.join(run_archive_dir, "report_FAILED_PARSE.txt")
            try:
                with open(failed_report_path, 'w', encoding='utf-8') as frf: frf.write(cleaned_text_for_report or "Original cleaned response was empty.")
            except IOError: pass
        return None

    # Save the report
    final_report_filename = "podcast_report.txt"
    final_report_filepath = os.path.join(run_archive_dir, final_report_filename) if run_archive_dir else final_report_filename

    try:
        with open(final_report_filepath, 'w', encoding='utf-8') as ef:
            ef.write(report_text)
        print(f"Saved generated report to {final_report_filepath}")
        log_to_file(f"Report saved to {final_report_filepath}")
        return final_report_filepath
    except IOError as e:
        print(f"\nError: Could not save generated report to {final_report_filepath}: {e}")
        log_to_file(f"Report Saving Error: Failed to save report to {final_report_filepath}: {e}")
        # Try CWD fallback
        if run_archive_dir:
            try:
                cwd_filename = final_report_filename
                with open(cwd_filename, 'w', encoding='utf-8') as ef_cwd: ef_cwd.write(report_text)
                print(f"Saved generated report to {cwd_filename} (in CWD as fallback)")
                log_to_file(f"Report saved to CWD fallback: {cwd_filename}")
                return cwd_filename
            except IOError as e_cwd:
                print(f"\nError: Could not save report to CWD fallback path either: {e_cwd}")
                log_to_file(f"Report Saving Error: Failed to save report to CWD fallback: {e_cwd}")
                return None
        else:
            return None


# --- Audio Synthesis (Placeholder) ---

def synthesize_audio(script_text_filepath, run_archive_dir):
    """Synthesizes audio from the script text file using TTS (Placeholder)."""
    print("\nSynthesizing audio (Placeholder)...")
    log_to_file("Starting audio synthesis phase (Placeholder).")
    if not script_text_filepath or not os.path.exists(script_text_filepath):
        print("Error: Script text file path is invalid or file does not exist.")
        log_to_file("Audio Synth Error: Script file not found or path invalid.")
        return None

    # TODO: Implement actual TTS integration (e.g., StyleTTS 2, CoquiTTS, Piper, etc.)
    #   - Parse script_text_filepath line by line (Host: ..., Guest: ...)
    #   - Select appropriate voice model/speaker based on Host/Guest
    #   - Synthesize each line to a temporary audio segment
    #   - Concatenate segments using pydub or similar
    #   - Add intro/outro music if desired
    #   - Export final audio file

    # Placeholder: Create an empty file
    output_filename = "podcast_final_audio.mp3"
    final_audio_path = os.path.join(run_archive_dir, output_filename) if run_archive_dir else output_filename

    print(f"Placeholder: Audio would be saved to {final_audio_path}")
    try:
        with open(final_audio_path, 'w') as f:
            f.write("Placeholder audio content generated by mainv3.py.")
        print(f"Simulated audio file created: {final_audio_path}")
        log_to_file(f"Audio synthesis placeholder complete. Simulated file: {final_audio_path}")
        return final_audio_path
    except IOError as e:
        print(f"Error creating placeholder audio file: {e}")
        log_to_file(f"Audio Synth Error: Failed to create placeholder file {final_audio_path}: {e}")
        return None

# --- Main Execution ---

def main():
    """Main function to orchestrate the podcast generation workflow."""
    global run_archive_dir # Allow modification of the global variable

    print("--- Starting AI Podcast Generator (v3) ---")
    start_time = time.time()

    # --- Setup ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env_config, models_config = load_config() # Unpack the tuple
    args = parse_arguments() # This function now loads YAML keys for --llm-model choices

    # --- Determine Final Model Configuration ---
    # Priority: Command Line (--llm-model) > Environment Variable (DEFAULT_MODEL_CONFIG) > Default ('default_model')
    final_model_key = "default_model" # Ultimate fallback
    env_model_key = os.getenv("DEFAULT_MODEL_CONFIG")

    if args.llm_model:
        final_model_key = args.llm_model
        print(f"Using LLM model specified via command line: '{final_model_key}'")
        # Store the finally chosen key in config for potential reference later (e.g., in call_ai_api error messages)
        env_config['final_model_key'] = final_model_key # Use env_config dict
        log_to_file(f"Model Selection: Using command line override: '{final_model_key}'")
    elif env_model_key:
        final_model_key = env_model_key
        print(f"Using LLM model specified via .env: '{final_model_key}'")
        env_config['final_model_key'] = final_model_key # Use env_config dict
        log_to_file(f"Model Selection: Using .env setting: '{final_model_key}'")
    else:
        print(f"Using default LLM model: '{final_model_key}' (Neither --llm-model nor DEFAULT_MODEL_CONFIG set)")
        env_config['final_model_key'] = final_model_key # Use env_config dict
        log_to_file(f"Model Selection: Using default: '{final_model_key}'")

    # Validate the final key and get the configuration from the already loaded models_config
    final_model_config = models_config.get(final_model_key)
    if not final_model_config or not isinstance(final_model_config, dict):
        print(f"Error: Final selected model key '{final_model_key}' configuration not found or invalid in ai_models.yml")
        print(f"Available configurations: {list(models_config.keys())}")
        log_to_file(f"Run Error: Invalid final model key selected: '{final_model_key}'")
        exit(1)
    if 'model' not in final_model_config:
        print(f"Error: 'model' name is missing in the configuration for '{final_model_key}' in ai_models.yml")
        log_to_file(f"Run Error: 'model' name missing for selected config key: '{final_model_key}'")
        exit(1)

    # Store the final selected config back into the main config dict for use by call_ai_api
    env_config["selected_model_config"] = final_model_config # Use env_config dict
    log_to_file(f"Final Model Config Used: {final_model_config}")
    # --- End Final Model Configuration Determination ---

    # Create Archive Directory for this run
    archive_base_dir = "archive"
    topic_slug = re.sub(r'\W+', '_', args.topic)[:50] # Sanitize topic for dir name
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_archive_dir_name = f"{timestamp}_{topic_slug}"
    run_archive_dir = os.path.join(archive_base_dir, run_archive_dir_name)
    try:
        os.makedirs(run_archive_dir, exist_ok=True)
        print(f"Created archive directory: {run_archive_dir}")
        # Initialize log file for this run
        log_to_file(f"--- AI Podcast Generator Run Start ({timestamp}) ---")
        log_to_file(f"Args: {vars(args)}")
        log_to_file(f"Env Config Keys Loaded: {list(env_config.keys())}") # Log env_config keys
        log_to_file(f"Model Config Keys Loaded: {list(models_config.keys())}") # Log models_config keys
    except OSError as e:
        print(f"Error creating archive directory {run_archive_dir}: {e}")
        run_archive_dir = None # Continue without archiving if creation fails
        log_to_file("Error: Failed to create archive directory. Archiving disabled for this run.")

    # Load Character Profiles (after archive dir is set for logging)
    host_profile_path = os.path.join(script_dir, 'settings', 'characters', 'host.yml')
    guest_profile_path = os.path.join(script_dir, 'settings', 'characters', 'guest.yml')
    host_profile = load_character_profile(host_profile_path)
    guest_profile = load_character_profile(guest_profile_path)
    if not host_profile or not guest_profile:
        print("Error: Failed to load character profiles. Exiting.")
        log_to_file("Run Error: Failed to load character profiles.")
        exit(1)
    log_to_file(f"Host Profile loaded: {host_profile}")

    # --- Load Reference Documents --- 
    reference_docs_content = []
    if args.reference_docs:
        print("\nLoading reference documents...")
        log_to_file(f"Attempting to load reference documents from: {args.reference_docs}")
        ref_doc_paths = [p.strip() for p in args.reference_docs.split(',') if p.strip()]
        for doc_path in ref_doc_paths:
            content = None
            try:
                print(f"  - Processing reference document: {doc_path}")
                if doc_path.lower().endswith('.pdf'):
                    # PDF processing
                    text_content = []
                    with open(doc_path, 'rb') as pdf_file: # Open in binary mode
                        reader = PyPDF2.PdfReader(pdf_file) # Use PdfReader
                        if reader.is_encrypted:
                             print(f"    - Warning: Skipping encrypted PDF: {doc_path}")
                             log_to_file(f"Warning: Skipping encrypted PDF: {doc_path}")
                             continue # Skip encrypted PDFs
                        for page in reader.pages:
                            page_text = page.extract_text()
                            if page_text: # Ensure text was extracted
                                text_content.append(page_text)
                    content = "\n".join(text_content)
                    print(f"    - Extracted text from PDF.")
                elif doc_path.lower().endswith('.docx'):
                    # DOCX processing
                    doc = docx.Document(doc_path)
                    text_content = [para.text for para in doc.paragraphs if para.text] # Filter empty paragraphs
                    content = "\n".join(text_content)
                    print(f"    - Extracted text from DOCX.")
                else: # Assume plain text for .txt or unknown/other extensions
                    if not doc_path.lower().endswith('.txt'):
                         print(f"    - Warning: Unknown extension for '{doc_path}', attempting to read as plain text.")
                         log_to_file(f"Warning: Unknown extension for reference doc '{doc_path}', reading as text.")
                    with open(doc_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    print(f"    - Read as plain text.")

                # Process extracted content
                if content and content.strip():
                    reference_docs_content.append({"path": doc_path, "content": content.strip()})
                    print(f"    - Successfully loaded content ({len(content)} chars).")
                    log_to_file(f"Loaded reference doc: {doc_path} ({len(content)} chars)")
                else:
                    print(f"    - Warning: No text content extracted or file is empty.")
                    log_to_file(f"Warning: Reference document {doc_path} empty or no text extracted.")

            except FileNotFoundError:
                print(f"  - Error: Reference document file not found: {doc_path}")
                log_to_file(f"Error: Reference document file not found: {doc_path}")
            except PyPDF2.errors.PdfReadError as pdf_err: # Catch specific PyPDF2 errors
                 print(f"  - Error reading PDF file {doc_path}: {pdf_err}")
                 log_to_file(f"Error reading PDF file {doc_path}: {pdf_err}")
            except Exception as e: # General catch-all
                print(f"  - Error processing reference document {doc_path}: {e}")
                log_to_file(f"Error processing reference document {doc_path}: {e} (Type: {type(e).__name__})")
        if not reference_docs_content:
            print("Warning: No valid reference documents were loaded despite --reference-docs being set.")
            log_to_file("Warning: --reference-docs set, but no content loaded.")

    # --- Load Reference Documents from Folder --- 
    if args.reference_docs_folder:
        print(f"\nLoading reference documents from folder: {args.reference_docs_folder}")
        log_to_file(f"Attempting to load reference documents from folder: {args.reference_docs_folder}")
        if not os.path.isdir(args.reference_docs_folder):
            print(f"  - Error: Provided path is not a valid directory: {args.reference_docs_folder}")
            log_to_file(f"Error: --reference-docs-folder path is not a directory: {args.reference_docs_folder}")
        else:
            for filename in os.listdir(args.reference_docs_folder):
                doc_path = os.path.join(args.reference_docs_folder, filename)
                if not os.path.isfile(doc_path):
                    continue # Skip subdirectories

                content = None
                file_ext = os.path.splitext(filename)[1].lower()

                try:
                    print(f"  - Processing reference document: {doc_path}")
                    if file_ext == '.pdf':
                        # PDF processing
                        text_content = []
                        with open(doc_path, 'rb') as pdf_file:
                            reader = PyPDF2.PdfReader(pdf_file)
                            if reader.is_encrypted:
                                print(f"    - Warning: Skipping encrypted PDF: {doc_path}")
                                log_to_file(f"Warning: Skipping encrypted PDF: {doc_path}")
                                continue
                            for page in reader.pages:
                                page_text = page.extract_text()
                                if page_text:
                                    text_content.append(page_text)
                        content = "\n".join(text_content)
                        print(f"    - Extracted text from PDF.")
                    elif file_ext == '.docx':
                        # DOCX processing
                        doc = docx.Document(doc_path)
                        text_content = [para.text for para in doc.paragraphs if para.text]
                        content = "\n".join(text_content)
                        print(f"    - Extracted text from DOCX.")
                    elif file_ext == '.txt':
                        # TXT processing
                        with open(doc_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        print(f"    - Read as plain text.")
                    else:
                        print(f"    - Skipping unsupported file type: {filename}")
                        log_to_file(f"Skipping unsupported file type in reference folder: {filename}")
                        continue # Skip unsupported files

                    # Process extracted content
                    if content and content.strip():
                        # Check for duplicates based on path before adding
                        if not any(d['path'] == doc_path for d in reference_docs_content):
                            reference_docs_content.append({"path": doc_path, "content": content.strip()})
                            print(f"    - Successfully loaded content ({len(content)} chars).")
                            log_to_file(f"Loaded reference doc from folder: {doc_path} ({len(content)} chars)")
                        else:
                            print(f"    - Skipping duplicate document already loaded: {doc_path}")
                            log_to_file(f"Skipping duplicate reference doc from folder: {doc_path}")
                    else:
                        print(f"    - Warning: No text content extracted or file is empty.")
                        log_to_file(f"Warning: Reference document {doc_path} from folder is empty or no text extracted.")

                except FileNotFoundError: # Should not happen with listdir unless race condition
                    print(f"  - Error: Reference document file not found unexpectedly: {doc_path}")
                    log_to_file(f"Error: Reference document file not found unexpectedly: {doc_path}")
                except PyPDF2.errors.PdfReadError as pdf_err:
                    print(f"  - Error reading PDF file {doc_path}: {pdf_err}")
                    log_to_file(f"Error reading PDF file {doc_path} from folder: {pdf_err}")
                except Exception as e:
                    print(f"  - Error processing reference document {doc_path}: {e}")
                    log_to_file(f"Error processing reference document {doc_path} from folder: {e} (Type: {type(e).__name__})")
        log_to_file(f"Finished processing reference documents folder. Total loaded: {len(reference_docs_content)}")


    log_to_file(f"Guest Profile loaded: {guest_profile}")


    # --- Workflow Steps ---
    try:
        # 1. Load Direct Articles (if specified)
        direct_article_urls = []
        if args.direct_articles:
            print(f"\nLoading direct articles from: {args.direct_articles}")
            log_to_file(f"Attempting to load direct articles from {args.direct_articles}")
            try:
                with open(args.direct_articles, 'r', encoding='utf-8') as f:
                    direct_article_urls = [line.strip() for line in f if line.strip() and line.strip().startswith(('http://', 'https://'))]
                if direct_article_urls:
                    print(f"Successfully loaded {len(direct_article_urls)} direct article URLs.")
                    log_to_file(f"Loaded {len(direct_article_urls)} direct URLs: {direct_article_urls}")
                else:
                    print(f"Warning: File {args.direct_articles} was empty or contained no valid URLs.")
                    log_to_file(f"Warning: Direct articles file {args.direct_articles} empty or invalid.")
            except FileNotFoundError:
                print(f"Error: Direct articles file not found: {args.direct_articles}")
                log_to_file(f"Error: Direct articles file not found: {args.direct_articles}")
                if args.no_search: # Critical if no search is allowed
                     raise FileNotFoundError(f"Direct articles file '{args.direct_articles}' not found, and --no-search was specified.")
                # If search is allowed, we can potentially continue without direct articles
            except Exception as e:
                print(f"Error reading direct articles file {args.direct_articles}: {e}")
                log_to_file(f"Error reading direct articles file {args.direct_articles}: {e}")
                if args.no_search: # Critical if no search is allowed
                     raise IOError(f"Failed to read direct articles file '{args.direct_articles}' due to error: {e}, and --no-search was specified.")

        # 2. Determine Sources/URLs to Scrape (and potentially discover sources)
        sources_for_scraping = [] # URLs/Subreddits to actually scrape
        if args.no_search:
            print("--no-search specified. Skipping source discovery and web search.")
            log_to_file("Source Determination: --no-search active. Skipping discovery/web search.")
            # Use only direct articles for scraping, if provided. Reference docs are handled separately.
            sources_for_scraping = direct_article_urls
            if sources_for_scraping:
                 print(f"Using {len(sources_for_scraping)} URLs from --direct-articles for scraping.")
                 log_to_file(f"Source Determination: Using {len(sources_for_scraping)} direct URLs for scraping.")
            else:
                 print("No direct articles provided via --direct-articles. Skipping scraping phase.")
                 log_to_file("Source Determination: No direct articles provided. Skipping scraping phase.")
            # Argument parser already ensures we have *some* offline content (direct_articles OR reference_docs OR reference_docs_folder)
        else:
            # Search is active, discover sources if needed
            print("Discovering sources via AI and combining with direct articles (if any)...")
            log_to_file("Source Determination: Discovering sources and combining with direct articles.")
            # Keywords are required here (validated by parser)
            discovered_sources = discover_sources(args.search_queries, env_config) # Pass env_config

            # Combine and deduplicate sources for scraping
            combined_sources = direct_article_urls + discovered_sources # Prioritize direct URLs
            seen_sources = set()
            unique_combined_sources = []
            for src in combined_sources:
                normalized_src = src # Keep original for now, simple exact match dedupe
                if normalized_src not in seen_sources:
                    unique_combined_sources.append(src)
                    seen_sources.add(normalized_src)

            sources_for_scraping = unique_combined_sources
            print(f"Combined sources for scraping: {len(sources_for_scraping)} unique sources/URLs.")
            log_to_file(f"Source Determination: Combined {len(discovered_sources)} discovered sources with {len(direct_article_urls)} direct URLs, resulting in {len(sources_for_scraping)} unique items for scraping.")

            if not sources_for_scraping and not reference_docs_content:
                 # If search was active but we found no sources AND have no reference docs, we can't proceed.
                 raise RuntimeError("No valid sources were discovered or provided directly, and no reference documents loaded. Cannot proceed.")
            elif not sources_for_scraping:
                 print("Warning: No sources discovered or provided for scraping, but proceeding with reference documents.")
                 log_to_file("Warning: No sources found for scraping, using only reference docs.")


        # 3. Scrape Content (only if sources_for_scraping is not empty)
        scraped_content = []
        if sources_for_scraping:
            scraped_content = scrape_content(sources_for_scraping, args, env_config) # Pass list of URLs/sources
            if not scraped_content and not reference_docs_content:
                 # If scraping failed AND we have no reference docs, we can't proceed.
                 raise RuntimeError("Failed to scrape any content from the provided/discovered sources, and no reference documents loaded.")
            elif not scraped_content:
                  print("Warning: Failed to scrape any content, but proceeding with reference documents.")
                  log_to_file("Warning: Scraping failed, using only reference docs.")
        else:
             print("Skipping content scraping as no sources were provided/discovered for it.")
             # We proceed here because reference_docs_content might still exist

        # Check if we have ANY content (scraped or reference) before summarizing
        if not scraped_content and not reference_docs_content:
             raise RuntimeError("No content available from scraping or reference documents. Cannot proceed.")

        # 4. Summarize Content (scraped and/or reference docs if --reference-docs-summarize)
        # Pass both scraped_content and reference_docs_content to summarize_content
        summaries = summarize_content(scraped_content, reference_docs_content, args.topic, env_config, args)
        # Summarize_content now handles logic for reference docs internally based on args.reference_docs_summarize
        # Check if ANY summaries were successfully generated (score >= 0) OR if we have non-summarized reference docs to use
        have_valid_summaries = any(s['score'] >= 0 for s in summaries)
        have_nonsummarized_ref_docs = reference_docs_content and not args.reference_docs_summarize

        if not have_valid_summaries and not have_nonsummarized_ref_docs:
             raise RuntimeError("Failed to generate any valid summaries, and no reference documents were provided/processed for direct use.")

        # Renumbering subsequent steps mentally
        # 5. Generate Report (Optional)
        if args.report:
            # Pass summaries AND reference_docs_content to generate_report
            report_filepath = generate_report(summaries, reference_docs_content, args.topic, env_config, args)
            if report_filepath:
                print(f"\nSuccessfully generated report: {report_filepath}")
            else:
                print("\nWarning: Report generation failed, but continuing with script generation.")
                log_to_file("Warning: Report generation failed.")

        # 6. Generate & Refine Script
        # Pass summaries AND reference_docs_content to generate_and_refine_script
        script_filepath = generate_and_refine_script(summaries, reference_docs_content, args.topic, host_profile, guest_profile, env_config, args)
        if not script_filepath:
            raise RuntimeError("Failed to generate or refine the podcast script.")

        # Display final script (optional)
        print("\n--- Final Script ---")
        try:
            with open(script_filepath, 'r', encoding='utf-8') as f: print(f.read())
        except Exception as e: print(f"Error reading script file for display: {e}")
        print("------------------\n")

        # 7. Synthesize Audio (Placeholder)
        audio_filepath = synthesize_audio(script_filepath, run_archive_dir)
        if not audio_filepath:
            # Don't raise error, just warn that audio failed
            print("\nWarning: Audio synthesis placeholder step failed.")
            log_to_file("Warning: Audio synthesis failed.")

        # --- Completion ---
        end_time = time.time()
        duration = end_time - start_time
        print("\n--- AI Podcast Generation Complete ---")
        if audio_filepath:
            print(f"Final Audio (Placeholder): {audio_filepath}")
        if script_filepath:
            print(f"Final Script: {script_filepath}")
        if run_archive_dir:
             print(f"Run Archive: {run_archive_dir}")
        print(f"Total Duration: {duration:.2f} seconds")
        log_to_file(f"--- AI Podcast Generator Run End --- Duration: {duration:.2f}s ---")

    except Exception as e:
        print(f"\n--- Workflow Error ---")
        print(f"An error occurred during the podcast generation process: {e}")
        import traceback
        traceback.print_exc() # Print full traceback
        log_to_file(f"FATAL WORKFLOW ERROR: {e}\n{traceback.format_exc()}")
        print("----------------------")
        exit(1)


if __name__ == "__main__":
    # Ensure necessary libraries are installed
    try:
        import newspaper # newspaper4k
        # import praw # No longer needed directly here
        import selenium
    except ImportError as e:
        print(f"Import Error: {e}. Please install necessary libraries.")
        print("Try running: pip install newspaper4k selenium python-dotenv PyYAML requests beautifulsoup4")
        exit(1)

    main()