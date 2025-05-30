import requests
import time
import random
import datetime
import json
import urllib.parse

from ..utils import log_to_file, USER_AGENTS # Import utilities from functions.utils

# --- Search API Functions ---

def search_google_api(query, config, num_results, from_date=None, to_date=None):
    """Performs search using Google Custom Search API."""
    urls = []
    api_key = config.get("google_api_key")
    cse_id = config.get("google_cse_id")
    if not api_key or not cse_id:
        log_to_file("Google API search skipped: API Key or CSE ID missing.")
        return None

    search_url = "https://www.googleapis.com/customsearch/v1"
    # Add date ranges using Google's `sort=date:r:YYYYMMDD:YYYYMMDD` parameter
    date_restrict = ""
    if from_date:
        try:
            from_dt_str = datetime.datetime.strptime(from_date, '%Y-%m-%d').strftime('%Y%m%d')
            to_dt_str = datetime.datetime.strptime(to_date, '%Y-%m-%d').strftime('%Y%m%d') if to_date else datetime.datetime.now().strftime('%Y%m%d')
            date_restrict = f"date:r:{from_dt_str}:{to_dt_str}"
        except ValueError:
             print(f"  - Warning: Invalid date format for Google search '{from_date}' or '{to_date}'. Ignoring date range.")
             log_to_file(f"Google API Warning: Invalid date format '{from_date}'/'{to_date}'. Ignoring date range.")

    print(f"  - Searching Google API: '{query}' (Num: {num_results}, Date: '{date_restrict or 'None'}')")
    log_to_file(f"Google API Search: Query='{query}', Num={num_results}, DateRestrict='{date_restrict}'")

    params = {'key': api_key, 'cx': cse_id, 'q': query, 'num': min(num_results, 10)}
    if date_restrict:
        params['sort'] = date_restrict # Add sort parameter for date range

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
        return None
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
    freshness_param = None

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

    print(f"  - Searching Brave API: '{query}' (Num: {num_results}, Freshness: '{freshness_param or 'None'}')")
    log_to_file(f"Brave API Search: Query='{query}', Num={num_results}, Freshness='{freshness_param}'")

    params = {'q': query, 'count': num_results}
    if freshness_param: params['freshness'] = freshness_param

    try:
        # Log the exact request details before sending
        prepared_request = requests.Request('GET', search_url, headers=headers, params=params).prepare()
        log_to_file(f"Brave API Request Details:\n  URL: {prepared_request.url}\n  Headers: {prepared_request.headers}")
        print(f"    - Requesting URL: {prepared_request.url}") # Also print URL for easier debugging

        response = requests.get(search_url, headers=headers, params=params, timeout=20)
        response.raise_for_status()
        search_data = response.json()
        log_to_file(f"Brave API Raw Response Body:\n{json.dumps(search_data, indent=2)}") # Log the raw JSON response

        if 'web' in search_data and 'results' in search_data['web']:
            urls = [item['url'] for item in search_data['web']['results'] if 'url' in item]
            print(f"    - Brave Found: {len(urls)} results.")
            log_to_file(f"Brave API Success: Found {len(urls)} URLs.")
        else:
            print("    - Brave Found: 0 results.")
            log_to_file(f"Brave API Success: No web/results found in response. Keys: {search_data.keys()}")
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