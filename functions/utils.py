import os
import datetime
import re
import random # Required for USER_AGENTS

# Global variables to hold the current run's archive directory and log file handler
run_archive_dir = None
log_file_path = None
log_file_handler = None

def set_run_archive_dir(path):
    """Sets the global run_archive_dir and initializes the log file path."""
    global run_archive_dir, log_file_path, log_file_handler
    # Close any existing log file handler before changing paths
    if log_file_handler:
        log_file_handler.close()
        log_file_handler = None

    run_archive_dir = path
    if run_archive_dir:
        log_file_path = os.path.join(run_archive_dir, f"ai_podcast_run_{datetime.datetime.now().strftime('%Y%m%d')}.log")
        try:
            # Open the file in append mode and keep the handler
            log_file_handler = open(log_file_path, 'a', encoding='utf-8')
        except IOError as e:
            print(f"Fatal: Could not open log file for writing at {log_file_path}: {e}")
            log_file_handler = None
    else:
        log_file_path = None

# User agents for requests/scraping
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
]

def log_to_file(message):
    """Appends a message to the log file using the global file handler."""
    if not log_file_handler:
        print(f"Warning: Log file handler not available. Could not log: {message}")
        return

    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file_handler.write(f"[{timestamp}] {message}\n")
        log_file_handler.flush() # Ensure it's written to disk immediately
    except Exception as e:
        print(f"Warning: Could not write to log file {log_file_path}: {e}")

def close_log_file():
    """Closes the global log file handler."""
    global log_file_handler
    if log_file_handler:
        try:
            log_file_handler.close()
            log_file_handler = None
            print("Log file closed.")
        except Exception as e:
            print(f"Warning: Error closing log file: {e}")

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