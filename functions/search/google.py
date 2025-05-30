import requests
import time
import random # For random delays

from ..utils import log_to_file # Import log_to_file from the utils module

def search_google_api(query, config, num_results, from_date=None, to_date=None):
    """Performs search using Google Custom Search API."""
    urls = []
    api_key = config.get("google_api_key")
    cse_id = config.get("google_cse_id")
    if not api_key or not cse_id:
        log_to_file("Google API search skipped: API Key or CSE ID missing.")
        print("    - Google API search skipped: API Key or CSE ID missing.")
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