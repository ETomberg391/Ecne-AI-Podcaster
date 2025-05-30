import requests
import time
import random
import re

from ..ai import call_ai_api # Import call_ai_api from the new ai module
from ..utils import log_to_file, parse_ai_tool_response, USER_AGENTS # Import utilities

def discover_sources(keywords_list, config, args): # Added args parameter
    """Uses AI to discover relevant websites and subreddits."""
    print("\nDiscovering sources via AI...")
    log_to_file("Starting source discovery phase.")
    # Use the first keyword/phrase for simplicity, or combine them
    discovery_keyword_str = " | ".join(keywords_list)
    print(f"Using keywords for discovery: '{discovery_keyword_str}'")
    log_to_file(f"Keywords for discovery: '{discovery_keyword_str}'")

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
        print("\nError: No response received from AI API for source discovery.")
        return []

    sources_str = parse_ai_tool_response(cleaned_response, "toolWebsites")

    if not sources_str or sources_str == cleaned_response: # Parsing failed or tag missing
        log_to_file("Error: Could not parse <toolWebsites> tag in source discovery response.")
        print("\nError: Could not parse <toolWebsites> tag in source discovery response.")
        return []

    # Remove trailing parenthetical explanations before validation
    sources_list_raw = [line.strip() for line in sources_str.split('\n') if line.strip()]
    sources_list = []
    for line in sources_list_raw:
        # Remove ' (explanation...)' from the end of the line
        cleaned_line = re.sub(r'\s*\(.*\)\s*$', '', line).strip()
        if cleaned_line:
            # Handle domain names without protocol
            if '.' in cleaned_line and not cleaned_line.startswith(('http://', 'https://', 'r/')):
                cleaned_line = f"https://{cleaned_line}"
            # Add if it's a valid URL or reddit source
            if cleaned_line.startswith(('http://', 'https://', 'r/')):
                sources_list.append(cleaned_line)

    if not sources_list:
        log_to_file(f"Warning: No valid sources extracted after parsing.\nParsed content: {sources_str}")
        print("\nWarning: No valid sources extracted after parsing.")
        return []

    print(f"Discovered {len(sources_list)} potential sources.")
    log_to_file(f"Discovered {len(sources_list)} potential sources.")

    # --- Add Source Validation ---
    validated_sources = []
    print("Validating sources...")
    log_to_file("Validating discovered sources.")
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
             log_to_file(f"Source validation failed for {source}: {e}")
        except Exception as e:
            print(f" Failed (Unexpected Error: {e})")
            log_to_file(f"Source validation failed for {source} (Unexpected): {e}")

        if is_valid:
            validated_sources.append(source)
        time.sleep(0.5) # Small delay between checks

    print(f"Validated {len(validated_sources)} sources: {validated_sources}")
    log_to_file(f"Validated {len(validated_sources)} sources: {validated_sources}")

    # --- Filter Reddit sources if --no-reddit is specified ---
    if args.no_reddit:
        non_reddit_sources = [src for src in validated_sources if not (src.startswith('r/') or 'reddit.com/r/' in src)]
        print(f"Filtering Reddit sources due to --no-reddit flag. Using {len(non_reddit_sources)} non-Reddit sources.")
        log_to_file(f"Source Discovery: Filtered out Reddit sources. Using {len(non_reddit_sources)} sources: {non_reddit_sources}")
        return non_reddit_sources
    else:
        return validated_sources