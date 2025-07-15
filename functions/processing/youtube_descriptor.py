import os
import re
import json # Used for logging raw response

from ..ai import call_ai_api # Import call_ai_api from the new ai module
from ..utils import log_to_file, clean_thinking_tags # Import utilities

def generate_youtube_description(report_content, topic, config, args):
    """Uses AI to generate a YouTube-friendly description based on an existing report."""
    # Access run_archive_dir from the global scope via utils
    from ..utils import run_archive_dir

    print("\nGenerating YouTube description via AI...")
    log_to_file(f"Starting YouTube description generation. Topic: {topic}")

    # Check if we have report content to work with
    if not report_content:
        print("Error: No report content provided for YouTube description generation.")
        log_to_file("YouTube Desc Error: No report content provided.")
        return None

    guidance_text = f"\n**Additional Guidance:** {args.guidance}\n" if args.guidance else ""
    prompt = (
        f"You are an AI assistant tasked with creating a YouTube video description based on an existing comprehensive report about '{topic}'.{guidance_text}\n"
        f"**Topic:** {topic}\n"
        f"{guidance_text}\n"
        f"**Task:**\n"
        f"Transform the provided comprehensive report into a YouTube description-friendly format. The output should be:\n"
        f"- Concise and scannable with bullet points and clear sections\n"
        f"- Simplified technical terms for general audience\n"
        f"- Key information organized by categories/sections\n"
        f"- Quick reference format suitable for video notes\n"
        f"- Actionable insights and specific recommendations\n"
        f"- YouTube-compatible plain text formatting (NO MARKDOWN)\n\n"
        f"Structure the YouTube description with:\n"
        f"1. Brief intro explaining what the topic covers\n"
        f"2. Key points organized in bullet format\n"
        f"3. Main categories/sections from the report\n"
        f"4. Quick takeaways and recommendations\n"
        f"5. Simplified explanations of technical concepts\n\n"
        f"IMPORTANT FORMATTING RULES FOR YOUTUBE:\n"
        f"- Use UPPERCASE for section headers (not ## or ###)\n"
        f"- Use • or - for bullet points (not * in markdown)\n"
        f"- NO bold (**text**), italics (*text*), or other markdown formatting\n"
        f"- Use emojis for visual appeal and section separation\n"
        f"- Use line breaks and spacing for readability\n"
        f"- Plain text only - YouTube descriptions don't support markdown\n\n"
        f"**Source Report Content:**\n"
        f"---\n{report_content}\n---\n\n"
        f"CRITICAL FORMATTING RULES (OUTPUT MUST FOLLOW EXACTLY):\n"
        f"1. OUTPUT TAG: You MUST enclose the entire YouTube description content within a single pair of `<youtubeDescription>` tags.\n"
        f"2. CONTENT: Use PLAIN TEXT formatting only - YouTube does NOT support markdown.\n"
        f"3. STYLE: Write in a friendly, accessible tone suitable for YouTube audience.\n"
        f"4. LENGTH: Keep it comprehensive but scannable - aim for detailed notes that viewers can quickly reference.\n"
        f"5. FORMATTING: Use UPPERCASE for headers, • or - for bullets, emojis for visual appeal, and line breaks for spacing.\n"
        f"6. NO MARKDOWN: Absolutely no **bold**, *italic*, ##headers##, or other markdown syntax.\n"
        f"7. NO EXTRA TEXT: ONLY include the YouTube description text inside the `<youtubeDescription>` tags. ABSOLUTELY NO other text, introductory phrases, explanations, or thinking tags should be present anywhere in the final output.\n\n"
        f"Remember: The entire output MUST be ONLY the YouTube description text enclosed in a single `<youtubeDescription>` tag. Use PLAIN TEXT formatting only - no markdown syntax whatsoever since YouTube descriptions don't support it."
    )

    # Save YouTube description prompt
    if run_archive_dir:
        prompt_filename = os.path.join(run_archive_dir, "youtube_description_prompt.txt")
        try:
            with open(prompt_filename, 'w', encoding='utf-8') as pf: 
                pf.write(prompt)
            log_to_file(f"Saved YouTube description prompt to {prompt_filename}")
        except IOError as e: 
            log_to_file(f"Warning: Could not save YouTube description prompt: {e}")

    # Call AI
    raw_response, cleaned_response = call_ai_api(prompt, config, tool_name="YouTubeDescriptionGeneration", timeout=args.ai_timeout, retries=args.ai_retries)

    # Save raw response
    if run_archive_dir and raw_response:
        raw_resp_filename = os.path.join(run_archive_dir, "youtube_description_response_raw.txt")
        try:
            with open(raw_resp_filename, 'w', encoding='utf-8') as rf: 
                rf.write(raw_response)
            log_to_file(f"Saved YouTube description raw response to {raw_resp_filename}")
        except IOError as e: 
            log_to_file(f"Warning: Could not save YouTube description raw response: {e}")

    if not cleaned_response:
        print("\nError: Failed to generate YouTube description from AI (empty cleaned response).")
        log_to_file("YouTube Desc Error: Failed (empty cleaned response).")
        return None

    # Parse the response - Find last <youtubeDescription> tag after cleaning <think> tags
    cleaned_text_for_youtube = clean_thinking_tags(cleaned_response)
    youtube_description_text = None
    if cleaned_text_for_youtube:
        last_opening_tag_index = cleaned_text_for_youtube.rfind('<youtubeDescription>')
        if last_opening_tag_index != -1:
            closing_tag_index = cleaned_text_for_youtube.find('</youtubeDescription>', last_opening_tag_index)
            if closing_tag_index != -1:
                start_content = last_opening_tag_index + len('<youtubeDescription>')
                youtube_description_text = cleaned_text_for_youtube[start_content:closing_tag_index].strip()

    if not youtube_description_text: # Check if parsing failed or resulted in empty string
        print("\nError: Could not parse valid <youtubeDescription> content from the AI response.")
        log_to_file(f"YouTube Desc Error: Failed to parse <youtubeDescription> tag or content was empty.\nCleaned Response was:\n{cleaned_text_for_youtube}")
        # Save the failed YouTube description output for debugging
        if run_archive_dir:
            failed_youtube_path = os.path.join(run_archive_dir, "youtube_description_FAILED_PARSE.txt")
            try:
                with open(failed_youtube_path, 'w', encoding='utf-8') as fyf: 
                    fyf.write(cleaned_text_for_youtube or "Original cleaned response was empty.")
            except IOError: 
                pass
        return None

    # Save the YouTube description
    final_youtube_filename = "youtube_description.md"
    final_youtube_filepath = os.path.join(run_archive_dir, final_youtube_filename) if run_archive_dir else final_youtube_filename

    try:
        with open(final_youtube_filepath, 'w', encoding='utf-8') as ef:
            ef.write(youtube_description_text)
        print(f"Saved generated YouTube description to {final_youtube_filepath}")
        log_to_file(f"YouTube description saved to {final_youtube_filepath}")
        return final_youtube_filepath
    except IOError as e:
        print(f"\nError: Could not save generated YouTube description to {final_youtube_filepath}: {e}")
        log_to_file(f"YouTube Desc Saving Error: Failed to save YouTube description to {final_youtube_filepath}: {e}")
        # Try saving to CWD as fallback ONLY if archive failed
        if run_archive_dir:
            try:
                cwd_filename = final_youtube_filename
                with open(cwd_filename, 'w', encoding='utf-8') as ef_cwd: 
                    ef_cwd.write(youtube_description_text)
                print(f"Saved generated YouTube description to {cwd_filename} (in CWD as fallback)")
                log_to_file(f"YouTube description saved to CWD fallback: {cwd_filename}")
                return cwd_filename
            except IOError as e_cwd:
                print(f"\nError: Could not save YouTube description to CWD fallback path either: {e_cwd}")
                log_to_file(f"YouTube Desc Saving Error: Failed to save YouTube description to CWD fallback: {e_cwd}")
                return None
        else:
            return None