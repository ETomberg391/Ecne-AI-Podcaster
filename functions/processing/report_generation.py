import os
import re
import json # Used for logging raw response

from ..ai import call_ai_api # Import call_ai_api from the new ai module
from ..utils import log_to_file, clean_thinking_tags # Import utilities

def generate_report(summaries_with_scores, reference_docs_content, topic, config, args):
    """Uses AI to generate a written report/paper based on summaries and optionally full reference docs."""
    # Access run_archive_dir from the global scope via utils
    from ..utils import run_archive_dir

    print("\nGenerating report via AI...")
    log_to_file(f"Starting report generation. Topic: {topic}")

    # --- Process Summaries ---
    # Use all valid summaries (which might include summarized ref docs), sorted by score
    valid_summaries = [s for s in summaries_with_scores if s['score'] >= 0 and not s['summary'].startswith("Error:")]
    num_summaries_used = 0
    combined_summaries_text = "No valid summaries were generated or met the criteria."

    if valid_summaries:
        top_summaries = sorted(valid_summaries, key=lambda x: x['score'], reverse=True)
        num_summaries_used = len(top_summaries)
        print(f"Using {num_summaries_used} summaries for report generation.")
        log_to_file(f"Report Gen: Using {num_summaries_used} valid summaries.")
        combined_summaries_text = "\n\n".join([
            # Include source info in the report prompt context as well
            f"Summary {i+1} (Source: {s['source_id']}, Type: {s['type']}, Score: {s['score']}):\n{s['summary']}"
            for i, s in enumerate(top_summaries)
        ])
    else:
         print("Warning: No valid summaries available for report generation.")
         log_to_file("Report Gen Warning: No valid summaries found.")
         # We might still proceed if full reference docs are available

    # --- Process Full Reference Documents (If Not Summarized) ---
    full_reference_docs_text = ""
    num_ref_docs_used = 0
    if reference_docs_content and not args.reference_docs_summarize:
        num_ref_docs_used = len(reference_docs_content)
        print(f"Including {num_ref_docs_used} full reference documents directly in the report prompt.")
        log_to_file(f"Report Gen: Including {num_ref_docs_used} full reference documents.")
        full_reference_docs_text = "\n\n---\n\n".join([
            f"Reference Document (Path: {doc['path']}):\n{doc['content']}"
            for doc in reference_docs_content
        ])
        # Add a header for clarity in the prompt
        full_reference_docs_text = f"**Full Reference Documents (Use for context):**\n---\n{full_reference_docs_text}\n---"

    # Check if we have *any* content to generate from
    if num_summaries_used == 0 and num_ref_docs_used == 0:
         print("Error: No summaries or reference documents available to generate report.")
         log_to_file("Report Gen Error: No summaries or reference documents available for context.")
         return None # Cannot generate report without context

    guidance_text = f"\n**Additional Guidance:** {args.guidance}\n" if args.guidance else ""
    prompt = (
        f"You are an AI assistant tasked with writing a well-structured, informative research paper/report on the topic: '{topic}'.{guidance_text}\n"
        f"**Topic:** {topic}\n"
        f"{guidance_text}\n" # Add guidance here as well for clarity
        f"**Task:**\n"
        f"Generate a comprehensive, well-structured, and informative research paper/report based *thoroughly* on the provided context (summaries and/or full reference documents). Synthesize the information, identify key themes, arguments, evidence, and supporting details (including specific statistics, names, dates, or benchmarks mentioned). Structure the report logically with an introduction (defining the topic and scope), body paragraphs (each exploring a specific facet or theme derived from the context, citing evidence implicitly), and a conclusion (summarizing key findings and potential implications or future directions). Maintain an objective, formal, and informative tone suitable for a research report. **Crucially, this must be a written report/essay format, NOT a script or dialogue.**\n\n"
        f"**Context for Report Generation (Analyze ALL):**\n\n"
        f"--- Summaries (Analyze these first) ---\n{combined_summaries_text}\n---\n\n"
        f"{full_reference_docs_text}\n\n" # This will be empty if no full docs were used
        f"**CRITICAL FORMATTING RULES (OUTPUT MUST FOLLOW EXACTLY):**\n"
        f"1. **OUTPUT TAG:** You MUST enclose the *entire* report content within a single pair of `<reportGenerate>` tags.\n"
        f"2. **CONTENT:** The content should be well-written, coherent, and directly based on the provided summaries.\n"
        f"3. **NO EXTRA TEXT:** ONLY include the report text inside the `<reportGenerate>` tags. **ABSOLUTELY NO** other text, introductory phrases, explanations, or thinking tags (`<think>...</think>`) should be present anywhere in the final output.\n\n"
        f"Remember: The entire output MUST be ONLY the report text enclosed in a single `<reportGenerate>` tag."
    )

    # Save report prompt
    if run_archive_dir:
        prompt_filename = os.path.join(run_archive_dir, "report_prompt.txt")
        try:
            with open(prompt_filename, 'w', encoding='utf-8') as pf: pf.write(prompt)
            log_to_file(f"Saved report prompt to {prompt_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save report prompt: {e}")

    # Call AI
    raw_response, cleaned_response = call_ai_api(prompt, config, tool_name="ReportGeneration", timeout=3000)

    # Save raw response
    if run_archive_dir and raw_response:
        raw_resp_filename = os.path.join(run_archive_dir, "report_response_raw.txt")
        try:
            with open(raw_resp_filename, 'w', encoding='utf-8') as rf: rf.write(raw_response)
            log_to_file(f"Saved report raw response to {raw_resp_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save report raw response: {e}")

    if not cleaned_response:
        print("\nError: Failed to generate report from AI (empty cleaned response).")
        log_to_file("Report Gen Error: Failed (empty cleaned response).")
        return None

    # Parse the response - Find last <reportGenerate> tag after cleaning <think> tags
    cleaned_text_for_report = clean_thinking_tags(cleaned_response)
    report_text = None
    if cleaned_text_for_report:
        last_opening_tag_index = cleaned_text_for_report.rfind('<reportGenerate>')
        if last_opening_tag_index != -1:
            closing_tag_index = cleaned_text_for_report.find('</reportGenerate>', last_opening_tag_index)
            if closing_tag_index != -1:
                start_content = last_opening_tag_index + len('<reportGenerate>')
                report_text = cleaned_text_for_report[start_content:closing_tag_index].strip()

    if not report_text: # Check if parsing failed or resulted in empty string
        print("\nError: Could not parse valid <reportGenerate> content from the AI response.")
        log_to_file(f"Report Gen Error: Failed to parse <reportGenerate> tag or content was empty.\nCleaned Response was:\n{cleaned_text_for_report}")
        # Save the failed report output for debugging
        if run_archive_dir:
            failed_report_path = os.path.join(run_archive_dir, "report_FAILED_PARSE.txt")
            try:
                with open(failed_report_path, 'w', encoding='utf-8') as frf: frf.write(cleaned_text_for_report or "Original cleaned response was empty.")
            except IOError: pass
        return None

    # Save the report
    final_report_filename = "podcast_report.txt"
    final_report_filepath = os.path.join(run_archive_dir, final_report_filename) if run_archive_dir else final_report_filename

    try:
        with open(final_report_filepath, 'w', encoding='utf-8') as ef:
            ef.write(report_text)
        print(f"Saved generated report to {final_report_filepath}")
        log_to_file(f"Report saved to {final_report_filepath}")
        return final_report_filepath
    except IOError as e:
        print(f"\nError: Could not save generated report to {final_report_filepath}: {e}")
        log_to_file(f"Report Saving Error: Failed to save report to {final_report_filepath}: {e}")
        # Try saving to CWD as fallback ONLY if archive failed
        if run_archive_dir:
            try:
                cwd_filename = final_report_filename
                with open(cwd_filename, 'w', encoding='utf-8') as ef_cwd: ef_cwd.write(report_text)
                print(f"Saved generated report to {cwd_filename} (in CWD as fallback)")
                log_to_file(f"Report saved to CWD fallback: {cwd_filename}")
                return cwd_filename
            except IOError as e_cwd:
                print(f"\nError: Could not save report to CWD fallback path either: {e_cwd}")
                log_to_file(f"Report Saving Error: Failed to save report to CWD fallback: {e_cwd}")
                return None
        else:
            return None
