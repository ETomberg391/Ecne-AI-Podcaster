import os
import datetime
import time
import re
import traceback # For printing tracebacks
import random # For random delays in scraping (though scrape_content handles this now)
import shutil

# Import functions from the new modular structure
from functions.config import load_config, load_character_profile
from functions.args import parse_arguments
from functions.search.discovery import discover_sources
from functions.scraping.content import scrape_content
from functions.scraping.documents import load_reference_documents
from functions.processing.summarization import summarize_content
from functions.processing.report_generation import generate_report
from functions.processing.youtube_descriptor import generate_youtube_description
from functions.processing.script_generation import generate_and_refine_script
from functions.utils import log_to_file, run_archive_dir, set_run_archive_dir, close_log_file

# --- Audio Synthesis (Placeholder) ---
# This function is a placeholder and will be moved here from the original script.
def synthesize_audio(script_text_filepath, run_archive_dir):
    """Synthesizes audio from the script text file using TTS (Placeholder)."""
    print("\nSynthesizing audio (Placeholder)...")
    log_to_file("Starting audio synthesis phase (Placeholder).")
    if not script_text_filepath or not os.path.exists(script_text_filepath):
        print("Error: Script text file path is invalid or file does not exist.")
        log_to_file("Audio Synth Error: Script file not found or path invalid.")
        return None

    # TODO: Implement actual TTS integration (e.g., StyleTTS 2, CoquiTTS, Piper, etc.)
    #   - Parse script_text_filepath line by line (Host: ..., Guest: ...)
    #   - Select appropriate voice model/speaker based on Host/Guest
    #   - Synthesize each line to a temporary audio segment
    #   - Concatenate segments using pydub or similar
    #   - Add intro/outro music if desired
    #   - Export final audio file

    # Placeholder: Create an empty file
    output_filename = "podcast_final_audio.mp3"
    final_audio_path = os.path.join(run_archive_dir, output_filename) if run_archive_dir else output_filename

    print(f"Placeholder: Audio would be saved to {final_audio_path}")
    try:
        with open(final_audio_path, 'w') as f:
            f.write("Placeholder audio content generated by new_script_builder.py.")
        print(f"Simulated audio file created: {final_audio_path}")
        log_to_file(f"Audio synthesis placeholder complete. Simulated file: {final_audio_path}")
        return final_audio_path
    except IOError as e:
        print(f"Error creating placeholder audio file: {e}")
        log_to_file(f"Audio Synth Error: Failed to create placeholder file {final_audio_path}: {e}")
        return None


# --- Main Execution ---

def main():
    """Main function to orchestrate the podcast generation workflow."""
    # run_archive_dir will be defined locally in this function

    print("--- Starting AI Podcast Generator (Refactored) ---")
    start_time = time.time()

    # --- Setup ---
    # script_dir is now the directory of this script (new_style/)
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Load configuration and models
    env_config, models_config = load_config() # Unpack the tuple

    # Parse arguments (args.py handles loading model keys dynamically)
    args = parse_arguments()

    # --- Determine Final Model Configuration ---
    # Priority: Command Line (--llm-model) > Environment Variable (DEFAULT_MODEL_CONFIG) > Default ('default_model')
    final_model_key = "default_model" # Ultimate fallback
    env_model_key = os.getenv("DEFAULT_MODEL_CONFIG")

    if args.llm_model:
        final_model_key = args.llm_model
        print(f"Using LLM model specified via command line: '{final_model_key}'")
        # Store the finally chosen key in config for potential reference later (e.g., in call_ai_api error messages)
        env_config['final_model_key'] = final_model_key # Use env_config dict
        log_to_file(f"Model Selection: Using command line override: '{final_model_key}'")
    elif env_model_key:
        final_model_key = env_model_key
        print(f"Using LLM model specified via .env: '{final_model_key}'")
        env_config['final_model_key'] = final_model_key # Use env_config dict
        log_to_file(f"Model Selection: Using .env setting: '{final_model_key}'")
    else:
        print(f"Using default LLM model: '{final_model_key}' (Neither --llm-model nor DEFAULT_MODEL_CONFIG set)")
        env_config['final_model_key'] = final_model_key # Use env_config dict
        log_to_file(f"Model Selection: Using default: '{final_model_key}'")

    # Validate the final key and get the configuration from the already loaded models_config
    final_model_config = models_config.get(final_model_key)
    if not final_model_config or not isinstance(final_model_config, dict):
        print(f"Error: Final selected model key '{final_model_key}' configuration not found or invalid in ai_models.yml")
        print(f"Available configurations: {list(models_config.keys())}")
        log_to_file(f"Run Error: Invalid final model key selected: '{final_model_key}'")
        exit(1)
    if 'model' not in final_model_config:
        print(f"Error: 'model' name is missing in the configuration for '{final_model_key}' in ai_models.yml")
        log_to_file(f"Run Error: 'model' name missing for selected config key: '{final_model_key}'")
        exit(1)

    # Store the final selected config back into the main config dict for use by call_ai_api
    env_config["selected_model_config"] = final_model_config # Use env_config dict
    log_to_file(f"Final Model Config Used: {final_model_config}")
    # --- End Final Model Configuration Determination ---


    topic_slug = re.sub(r'\W+', '_', args.topic)[:50] # Sanitize topic for dir name
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # Define the base archive directory within the current script's directory (Ecne-AI-Podcasterv2)
    outputs_dir = os.path.join(script_dir, "outputs")
    # Create all necessary output directories at the start
    os.makedirs(os.path.join(outputs_dir, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(outputs_dir, "reports"), exist_ok=True)
    os.makedirs(os.path.join(outputs_dir, "youtube_descriptions"), exist_ok=True)
    os.makedirs(os.path.join(outputs_dir, "archive", "script_builder_archive"), exist_ok=True)

    run_archive_dir = os.path.join(outputs_dir, f"{timestamp}_{topic_slug}") # Define run_archive_dir here

    try:
        os.makedirs(run_archive_dir, exist_ok=True)
        print(f"Created temporary run directory: {run_archive_dir}")
        # Set the global run_archive_dir in utils
        set_run_archive_dir(run_archive_dir)
        # Initialize log file for this run
        log_to_file(f"--- AI Podcast Generator Run Start ({timestamp}) ---")
        log_to_file(f"Args: {vars(args)}")
        log_to_file(f"Env Config Keys Loaded: {list(env_config.keys())}") # Log env_config keys
        log_to_file(f"Model Config Keys Loaded: {list(models_config.keys())}") # Log models_config keys
    except OSError as e:
        print(f"Error creating archive directory {run_archive_dir}: {e}")
        # Reset the local run_archive_dir to None if creation fails
        run_archive_dir = None
        # Also reset the global one in utils
        set_run_archive_dir(None)
        log_to_file("Error: Failed to create archive directory. Archiving disabled for this run.")


    # Load Character Profiles
    # Character profiles are still relative to the original project's settings directory
    host_profile_path = os.path.join(script_dir, 'settings', 'characters', 'host.yml')
    guest_profile_path = os.path.join(script_dir, 'settings', 'characters', 'guest.yml')

    host_profile = load_character_profile(host_profile_path)
    guest_profile = load_character_profile(guest_profile_path)

    if not host_profile or not guest_profile:
        print("Error: Failed to load character profiles. Exiting.")
        log_to_file("Run Error: Failed to load character profiles.")
        exit(1)
    log_to_file(f"Host Profile loaded: {host_profile}")
    log_to_file(f"Guest Profile loaded: {guest_profile}")


    # --- Workflow Steps ---
    try:
        # 1. Load Reference Documents
        # load_reference_documents now handles both --reference-docs and --reference-docs-folder
        reference_docs_content = load_reference_documents(args)
        if not reference_docs_content and (args.reference_docs or args.reference_docs_folder):
             print("Warning: No valid reference documents were loaded from specified paths or folder.")
             log_to_file("Warning: Reference docs/folder specified, but no content loaded.")

        # 2. Load Direct Articles (if specified)
        direct_article_urls = []
        if args.direct_articles:
            print(f"\nLoading direct articles from: {args.direct_articles}")
            log_to_file(f"Attempting to load direct articles from {args.direct_articles}")
            try:
                with open(args.direct_articles, 'r', encoding='utf-8') as f:
                    direct_article_urls = [line.strip() for line in f if line.strip() and line.strip().startswith(('http://', 'https://'))]
                if direct_article_urls:
                    print(f"Successfully loaded {len(direct_article_urls)} direct article URLs.")
                    log_to_file(f"Loaded {len(direct_article_urls)} direct URLs: {direct_article_urls}")
                else:
                    print(f"Warning: File {args.direct_articles} was empty or contained no valid URLs.")
                    log_to_file(f"Warning: Direct articles file {args.direct_articles} empty or invalid.")
            except FileNotFoundError:
                print(f"Error: Direct articles file not found: {args.direct_articles}")
                log_to_file(f"Error: Direct articles file not found: {args.direct_articles}")
                if args.no_search: # Critical if no search is allowed
                     raise FileNotFoundError(f"Direct articles file '{args.direct_articles}' not found, and --no-search was specified.")
                # If search is allowed, we can potentially continue without direct articles
            except Exception as e:
                print(f"Error reading direct articles file {args.direct_articles}: {e}")
                log_to_file(f"Error reading direct articles file {args.direct_articles}: {e}")
                if args.no_search: # Critical if no search is allowed
                     raise IOError(f"Failed to read direct articles file '{args.direct_articles}' due to error: {e}, and --no-search was specified.")

        # 3. Determine Sources/URLs to Scrape (and potentially discover sources)
        sources_for_scraping = [] # URLs/Subreddits to actually scrape
        if args.no_search:
            print("--no-search specified. Skipping source discovery and web search.")
            log_to_file("Source Determination: --no-search active. Skipping discovery/web search.")
            # Use only direct articles for scraping, if provided. Reference docs are handled separately.
            sources_for_scraping = direct_article_urls
            if sources_for_scraping:
                 print(f"Using {len(sources_for_scraping)} URLs from --direct-articles for scraping.")
                 log_to_file(f"Source Determination: Using {len(sources_for_scraping)} direct URLs for scraping.")
            else:
                 print("No direct articles provided via --direct-articles. Skipping scraping phase.")
                 log_to_file("Source Determination: No direct articles provided. Skipping scraping phase.")
            # Argument parser already ensures we have *some* offline content (direct_articles OR reference_docs OR reference_docs_folder)
        else:
            # Search is active, discover sources if needed
            print("Discovering sources via AI and combining with direct articles (if any)...")
            log_to_file("Source Determination: Discovering sources and combining with direct articles.")
            # Keywords are required here (validated by parser)
            discovered_sources = discover_sources(args.search_queries, env_config, args) # Pass env_config and args

            # Combine and deduplicate sources for scraping
            combined_sources = direct_article_urls + discovered_sources # Prioritize direct URLs
            seen_sources = set()
            unique_combined_sources = []
            for src in combined_sources:
                normalized_src = src # Keep original for now, simple exact match dedupe
                if normalized_src not in seen_sources:
                    unique_combined_sources.append(src)
                    seen_sources.add(normalized_src)

            sources_for_scraping = unique_combined_sources
            print(f"Combined sources for scraping: {len(sources_for_scraping)} unique sources/URLs.")
            log_to_file(f"Source Determination: Combined {len(discovered_sources)} discovered sources with {len(direct_article_urls)} direct URLs, resulting in {len(sources_for_scraping)} unique items for scraping.")

            if not sources_for_scraping and not reference_docs_content:
                 # If search was active but we found no sources AND have no reference docs, we can't proceed.
                 raise RuntimeError("No valid sources were discovered or provided directly, and no reference documents loaded. Cannot proceed.")
            elif not sources_for_scraping:
                 print("Warning: No sources discovered or provided for scraping, but proceeding with reference documents.")
                 log_to_file("Warning: No sources found for scraping, using only reference docs.")


        # 4. Scrape Content (only if sources_for_scraping is not empty)
        scraped_content = []
        if sources_for_scraping:
            scraped_content = scrape_content(sources_for_scraping, direct_article_urls, args, env_config) # Pass list of URLs/sources
            if not scraped_content and not reference_docs_content:
                 # If scraping failed AND we have no reference docs, we can't proceed.
                 raise RuntimeError("Failed to scrape any content from the provided/discovered sources, and no reference documents loaded.")
            elif not scraped_content:
                  print("Warning: Failed to scrape any content, but proceeding with reference documents.")
                  log_to_file("Warning: Scraping failed, using only reference docs.")
        else:
             print("Skipping content scraping as no sources were provided/discovered for it.")
             # We proceed here because reference_docs_content might still exist

        # Check if we have ANY content (scraped or reference) before summarizing
        if not scraped_content and not reference_docs_content:
             raise RuntimeError("No content available from scraping or reference documents. Cannot proceed.")

        # 5. Summarize Content (scraped and/or reference docs if --reference-docs-summarize)
        # Pass both scraped_content and reference_docs_content to summarize_content
        summaries = summarize_content(scraped_content, reference_docs_content, args.topic, env_config, args)
        # Summarize_content now handles logic for reference docs internally based on args.reference_docs_summarize

        # --- Filter Summaries by Score ---
        relevant_summaries = [s for s in summaries if s['score'] >= args.score_threshold and not s['summary'].startswith("Error:")]
        print(f"\nFiltered summaries. Using {len(relevant_summaries)} summaries with score >= {args.score_threshold} for script generation.")
        log_to_file(f"Filtered summaries. Using {len(relevant_summaries)} summaries with score >= {args.score_threshold}.")

        # Check if ANY relevant content (filtered summaries OR non-summarized reference docs) exists
        have_relevant_summaries = len(relevant_summaries) > 0
        have_nonsummarized_ref_docs = reference_docs_content and not args.reference_docs_summarize

        if not have_relevant_summaries and not have_nonsummarized_ref_docs:
             raise RuntimeError(f"No summaries met the threshold ({args.score_threshold}), and no reference documents were provided/processed for direct use. Cannot proceed.")
        elif not have_relevant_summaries:
             print(f"Warning: No summaries met the threshold ({args.score_threshold}). Script will rely solely on reference documents (if any).")
             log_to_file(f"Warning: No summaries met threshold {args.score_threshold}. Using only reference docs for script.")


        # Renumbering subsequent steps mentally
        # 6. Generate Report (Optional)
        report_filepath_temp = None
        if args.report:
            # Pass relevant_summaries AND reference_docs_content to generate_report
            report_filepath_temp = generate_report(relevant_summaries, reference_docs_content, args.topic, env_config, args)
            if report_filepath_temp:
                print(f"\nSuccessfully generated report: {report_filepath_temp}")
            else:
                print("\nWarning: Report generation failed, but continuing with script generation.")
                log_to_file("Warning: Report generation failed.")

        # 6.5. Generate YouTube Description (Optional, requires report)
        youtube_desc_filepath_temp = None # Initialize
        if args.youtube_description:
            if report_filepath_temp and os.path.exists(report_filepath_temp):
                try:
                    with open(report_filepath_temp, 'r', encoding='utf-8') as rf:
                        report_content = rf.read()
                    
                    youtube_desc_filepath_temp = generate_youtube_description(report_content, args.topic, env_config, args)
                    if youtube_desc_filepath_temp:
                        print(f"\nSuccessfully generated YouTube description: {youtube_desc_filepath_temp}")
                    else:
                        print("\nWarning: YouTube description generation failed.")
                        log_to_file("Warning: YouTube description generation failed.")
                except Exception as e:
                    print(f"\nError during YouTube description generation: {e}")
                    log_to_file(f"Error during YouTube description generation: {e}")
            else:
                print("\nWarning: YouTube description generation requires a report. Skipping.")
                log_to_file("Warning: YouTube description generation skipped - no report.")

        # 7. Generate & Refine Script
        script_filepath_temp = generate_and_refine_script(relevant_summaries, reference_docs_content, args.topic, host_profile, guest_profile, env_config, args)
        if not script_filepath_temp:
            raise RuntimeError("Failed to generate or refine the podcast script.")

        # --- Archive Final Script, Report, and YouTube Description ---
        run_dir_name = os.path.basename(run_archive_dir) if run_archive_dir else f"{timestamp}_{topic_slug}"
        
        # 1. Handle Final Script
        scripts_output_dir = os.path.join(script_dir, "outputs", "scripts")
        final_script_filename = f"{run_dir_name}_podcast_script.txt"
        final_script_filepath = os.path.join(scripts_output_dir, final_script_filename)
        shutil.copy(script_filepath_temp, final_script_filepath)
        script_filepath = final_script_filepath
        print(f"Copied final script to: {script_filepath}")
        log_to_file(f"Copied final script to: {script_filepath}")

        # 2. Handle Report
        if report_filepath_temp and os.path.exists(report_filepath_temp):
            reports_output_dir = os.path.join(script_dir, "outputs", "reports")
            final_report_filename = f"{run_dir_name}_report.txt"
            final_report_filepath = os.path.join(reports_output_dir, final_report_filename)
            shutil.move(report_filepath_temp, final_report_filepath)
            print(f"Moved report to: {final_report_filepath}")
            log_to_file(f"Moved report to: {final_report_filepath}")

        # 3. Handle YouTube Description
        if youtube_desc_filepath_temp and os.path.exists(youtube_desc_filepath_temp):
            youtube_desc_output_dir = os.path.join(script_dir, "outputs", "youtube_descriptions")
            final_desc_filename = f"Youtube_{run_dir_name}.md"
            final_desc_filepath = os.path.join(youtube_desc_output_dir, final_desc_filename)
            shutil.move(youtube_desc_filepath_temp, final_desc_filepath)
            print(f"Moved YouTube description to: {final_desc_filepath}")
            log_to_file(f"Moved YouTube description to: {final_desc_filepath}")

        # Display final script (optional)
        print("\n--- Final Script ---")
        try:
            with open(script_filepath, 'r', encoding='utf-8') as f: print(f.read())
        except Exception as e: print(f"Error reading script file for display: {e}")
        print("------------------\n")

        # 8. Audio synthesis is handled by podcast_builder, not script_builder
        print("\nSkipping audio synthesis - audio handled by podcast_builder.")
        log_to_file("Audio synthesis skipped - handled by podcast_builder.")
        audio_filepath = None

        # --- Completion ---
        end_time = time.time()
        duration = end_time - start_time
        print("\n--- AI Podcast Generation Complete ---")
        if audio_filepath:
            print(f"Final Audio (Placeholder): {audio_filepath}")
        if script_filepath:
            print(f"Final Script: {script_filepath}")
        # Check if run_archive_dir was successfully created before printing
        if run_archive_dir: # Check if the local variable is not None
             print(f"Run Archive: {run_archive_dir}")
        print(f"Total Duration: {duration:.2f} seconds")
        log_to_file(f"--- AI Podcast Generator Run End --- Duration: {duration:.2f}s ---")

        # Close the log file BEFORE moving the directory
        close_log_file()

        # Move the run directory to the script builder archive
        if run_archive_dir and os.path.exists(run_archive_dir):
            script_builder_archive_dir = os.path.join(script_dir, "outputs", "archive", "script_builder_archive")
            
            new_archive_path = os.path.join(script_builder_archive_dir, os.path.basename(run_archive_dir))
            
            try:
                shutil.move(run_archive_dir, new_archive_path)
                print(f"Moved run directory to script builder archive: {new_archive_path}")
                # No more logging after this point for this run
            except Exception as e:
                print(f"Warning: Failed to move run directory to script builder archive: {e}")

    except Exception as e:
        print(f"\n--- Workflow Error ---")
        print(f"An error occurred during the podcast generation process: {e}")
        traceback.print_exc() # Print full traceback
        log_to_file(f"FATAL WORKFLOW ERROR: {e}\n{traceback.format_exc()}")
        print("----------------------")
        exit(1)


if __name__ == "__main__":
    # Ensure necessary libraries are installed
    try:
        import newspaper # newspaper4k
        import selenium
        import PyPDF2
        import docx
        import requests
        import yaml
        import dotenv
        import bs4
    except ImportError as e:
        print(f"Import Error: {e}. Please install necessary libraries.")
        print("Try running: pip install newspaper4k selenium python-dotenv PyYAML requests beautifulsoup4 pypdf python-docx") # Added pypdf and python-docx
        exit(1)

    main()
