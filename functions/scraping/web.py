import requests
import time
import random
from newspaper import Article, ArticleException # Using newspaper4k for better web scraping

from ..utils import log_to_file, USER_AGENTS # Import utilities including USER_AGENTS

def scrape_website_url(url):
    """Scrapes content from a single website URL using newspaper4k."""
    print(f"      - Scraping URL (Newspaper4k): {url}")
    log_to_file(f"Scraping website URL: {url}")
    try:
        headers = {'User-Agent': random.choice(USER_AGENTS)}
        article = Article(url, request_headers=headers, fetch_images=False)
        article.download()
        # Handle potential download errors before parsing
        # Check download state - handle both integer (old) and enum (new) formats
        download_state_value = article.download_state
        if hasattr(download_state_value, 'value'):
            # It's an enum, get the value
            download_state_value = download_state_value.value
        if download_state_value != 2: # 2 means success
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