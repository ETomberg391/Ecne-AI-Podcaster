import os
import re

from ..ai import call_ai_api # Import call_ai_api from the new ai module
from ..utils import log_to_file, clean_thinking_tags, parse_ai_tool_response, run_archive_dir # Import utilities including run_archive_dir

def summarize_content(scraped_texts, reference_docs_content, topic, config, args):
    """
    Uses AI to summarize scraped content and optionally reference documents,
    assigning a relevance score to each.
    """
    content_to_process = []
    # Add scraped texts with a type identifier
    for idx, text in enumerate(scraped_texts):
        content_to_process.append({"type": "scraped", "content": text, "source_index": idx + 1})

    # Add reference docs if summarization is requested
    if args.reference_docs_summarize and reference_docs_content:
        print(f"Including {len(reference_docs_content)} reference documents in summarization.")
        log_to_file(f"Including {len(reference_docs_content)} reference documents in summarization.")
        for doc in reference_docs_content:
             content_to_process.append({"type": "reference", "content": doc["content"], "path": doc["path"]})
    elif reference_docs_content:
         print(f"Skipping summarization for {len(reference_docs_content)} reference documents as --reference-docs-summarize is not set.")
         log_to_file(f"Skipping summarization for {len(reference_docs_content)} reference documents.")


    total_pieces = len(content_to_process)
    if total_pieces == 0:
        print("\nWarning: No content (scraped or reference for summarization) available to summarize.")
        log_to_file("Summarization Warning: No content found to process.")
        return [] # Return empty list if nothing to do

    print(f"\nSummarizing {total_pieces} content piece(s)...")
    log_to_file(f"Starting summarization for {total_pieces} piece(s). Topic: {topic}")
    summaries_with_scores = []
    successful_summaries = 0

    for i, item in enumerate(content_to_process, 1):
        text = item["content"]
        item_type = item["type"]
        item_source_id = item.get("path", f"Scraped_{item.get('source_index', i)}") # Use path for ref docs, index for scraped

        if len(text) < 100: # Increased minimum length
            print(f"\rSkipping summary for short text piece {i}/{total_pieces} ({item_source_id}).", end='', flush=True)
            log_to_file(f"Summary {i}/{total_pieces} ({item_source_id}) skipped (too short: {len(text)} chars).")
            continue

        # Show progress
        print(f"\rSummarizing & Scoring {i}/{total_pieces} ({item_type}) (Completed: {successful_summaries})", end='', flush=True)

        # Limit text size sent to AI if necessary (check API limits)
        max_summary_input_chars = 150000 # Example limit, adjust as needed
        truncated_text = text[:max_summary_input_chars]
        if len(text) > max_summary_input_chars:
            log_to_file(f"Warning: Summary {i} ({item_source_id}) input text truncated to {max_summary_input_chars} chars.")

        guidance_text = f"\n**Additional Guidance:** {args.guidance}\n" if args.guidance else ""
        prompt = (
            f"Please provide a concise yet comprehensive summary of the following text. Focus on the key information, main arguments, findings, and any specific data points (statistics, percentages, benchmark results, dates, names) relevant to the main topic.\n"
            f"**Main Topic:** {topic}{guidance_text}\n"
            f"**Text to Summarize:**\n---\n{truncated_text}\n---\n\n"
            f"**Instructions:**\n"
            f"1. Format your summary *only* within <toolScrapeSummary> tags.\n"
            f"2. After the summary tag, provide a relevance score (integer 0-10) indicating how relevant the *summary* is to the Main Topic ('{topic}') and adheres to any Additional Guidance provided. Enclose the score *only* in <summaryScore> tags.\n\n"
            f"**Example Response Structure:**\n"
            f"<toolScrapeSummary>This is a concise summary preserving key details like a 95% accuracy rate achieved in 2023 according to Dr. Smith.</toolScrapeSummary>\n"
            f"<summaryScore>8</summaryScore>"
        )

        raw_response, cleaned_response = call_ai_api(prompt, config, tool_name=f"Summary_{i}_{item_type}", timeout=3000) # Shorter timeout, added type

        summary = "Error: Summarization Failed"
        score = -1 # Default score
        summary_details = {"type": item_type, "source_id": item_source_id} # Store type and source id

        if cleaned_response:
            parsed_summary = parse_ai_tool_response(cleaned_response, "toolScrapeSummary")
            # Check if parsing returned the whole response (tag missing)
            if parsed_summary == cleaned_response and '<toolScrapeSummary>' not in cleaned_response:
                 log_to_file(f"Error: Summary {i} ({item_source_id}) parsing failed - <toolScrapeSummary> tag missing.")
                 summary = f"Error: Could not parse summary {i} ({item_source_id}) (<toolScrapeSummary> tag missing)"
            elif not parsed_summary:
                 log_to_file(f"Error: Summary {i} ({item_source_id}) parsing failed - No content found in <toolScrapeSummary> tag.")
                 summary = f"Error: Could not parse summary {i} ({item_source_id}) (empty tag)"
            else:
                 summary = parsed_summary # Use parsed summary

            # Extract score robustly
            score_match = re.search(r'<summaryScore>(\d{1,2})</summaryScore>', cleaned_response, re.IGNORECASE)
            if score_match:
                try:
                    parsed_score = int(score_match.group(1))
                    if 0 <= parsed_score <= 10:
                        score = parsed_score
                        successful_summaries += 1 # Count success only if score is valid
                    else:
                        log_to_file(f"Warning: Summary {i} ({item_source_id}) score '{parsed_score}' out of range (0-10). Using -1.")
                except ValueError:
                    log_to_file(f"Warning: Could not parse summary {i} ({item_source_id}) score '{score_match.group(1)}'. Using -1.")
            else:
                 log_to_file(f"Warning: Could not find/parse <summaryScore> tag for summary {i} ({item_source_id}). Using -1.")

        else: # API call itself failed
            log_to_file(f"Error: API call failed for Summary_{i} ({item_source_id})")
            summary = f"Error: Could not summarize text piece {i} ({item_source_id}) (API call failed)"

        # Add summary and score along with type and source identifier
        summary_details = {"type": item_type, "source_id": item_source_id, 'summary': summary, 'score': score}
        summaries_with_scores.append(summary_details)

        # Save the summary text to archive regardless of score validity
        if run_archive_dir:
            # Create a more descriptive filename
            safe_source_id = re.sub(r'[\\/*?:"<>|]', "_", str(item_source_id)) # Sanitize filename chars
            summary_filename = os.path.join(run_archive_dir, f"summary_{i}_{item_type}_{safe_source_id[:50]}.txt") # Truncate long paths
            try:
                with open(summary_filename, 'w', encoding='utf-8') as sf:
                    sf.write(f"Source: {item_source_id}\nType: {item_type}\nScore: {score}\n\n{summary}")
            except IOError as e:
                log_to_file(f"Warning: Could not save summary {i} ({item_source_id}) to file {summary_filename}: {e}")


    # Final status update
    print(f"\rSummarization & Scoring complete. Generated {successful_summaries}/{total_pieces} summaries successfully (with valid scores).")
    log_to_file(f"Summarization phase complete. Successful summaries (with score): {successful_summaries}/{total_pieces}")
    return summaries_with_scores