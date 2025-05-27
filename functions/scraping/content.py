import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
import urllib.parse
# Import scraping and search functions from the new modules
from .web import scrape_website_url
from .reddit import scrape_reddit_source
from ..search.google import search_google_api
from ..search.brave import search_brave_api
# Import utility function
from ..utils import log_to_file, USER_AGENTS

def setup_selenium_driver():
    """Initializes and returns a Selenium WebDriver instance."""
    # Determine the path to chromedriver within the virtual environment
    # This script is in Ecne-AI-Podcasterv2/functions/scraping/
    # The venv is in Ecne-AI-Podcasterv2/host_venv/
    # Chromedriver will be in Ecne-AI-Podcasterv2/host_venv/bin/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up two directories (from functions/scraping to Ecne-AI-Podcasterv2)
    project_root = os.path.abspath(os.path.join(script_dir, '..', '..'))
    chromedriver_path = os.path.join(project_root, 'host_venv', 'bin', 'chromedriver')

    # Check if chromedriver exists at the expected path
    if not os.path.exists(chromedriver_path):
        print(f"    - ERROR: Chromedriver not found at expected path: {chromedriver_path}")
        log_to_file(f"Selenium Skip: Chromedriver not found at {chromedriver_path}")
        return None # Return None if chromedriver is not found

    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless'); options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')

        # Use ChromeService to specify the executable path
        service = ChromeService(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)

        print("    - Selenium WebDriver initialized using venv chromedriver.")
        return driver # Return the driver instance
    except Exception as e:
        print(f"    - ERROR: Failed to initialize Selenium driver: {e}")
        log_to_file(f"Selenium Driver Init Error: {e}")
        return None # Return None on failure
def scrape_content(sources_or_urls, direct_article_urls, args, config):
    """Scrapes content from discovered/provided sources or direct URLs."""
    print(f"\n--- Starting Content Scraping Phase ---")
    scraped_data = [] # Changed from scraped_texts to store dicts
    seen_urls_global = set()
    direct_urls_set = set(direct_article_urls or [])

    for i, item in enumerate(sources_or_urls, 1):
        print(f"\nProcessing item {i}/{len(sources_or_urls)}: {item}")
        source_texts_count = 0

        is_reddit_source = item.startswith('r/') or 'reddit.com/r/' in item
        is_direct_url = item in direct_urls_set and not is_reddit_source
        is_website_source = not is_reddit_source and not is_direct_url

        try:
            # --- Handle Explicit Direct URLs ---
            if is_direct_url:
                print(f"  - Type: Explicit Direct URL")
                if item in seen_urls_global:
                    print(f"      - Skipping already scraped URL: {item}")
                    continue

                scraped_text = scrape_website_url(item)
                if scraped_text:
                    scraped_data.append(scraped_text) # Use scraped_data
                    seen_urls_global.add(item)
                    source_texts_count += 1

            # --- Handle Reddit Sources (Selenium) ---
            elif is_reddit_source:
                # --- Check for --no-reddit flag ---
                if args.no_reddit:
                    print(f"  - Skipping Reddit source '{item}' because --no-reddit flag is set.")
                    log_to_file(f"Scraping Skip: Skipped Reddit source {item} due to --no-reddit flag.")
                    continue # Skip this item entirely

                print(f"  - Type: Reddit Source")
                if args.no_search:
                     print(f"  - Warning: Skipping Reddit source '{item}' because --no-search is active.")
                     log_to_file(f"Scraping Warning: Skipped Reddit source {item} due to --no-search.")
                     continue

                source_scrape_limit = args.max_reddit_results # Limit on POSTS
                subreddit_name = item.replace('r/', '').split('/')[0]
                if not subreddit_name:
                    print(f"  - Warning: Could not extract subreddit name from '{item}'. Skipping.")
                    log_to_file(f"Scraping Warning: Invalid subreddit source format '{item}'")
                    continue

                print(f"  - Processing r/{subreddit_name} using Selenium/old.reddit.com...")
                log_to_file(f"Initiating Selenium scrape for r/{subreddit_name}")
                driver = setup_selenium_driver() # Use helper function
                if not driver:
                     print("    - ERROR: Failed to initialize Selenium driver. Skipping Reddit source.")
                     log_to_file(f"Selenium Skip: Driver initialization failed for r/{subreddit_name}")
                     continue # Skip this source if driver fails

                all_post_links_for_subreddit = set()
                reddit_data = [] # Changed from reddit_texts
                wait = WebDriverWait(driver, 20) # 20 sec timeout for elements

                try:
                    # --- Perform Search for Each Keyword ---
                    if not args.search_queries: # Should not happen if not --no-search, but check
                        print("    - Warning: No search queries defined for Reddit search. Cannot find posts.")
                        log_to_file(f"Selenium Warning: No search queries for r/{subreddit_name}")
                    else:
                        for query_idx, search_query in enumerate(args.search_queries):
                            print(f"      - Searching subreddit for query {query_idx+1}/{len(args.search_queries)}: '{search_query}'")
                            try:
                                encoded_query = urllib.parse.quote_plus(search_query)
                                search_url = f"https://old.reddit.com/r/{subreddit_name}/search/?q={encoded_query}&restrict_sr=1&sort=relevance&t=all" # Ensure restrict_sr=1
                                print(f"        - Navigating to: {search_url}")
                                driver.get(search_url)
                                time.sleep(random.uniform(2.5, 4.5)) # Let dynamic content load

                                # Wait for search results container or a specific result link
                                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.search-result, a.search-link")))
                                link_elements = driver.find_elements(By.CSS_SELECTOR, "a.search-link, a.search-title") # Broader link selection
                                print(f"        - Found {len(link_elements)} potential result links for this query.")

                                count = 0
                                for link_element in link_elements:
                                    href = link_element.get_attribute('href')
                                    # Check if it's a valid post link, not already seen
                                    if href and '/comments/' in href and subreddit_name in href and href not in all_post_links_for_subreddit:
                                         # Simple check to avoid user profile links if possible
                                        if '/user/' not in href:
                                             all_post_links_for_subreddit.add(href)
                                             count += 1
                                print(f"        - Added {count} new unique post links for this query.")

                            except TimeoutException:
                                print(f"        - Timeout/No results found for query: '{search_query}'")
                                log_to_file(f"Selenium Timeout/No Results: r/{subreddit_name}, Query: '{search_query}'")
                            except Exception as search_e:
                                print(f"        - Error extracting search results for query '{search_query}': {search_e}")
                                log_to_file(f"Selenium Error extracting search results: r/{subreddit_name}, Query: '{search_query}': {search_e}")
                            finally:
                                time.sleep(random.uniform(1, 2)) # Delay between searches

                    # --- Scrape Collected Post Links ---
                    unique_post_links = list(all_post_links_for_subreddit)
                    print(f"    - Total unique post links found: {len(unique_post_links)}")
                    links_to_scrape = unique_post_links[:source_scrape_limit]
                    print(f"    - Scraping top {len(links_to_scrape)} posts (Limit: {source_scrape_limit})...")

                    if not links_to_scrape: print("    - No relevant post links found to scrape.")

                    for post_idx, post_url in enumerate(links_to_scrape, 1):
                        if post_url in seen_urls_global:
                            print(f"      - Post {post_idx}: Skipping already scraped URL (globally): {post_url}")
                            continue
                        # No need to check source_texts_count limit here, already limited by links_to_scrape

                        print(f"      - Post {post_idx}: Scraping {post_url}")
                        try:
                            driver.get(post_url)
                            time.sleep(random.uniform(2.5, 4.5))

                            post_title = "N/A"; post_body = ""; comment_texts = []
                            # Title (old reddit)
                            try:
                                title_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "p.title a.title")))
                                post_title = title_element.text.strip()
                            except Exception: print("        - Warning: Could not find post title.")
                            # Body (old reddit)
                            try:
                                # Look for selftext md first, then expando
                                body_elements = driver.find_elements(By.CSS_SELECTOR, "div.entry div.expando div.md")
                                if body_elements:
                                    post_body = body_elements[0].text.strip()
                            except Exception: pass # Ignore if no body
                            # Comments (old reddit)
                            try:
                                comment_limit = args.max_reddit_comments
                                print(f"        - Extracting top {comment_limit} comments...")
                                # Target the main paragraph within each comment body
                                comment_elements = driver.find_elements(By.CSS_SELECTOR, "div.commentarea .comment .md p")
                                collected_comments = 0
                                for p_element in comment_elements:
                                     if collected_comments >= comment_limit: break
                                     comment_text = p_element.text.strip()
                                     # Basic filtering: non-empty, not just '[deleted]' or '[removed]'
                                     if comment_text and comment_text.lower() not in ('[deleted]', '[removed]'):
                                        comment_texts.append(comment_text)
                                        collected_comments += 1
                                print(f"        - Extracted {len(comment_texts)} valid comment paragraphs.")
                            except Exception as comment_e: print(f"        - Warning: Error extracting comments: {comment_e}")

                            # Combine content
                            full_content = (f"Source: Reddit (r/{subreddit_name})\n"
                                            f"Permalink: {post_url}\n"
                                            f"Title: {post_title}\n\n"
                                            f"Body:\n{post_body if post_body else '[No Body Text]'}\n\n"
                                            f"--- Comments ({len(comment_texts)} scraped) ---\n" +
                                            "\n\n---\n\n".join(comment_texts)) # Use double newline between comments
                            content_length = len(full_content)
                            min_length = 100 # Lower min length for Reddit posts

                            if content_length > min_length:
                                # Append dict with url and content for consistency
                                reddit_data.append({"url": post_url, "content": full_content.strip()})
                                seen_urls_global.add(post_url)
                                source_texts_count += 1 # Counts successful POST scrapes
                                print(f"        - Success: Scraped content ({content_length} chars).")
                                log_to_file(f"Selenium scrape success: {post_url} ({content_length} chars)")
                            else:
                                print(f"        - Warning: Scraped content too short ({content_length} chars, min {min_length}). Skipping post.")
                                log_to_file(f"Selenium scrape warning (too short): {post_url} ({content_length} chars)")

                        except TimeoutException:
                            print(f"      - Post {post_idx}: Timeout loading post page: {post_url}")
                            log_to_file(f"Selenium Timeout loading post page: {post_url}")
                        except Exception as post_e:
                            print(f"      - Post {post_idx}: Error processing post page {post_url}: {post_e}")
                            log_to_file(f"Selenium Error processing post page {post_url}: {post_e}")
                        finally:
                             time.sleep(random.uniform(1.5, 3)) # Delay between posts

                except Exception as selenium_e:
                   print(f"    - An error occurred during Selenium processing for r/{subreddit_name}: {selenium_e}")
                   log_to_file(f"Selenium Error processing source r/{subreddit_name}: {selenium_e}")
                finally:
                   if driver:
                       print("    - Quitting Selenium WebDriver for this source.")
                       driver.quit()

                scraped_data.extend(reddit_data) # Add all collected dicts for this subreddit

            # --- Handle Website Sources (Search API + Newspaper4k) ---
            elif is_website_source:
                print(f"  - Type: Website Source (Requires Search)")
                if args.no_search:
                    print(f"  - Warning: Skipping website source '{item}' because --no-search is active.")
                    log_to_file(f"Scraping Warning: Skipped website source {item} due to --no-search.")
                    continue

                source_scrape_limit = args.max_web_results # Limit on URLS per domain
                domain = urllib.parse.urlparse(item).netloc or item
                print(f"  - Processing domain: {domain} (Original source suggestion: {item})")
                log_to_file(f"Processing website source: {domain} (Original: {item})")
                urls_to_scrape_for_domain = set()

                search_targets = args.search_queries
                results_limit_per_api_call = args.per_keyword_results

                # --- Search APIs ---
                if not search_targets:
                    print("    - Warning: No search queries defined for website source. Cannot find specific articles.")
                    log_to_file(f"Scraping Warning: No search queries for website source {domain}")
                else:
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

                        quota_hit = api_results == 'quota_error'
                        failed = api_results is None

                        if quota_hit: print(f"      - Primary API '{primary_api}' quota limit hit.")
                        elif failed: print(f"      - Primary API '{primary_api}' failed or returned no results.")

                        # Attempt Fallback API if primary failed (not due to quota initially) or hit quota
                        if failed or quota_hit:
                            print(f"      - Attempting fallback API: {fallback_api}")
                            if fallback_api == 'google':
                                api_results_fallback = search_google_api(current_query_for_api, config, results_limit_per_api_call, args.from_date, args.to_date)
                            else: # brave
                                api_results_fallback = search_brave_api(current_query_for_api, config, results_limit_per_api_call, args.from_date, args.to_date)

                            # Decide which results to use (prefer fallback if primary failed, handle double quota)
                            if api_results_fallback == 'quota_error':
                                print(f"      - Fallback API '{fallback_api}' also hit quota limit.")
                                if quota_hit: api_results = None # Both hit quota, give up
                                # else: keep original primary results if they existed before quota hit (unlikely scenario)
                            elif api_results_fallback is None:
                                print(f"      - Fallback API '{fallback_api}' also failed or returned no results.")
                                if quota_hit: api_results = None # Primary hit quota, fallback failed
                                # else: keep original primary results if they existed and weren't quota error
                            elif isinstance(api_results_fallback, list):
                                print(f"      - Fallback API '{fallback_api}' succeeded.")
                                api_results = api_results_fallback # Use fallback results
                            # If fallback was None/Error, api_results retains its state from primary attempt

                        # Add successfully found URLs
                        if isinstance(api_results, list):
                            added_count = 0
                            for url in api_results:
                                if url not in urls_to_scrape_for_domain and url not in seen_urls_global:
                                    urls_to_scrape_for_domain.add(url)
                                    added_count += 1
                            print(f"      - Added {added_count} new unique URLs from API search.")
                            log_to_file(f"API Search: Added {added_count} URLs for query '{current_query_for_api}' on site {domain}")
                        else:
                            print(f"      - No URLs obtained from APIs for this query.")
                            log_to_file(f"API Search Failed/Empty for query '{current_query_for_api}' on site {domain}")

                        time.sleep(random.uniform(1, 2)) # Delay between API calls

                # --- Scrape Content from URLs ---
                unique_urls_list = list(urls_to_scrape_for_domain)
                print(f"    - Total unique URLs found for domain '{domain}': {len(unique_urls_list)}")
                urls_to_process = unique_urls_list[:source_scrape_limit] # Apply overall limit per domain
                print(f"    - Attempting to scrape top {len(urls_to_process)} URLs (Limit: {source_scrape_limit})...")

                for url_idx, url in enumerate(urls_to_process, 1):
                    if url in seen_urls_global:
                        print(f"      - URL {url_idx}: Skipping already scraped URL (globally): {url}")
                        continue
                    # Limit already applied by urls_to_process slice

                    print(f"      - URL {url_idx}: ", end="") # scrape_website_url will add details
                    scraped_text = scrape_website_url(url)
                    if scraped_text:
                        scraped_data.append(scraped_text) # Use scraped_data
                        seen_urls_global.add(url)
                        source_texts_count += 1
                    # scrape_website_url handles its own logging/printing

            else:
                print(f"  - Warning: Could not determine type for item: {item}. Skipping.")
                log_to_file(f"Scraping Warning: Unknown item type: {item}")

        except Exception as item_e:
            print(f"\nError processing item '{item}': {item_e}")
            log_to_file(f"Scraping Error: Unexpected error processing item '{item}': {item_e}")
            import traceback
            log_to_file(f"Traceback:\n{traceback.format_exc()}") # Log traceback for item errors

        print(f"  - Finished item: {item}. Scraped {source_texts_count} piece(s) for this item.")
        if i < len(sources_or_urls):
            delay = random.uniform(2, 5) # Slightly shorter delay between sources
            print(f"--- Delaying {delay:.2f}s before next source ---")
            time.sleep(delay)

    print(f"\n--- Finished Scraping Phase. Total unique content pieces gathered: {len(scraped_data)} ---") # Use scraped_data
    log_to_file(f"Scraping phase complete. Gathered {len(scraped_data)} content pieces.") # Use scraped_data
    return scraped_data # Use scraped_data