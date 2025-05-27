import os
import datetime
import re
import random # Required for USER_AGENTS

# Global variable for archive directory (set in main)
run_archive_dir = None

def set_run_archive_dir(path):
    """Sets the global run_archive_dir variable."""
    global run_archive_dir
    run_archive_dir = path

# User agents for requests/scraping
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
]

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