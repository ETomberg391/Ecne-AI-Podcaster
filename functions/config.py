import os
import yaml
import json # Although json is not directly used in these functions, it's used in call_ai_api which relies on config.
from dotenv import load_dotenv
from .utils import log_to_file # Import log_to_file from the new utils module

# Define script directory and LLM directory relative to this new structure
# Assuming the new_script_builder.py will be in new_style/
# And settings are still relative to the original Ecne-AI-Podcaster directory.
# We need to adjust paths accordingly.
# The original SCRIPT_DIR was os.path.dirname(__file__) from Ecne-AI-Podcaster/script_builder.py
# The new script will be in new_style/, so relative paths need adjustment.
# Let's assume the settings directory remains relative to the project base
NEW_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) # Directory of this file (e.g., .../Ecne-AI-Podcasterv2/functions)
# Go up one level from the functions directory to reach the project root (e.g., .../Ecne-AI-Podcasterv2)
PROJECT_BASE_DIR = os.path.abspath(os.path.join(NEW_SCRIPT_DIR, '..'))
LLM_DIR = os.path.join(PROJECT_BASE_DIR, "settings/llm_settings")


def load_config():
    """Loads configuration from .env file and ai_models.yml."""
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
        log_to_file(f"Loaded model configurations from {models_config_path}")
    except FileNotFoundError:
        print(f"Error: Model configuration file not found at {models_config_path}")
        log_to_file(f"Error: Model configuration file not found at {models_config_path}")
        # In a modular structure, we might return None or raise a specific error
        # For now, maintaining original behavior of exiting
        exit(1)
    except (yaml.YAMLError, ValueError) as e:
        print(f"Error parsing model configuration file {models_config_path}: {e}")
        log_to_file(f"Error parsing model configuration file {models_config_path}: {e}")
        exit(1)

    # NOTE: Model selection logic moved to main() after args parsing

    # Basic validation
    # Check search APIs
    google_ok = config.get("google_api_key") and config.get("google_cse_id")
    brave_ok = config.get("brave_api_key")
    if not google_ok and not brave_ok:
         print("Warning: Neither Google (API Key + CSE ID) nor Brave API Key are set. Web search will fail.")
         log_to_file("Warning: Neither Google (API Key + CSE ID) nor Brave API Key are set. Web search will fail.")

    # Check Reddit API creds
    reddit_ok = all(config.get(k) for k in ["reddit_client_id", "reddit_client_secret", "reddit_user_agent"])
    if not reddit_ok:
        print("Warning: Reddit credentials (client_id, client_secret, user_agent) missing in .env. Reddit scraping via PRAW will fail.")
        log_to_file("Warning: Reddit credentials (client_id, client_secret, user_agent) missing in .env. Reddit scraping via PRAW will fail.")

    print("Configuration loaded.")
    log_to_file("Configuration loaded successfully.")
    # Return both basic config and the loaded models dictionary
    return config, models_config

def load_character_profile(filepath):
    """Loads character profile from a YAML file."""
    try:
        print(f"Loading character profile from {filepath}")
        log_to_file(f"Attempting to load character profile from {filepath}")
        with open(filepath, 'r', encoding='utf-8') as f:
            profile = yaml.safe_load(f)
            # Ensure podcast name is loaded if present
            if 'podcast_name' not in profile:
                 print(f"Warning: 'podcast_name' not found in profile {filepath}. Using default.")
                 log_to_file(f"Warning: 'podcast_name' not found in profile {filepath}. Using default.")
                 profile.setdefault('podcast_name', 'Podcast') # Default if missing
            print(f"Loaded character profile from {filepath}")
            log_to_file(f"Successfully loaded character profile from {filepath}")
            return profile
    except FileNotFoundError:
        print(f"Error: Character profile file not found at {filepath}")
        log_to_file(f"Error: Character profile file not found at {filepath}")
        return None
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file {filepath}: {e}")
        log_to_file(f"Error parsing YAML file {filepath}: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred loading {filepath}: {e}")
        log_to_file(f"An unexpected error occurred loading {filepath}: {e}")
        return None