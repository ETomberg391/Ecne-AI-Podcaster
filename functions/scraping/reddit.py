import time
import random
import urllib.parse
import os # Import os module
import time
import random
import urllib.parse
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from ..utils import log_to_file, USER_AGENTS # Import utilities

def scrape_reddit_source(subreddit_name, search_queries, args, seen_urls_global, source_scrape_limit):
    """
    Scrapes content from a specific subreddit using Selenium.
    Returns a list of scraped text content from posts/comments.
    Updates the seen_urls_global set.
    """
    print(f"  - Processing Reddit source '{subreddit_name}' using Selenium/old.reddit.com...")
    log_to_file(f"Initiating Selenium scrape for r/{subreddit_name}")
    driver = None
    all_post_links_for_subreddit = set()
    reddit_texts = [] # Store texts scraped from this source
    source_texts_count = 0 # Track count for this source

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
        return [] # Return empty list if chromedriver is not found

    try:
        options = webdriver.ChromeOptions()
        options.add_argument('--headless'); options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
        options.add_argument(f'user-agent={random.choice(USER_AGENTS)}')
        
        # Use ChromeService to specify the executable path
        service = ChromeService(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
        
        wait = WebDriverWait(driver, 20) # Consider making timeout configurable
        print("    - Selenium WebDriver initialized using venv chromedriver.")

        # --- Perform Search for Each Keyword Query ---
        for query_idx, search_query in enumerate(search_queries):
            print(f"      - Searching subreddit '{subreddit_name}' for query {query_idx+1}/{len(search_queries)}: '{search_query}'")
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

    except Exception as selenium_e:
        print(f"    - An error occurred during Selenium processing for r/{subreddit_name}: {selenium_e}")
        log_to_file(f"Selenium Error processing source r/{subreddit_name}: {selenium_e}")
    finally:
        if driver:
            print("    - Quitting Selenium WebDriver.")
            driver.quit()

    print(f"  - Finished processing Reddit source r/{subreddit_name}. Scraped {source_texts_count} piece(s).")
    return reddit_texts