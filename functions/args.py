import argparse
import os
import yaml
import datetime
import urllib.parse

# Define LLM_DIR relative to this new structure
# Go up one level from functions, then into Ecne-AI-Podcaster, then settings/llm_settings
NEW_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ORIGINAL_BASE_DIR = os.path.abspath(os.path.join(NEW_SCRIPT_DIR, '..', '..', 'Ecne-AI-Podcaster'))
LLM_DIR = os.path.join(ORIGINAL_BASE_DIR, "settings/llm_settings")


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
    parser.add_argument("--no-reddit", action="store_true", help="Exclude Reddit sources from discovery and scraping.")

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