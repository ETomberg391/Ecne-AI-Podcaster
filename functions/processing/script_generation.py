import os
import re
import yaml # For loading character profiles within prompt formatting
import json # Used for logging raw response
import time # Used for delays in call_ai_api (imported by ai)
import traceback # Used for printing traceback in main (will be moved)

from ..ai import call_ai_api # Import call_ai_api from the new ai module
from ..utils import log_to_file, clean_thinking_tags, parse_ai_tool_response # Import utilities
# Access run_archive_dir from the global scope via utils
from ..utils import run_archive_dir


def format_script_generation_prompt(summaries_with_scores, reference_docs_content, topic, host_profile, guest_profile, args):
    """Formats the detailed prompt for the initial script generation AI call, including summaries and/or full reference docs."""

    # --- Process Summaries (Scraped + Reference if Summarized) ---
    score_threshold = args.score_threshold # Use the threshold from args
    valid_summaries = [s for s in summaries_with_scores if s['score'] >= 0 and not s['summary'].startswith("Error:")]
    print(f"\nFiltering {len(valid_summaries)} valid summaries with score >= {score_threshold}...")
    log_to_file(f"Script Gen: Filtering {len(valid_summaries)} valid summaries with score >= {score_threshold}.")
    filtered_summaries = [s for s in valid_summaries if s['score'] >= score_threshold]
    num_summaries_used = 0
    combined_summaries_text = "No summaries met the score threshold or were generated."

    # Fallback if threshold is too high
    if not filtered_summaries and valid_summaries:
        print(f"Warning: No summaries met score threshold >= {score_threshold}. Using all valid summaries.")
        log_to_file(f"Script Gen Warning: No summaries >= {score_threshold}. Using all {len(valid_summaries)} valid summaries.")
        top_summaries = sorted(valid_summaries, key=lambda x: x['score'], reverse=True)
    elif filtered_summaries:
        top_summaries = sorted(filtered_summaries, key=lambda x: x['score'], reverse=True)
    else:
        top_summaries = [] # No valid summaries at all

    if top_summaries:
        num_summaries_used = len(top_summaries)
        print(f"Using {num_summaries_used} summaries for script generation.")
        log_to_file(f"Script Gen: Using {num_summaries_used} summaries (Threshold: {score_threshold}).")
        # Format summaries for the prompt, including source info
        combined_summaries_text = "\n\n".join([
             f"Summary {i+1} (Source: {s['source_id']}, Type: {s['type']}, Score: {s['score']}):\n{s['summary']}"
             for i, s in enumerate(top_summaries)
        ])
    else:
        print("Warning: No summaries will be included in the script generation prompt.")
        log_to_file("Script Gen Warning: No summaries included in prompt.")

    # --- Process Full Reference Documents (If Not Summarized) ---
    full_reference_docs_text = ""
    num_ref_docs_used = 0
    if reference_docs_content and not args.reference_docs_summarize:
        num_ref_docs_used = len(reference_docs_content)
        print(f"Including {num_ref_docs_used} full reference documents directly in the prompt.")
        log_to_file(f"Script Gen: Including {num_ref_docs_used} full reference documents.")
        full_reference_docs_text = "\n\n---\n\n".join([
            f"Reference Document (Path: {doc['path']}):\n{doc['content']}"
            for doc in reference_docs_content
        ])
        # Add a header for clarity in the prompt
        full_reference_docs_text = f"**Full Reference Documents (Use for context):**\n---\n{full_reference_docs_text}\n---"

    # Check if we have *any* content to generate from
    if num_summaries_used == 0 and num_ref_docs_used == 0:
         print("Error: No summaries met the threshold and no reference documents provided/processed. Cannot generate script.")
         log_to_file("Script Gen Error: No summaries or reference documents available for context.")
         return None, 0, 0 # Indicate error


    # Load podcast name from host profile
    podcast_name = host_profile.get('podcast_name', 'Podcast') # Default if missing

    # Prepare character profiles as strings
    host_details = yaml.dump(host_profile, default_flow_style=False, sort_keys=False)
    guest_details = yaml.dump(guest_profile, default_flow_style=False, sort_keys=False)

    # --- Construct the Prompt ---
    # (Using the detailed prompt from main.py, slightly adjusted)
    guidance_text = f"\n**Additional Guidance:** {args.guidance}\n" if args.guidance else ""
    prompt = (
        f"You are an AI scriptwriter for the podcast '{podcast_name}'. Your task is to create a natural, engaging podcast script with a '{host_profile.get('vibe', 'chill but informal')}' vibe about the specific topic: '{topic}'.{guidance_text}\n"
        f"**Characters:**\n\n"
        f"--- HOST PROFILE ---\n{host_details}\n--------------------\n\n"
        f"--- GUEST PROFILE ---\n{guest_details}\n---------------------\n\n"
        f"**Podcast Topic:** {topic}\n"
        f"{guidance_text}\n" # Add guidance here as well for clarity
        f"**Task:**\n"
        f"Generate a comprehensive and extended podcast script based *thoroughly* on the provided context (summaries and/or full reference documents), following these strict rules:\n"
        f"1. **Human-like & Extended Conversation:** Make the dialogue sound like a real, flowing, and in-depth conversation. Aim to extend the discussion naturally by exploring nuances within the provided context. Inject subtle emotions like curiosity (Host), enthusiasm (Guest), surprise, or thoughtfulness where appropriate based on the content. Avoid robotic question-answer cycles.\n"
        f"2. **Emotional Nuance:** Host should express genuine interest and occasionally react with phrases like 'Wow, that's really interesting!' or 'I never thought about it that way.' Guest should convey passion for the topic, perhaps expressing excitement about a breakthrough or thoughtful concern about implications.\n"
        f"3. **Comprehensive Analysis & Synthesis:** Analyze **ALL** provided summaries (prioritizing higher scores) AND any full reference documents exhaustively. Find connections, contrasts, related themes, and specific details (especially statistics or benchmarks). Integrate information from all sources (summaries and full documents) into a coherent discussion about the main '{topic}'. Don't just list facts; weave the information together.\n"
        f"4. **Coverage & Flow:** Cover the most relevant points (indicated by summary score or presence in reference docs) comprehensively. Create natural, smooth transitions between different topics or aspects derived from the context.\n"
        f"5. **Character Adherence:** Strictly match the personalities, speaking styles, and interaction patterns defined in the profiles.\n"
        f"6. **Proactive Host Role:** Host guides the conversation, introduces the main topic '{topic}' and the podcast name '{podcast_name}' in the intro, connects topics, and expresses the listener's perspective. **Crucially, the Host should actively look for opportunities to ask insightful follow-up questions after the Guest responds, potentially drawing more details from other relevant summaries. The Host MUST also ask for clarification if the Guest provides a complex, technical, or potentially confusing answer.**\n"
        f"7. **Informative Guest Role:** Guest provides expert information, explains complex ideas clearly, links related concepts, and responds thoughtfully to the host's initial and follow-up questions.\n\n"
        f"**Content Organization:**\n"
        f"   - Intro: Host introduces podcast ('{podcast_name}'), topic ('{topic}'), and guest. Asks for high-level overview based on the overall context.\n"
        f"   - Body: Discuss key aspects from the summaries (prioritizing high scores) and reference documents. Use Host's follow-up questions and clarifications to delve deeper. Ensure Guest defines technical terms. Transition smoothly between sub-topics derived from all context.\n"
        f"   - Outro: Host briefly summarizes key takeaways and thanks the guest. (A specific sign-off will be added in the refinement step).\n\n"
        f"**CRITICAL FORMATTING RULES (OUTPUT MUST FOLLOW EXACTLY):**\n"
        f"1. **OUTPUT TAG:** You MUST enclose the *entire* podcast script dialogue within a single pair of `<scriptCast>` tags.\n"
        f"2. **DIALOGUE FORMAT:** Inside the `<scriptCast>` tag, each line of dialogue MUST start with either 'Host: ' or 'Guest: ', followed by their speech.\n"
        f"3. **NO EXTRA TEXT:** ONLY include the dialogue lines (starting with 'Host: ' or 'Guest: ') inside the `<scriptCast>` tags. **ABSOLUTELY NO** other text, introductory phrases, explanations, thinking tags (`<think>...</think>`), or stage directions (like `[laughs]`) should be present anywhere in the final output, especially not outside the `<scriptCast>` tags.\n\n"
        f"**Example of CORRECT Output Format:**\n"
        f"<scriptCast>\n"
        f"Host: Welcome back to {podcast_name}, everyone! Today, we're diving into the fascinating topic of '{topic}'. {guest_profile.get('name', 'Guest')}, thanks for joining us. Could you give us the high-level view?\n"
        f"Guest: Absolutely, {host_profile.get('name', 'Host')}! Great to be here. At its core, {topic} is about...\n"
        f"Host: That makes sense. You mentioned [detail from summary], could you expand on that?\n"
        f"Guest: Certainly. That relates to...\n"
        f"Host: Okay, so if I understand correctly, [paraphrases complex point]?\n"
        f"Guest: Exactly!\n"
        f"Host: Fantastic insights, {guest_profile.get('name', 'Guest')}. Thanks for breaking that down.\n"
        f"</scriptCast>\n\n"
        f"**Context for Script Generation:**\n\n"
        f"--- Summaries (Prioritize higher scores) ---\n{combined_summaries_text}\n---\n\n"
        f"{full_reference_docs_text}\n\n" # This will be empty if no full docs were used
        f"Remember: The entire output MUST be ONLY the dialogue script (with 'Host:'/'Guest:' labels) enclosed in a single `<scriptCast>` tag. NO OTHER TEXT OR TAGS outside of this single tag pair."
    )
    # Return counts for both summaries and full reference docs used
    return prompt, num_summaries_used, num_ref_docs_used


def format_refinement_prompt(initial_script_text, topic, host_profile, guest_profile):
    """Formats the prompt for the script refinement AI call."""

    podcast_name = host_profile.get('podcast_name', 'Podcast')
    host_details = yaml.dump(host_profile, default_flow_style=False, sort_keys=False)
    guest_details = yaml.dump(guest_profile, default_flow_style=False, sort_keys=False)

    # Mandatory Host Outro Line (incorporating profile names)
    host_name = host_profile.get('name', 'your host')
    outro_line = f"Host: Thank you for joining us! I'm {host_name}, and this has been {podcast_name}. Until next time!"

    prompt = (
        f"You are an AI script editor for the podcast '{podcast_name}'. Your task is to refine the provided podcast script to make it sound more natural and human-like, based on the character profiles, and to prepare it for Text-to-Speech (TTS) by expanding abbreviations and numbers.\n\n"
        f"**Characters:**\n\n"
        f"--- HOST PROFILE ---\n{host_details}\n--------------------\n\n"
        f"--- GUEST PROFILE ---\n{guest_details}\n---------------------\n\n"
        f"**Podcast Topic:** {topic}\n\n"
        f"**Task:**\n"
        f"Review and refine the following podcast script. Apply these specific changes:\n"
        f"1. **Enhance Natural Dialogue:** Adjust phrasing, add minor interjections (like 'uh-huh', 'right', 'interesting', 'you know'), smooth transitions, and ensure the conversation flows naturally according to the host and guest personalities. Maintain the '{host_profile.get('vibe', 'chill but informal')}' vibe.\n"
        f"2. **TTS Prep - Expand Abbreviations:** Find common abbreviations (e.g., 'AI', 'LLM', 'API', 'CPU', 'GPU', 'etc.') and expand them appropriately for speech (e.g., 'Artificial Intelligence' or 'A.I.', 'L.L.M.', 'A.P.I.'). Use context; spell out the first time if helpful.\n"
        f"3. **TTS Prep - Expand Numbers/Currency/Symbols:** Convert numerical figures, percentages, currency amounts, and common symbols into words suitable for speech. Examples:\n"
        f"   - '$40' -> 'forty dollars'\n"
        f"   - '0.45' -> 'point four five' or 'forty-five cents'\n"
        f"   - '$45B' / $45bn -> 'forty-five billion dollars'\n"
        f"   - '50%' -> 'fifty percent'\n"
        f"   - '2024' -> 'twenty twenty-four' (year) or 'two thousand twenty-four'\n"
        f"   - '#' -> 'number' or 'hash'\n"
        f"   - '@' -> 'at'\n"
        f"   - '&' -> 'and'\n"
        f"4. **TTS Prep - Handle Asterisks/Emphasis:** Replace text emphasized with asterisks (e.g., *important* or **critical**) with phrasing that conveys emphasis verbally, or remove the asterisks if emphasis isn't crucial for TTS.\n"
        f"5. **Maintain Structure:** Keep the original 'Host: ' and 'Guest: ' labels for each line.\n"
        f"6. **Character Consistency:** Ensure the refined dialogue still perfectly matches the character profiles.\n"
        f"7. **Mandatory Host Outro:** Ensure the *very last line* of the script is spoken by the Host and is EXACTLY: '{outro_line}'\n\n"
        f"**Original Script to Refine:**\n---\n{initial_script_text}\n---\n\n"
        f"**CRITICAL FORMATTING RULES (OUTPUT MUST FOLLOW EXACTLY):**\n"
        f"1. **OUTPUT TAG:** You MUST enclose the *entire* refined podcast script dialogue within a single pair of `<scriptCast>` tags.\n"
        f"2. **DIALOGUE FORMAT:** Inside the `<scriptCast>` tag, each line of dialogue MUST start with either 'Host: ' or 'Guest: ', followed by their speech.\n"
        f"3. **NO EXTRA TEXT:** ONLY include the dialogue lines (starting with 'Host: ' or 'Guest: ') inside the `<scriptCast>` tags. **ABSOLUTELY NO** other text, introductory phrases, explanations, or thinking tags (`<think>...</think>`) should be present anywhere in the final output.\n\n"
        f"**Example of CORRECT Refined Output Format:**\n"
        f"<scriptCast>\n"
        f"Host: Welcome back to {podcast_name}, everyone! Today, we're diving into the fascinating topic of '{topic}'. {guest_profile.get('name', 'Guest')}, thanks for joining us. Could you give us the, you know, the high-level view?\n"
        f"Guest: Absolutely, {host_profile.get('name', 'Host')}! Great to be here. Right, so at its core, {topic} is about...\n"
        f"Host: Interesting. You mentioned achieving, uh, ninety-five percent accuracy? Could you expand on that?\n"
        f"Guest: Certainly. That relates to the model we developed back in twenty twenty-three...\n"
        f"Host: Okay, so if I understand correctly, you're saying it cost forty million dollars?\n"
        f"Guest: Exactly! A significant investment.\n"
        f"{outro_line}\n" # Ensure example includes the outro
        f"</scriptCast>\n\n"
        f"Remember: The entire output MUST be ONLY the refined dialogue script (with 'Host:'/'Guest:' labels) enclosed in a single `<scriptCast>` tag, ending with the specific Host outro line."
    )
    return prompt


def generate_and_refine_script(summaries_with_scores, reference_docs_content, topic, host_profile, guest_profile, config, args):
    """Generates, refines, and saves the podcast script."""
    # Access run_archive_dir from the global scope via utils
    from ..utils import run_archive_dir

    print("\nGenerating and refining podcast script...")
    log_to_file("Starting script generation and refinement phase.")

    # --- Initial Generation ---
    # Pass reference_docs_content to the formatting function
    initial_prompt, num_summaries, num_ref_docs = format_script_generation_prompt(summaries_with_scores, reference_docs_content, topic, host_profile, guest_profile, args)
    if not initial_prompt: return None # Error occurred in formatting

    # Save initial prompt
    if run_archive_dir:
        prompt_filename = os.path.join(run_archive_dir, "script_initial_prompt.txt")
        try:
            with open(prompt_filename, 'w', encoding='utf-8') as pf: pf.write(initial_prompt)
            log_to_file(f"Saved initial script prompt to {prompt_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save initial script prompt: {e}")

    print("Calling AI for initial script generation...")
    raw_initial_response, cleaned_initial_response = call_ai_api(initial_prompt, config, tool_name="ScriptGeneration_Initial", timeout=3000) # Longer timeout

    # Save initial raw response
    if run_archive_dir and raw_initial_response:
        raw_resp_filename = os.path.join(run_archive_dir, "script_initial_response_raw.txt")
        try:
            with open(raw_resp_filename, 'w', encoding='utf-8') as rf: rf.write(raw_initial_response)
            log_to_file(f"Saved initial script raw response to {raw_resp_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save initial script raw response: {e}")

    if not cleaned_initial_response:
        print("\nError: Failed to generate initial script (empty cleaned response).")
        log_to_file("Script Gen Error: Initial generation failed (empty cleaned response).")
        return None

    initial_script_text = parse_ai_tool_response(cleaned_initial_response, "scriptCast")

    if not initial_script_text or initial_script_text == cleaned_initial_response:
        print("\nError: Could not parse <scriptCast> tag in initial script response.")
        log_to_file(f"Script Gen Error: Failed to parse <scriptCast> tag in initial response.\nResponse was:\n{cleaned_initial_response}")
        # Save the failed parsed output for debugging
        if run_archive_dir:
            failed_script_path = os.path.join(run_archive_dir, "script_initial_FAILED_PARSE.txt")
            try:
                with open(failed_script_path, 'w', encoding='utf-8') as fsf: fsf.write(cleaned_initial_response)
            except IOError: pass
        return None

    # Basic validation
    if not re.search(r'^(Host|Guest):', initial_script_text, re.MULTILINE):
         print("\nWarning: Initial script content doesn't seem to contain 'Host:' or 'Guest:' labels.")
         log_to_file("Script Gen Warning: Initial script missing Host:/Guest: labels.")
         # Proceed to refinement, maybe it can fix it?


    line_count = initial_script_text.count('\n') + 1
    print(f"Generated initial script with {line_count} lines.")
    log_to_file(f"Script Gen: Initial script generated ({line_count} lines).")
    # Save initial script before refinement
    if run_archive_dir:
         initial_script_path = os.path.join(run_archive_dir, "script_initial_GENERATED.txt")
         try:
             with open(initial_script_path, 'w', encoding='utf-8') as isf: isf.write(initial_script_text)
             log_to_file(f"Saved initial generated script to {initial_script_path}")
         except IOError as e: log_to_file(f"Warning: Could not save initial generated script: {e}")


    # --- Refinement Step ---
    refinement_prompt = format_refinement_prompt(initial_script_text, topic, host_profile, guest_profile)

    # Save refinement prompt
    if run_archive_dir:
        prompt_filename = os.path.join(run_archive_dir, "script_refinement_prompt.txt")
        try:
            with open(prompt_filename, 'w', encoding='utf-8') as pf: pf.write(refinement_prompt)
            log_to_file(f"Saved refinement script prompt to {prompt_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save refinement script prompt: {e}")

    print("Calling AI for script refinement...")
    raw_refined_response, cleaned_refined_response = call_ai_api(refinement_prompt, config, tool_name="ScriptRefinement", timeout=300)

    # Save refinement raw response
    if run_archive_dir and raw_refined_response:
        raw_resp_filename = os.path.join(run_archive_dir, "script_refinement_response_raw.txt")
        try:
            with open(raw_resp_filename, 'w', encoding='utf-8') as rf: rf.write(raw_refined_response)
            log_to_file(f"Saved refinement script raw response to {raw_resp_filename}")
        except IOError as e: log_to_file(f"Warning: Could not save refinement script raw response: {e}")

    if not cleaned_refined_response:
        print("\nWarning: Failed to refine script (empty cleaned response). Using initial script.")
        log_to_file("Script Refinement Warning: Refinement failed (empty cleaned response). Using initial script.")
        final_script_text = initial_script_text # Fallback to initial
    else:
        refined_script_text = parse_ai_tool_response(cleaned_refined_response, "scriptCast")

        if not refined_script_text or refined_script_text == cleaned_refined_response:
            print("\nWarning: Could not parse <scriptCast> tag in refinement response. Using initial script.")
            log_to_file(f"Script Refinement Warning: Failed to parse <scriptCast> tag in refinement response. Using initial script.\nResponse was:\n{cleaned_refined_response}")
            final_script_text = initial_script_text # Fallback to initial
             # Save the failed refinement output for debugging
            if run_archive_dir:
                failed_script_path = os.path.join(run_archive_dir, "script_refinement_FAILED_PARSE.txt")
                try:
                    with open(failed_script_path, 'w', encoding='utf-8') as fsf: fsf.write(cleaned_refined_response)
                except IOError: pass
        else:
             # Basic validation
            if not re.search(r'^(Host|Guest):', refined_script_text, re.MULTILINE):
                 print("\nWarning: Refined script content missing 'Host:'/'Guest:' labels. Using initial script.")
                 log_to_file("Script Refinement Warning: Refined script missing Host:/Guest: labels. Using initial script.")
                 final_script_text = initial_script_text # Fallback
            else:
                 print("Script refinement successful.")
                 log_to_file("Script Refinement: Success.")
                 final_script_text = refined_script_text # Use refined script
# --- Save Final Script ---
    topic_slug = re.sub(r'\W+', '_', topic)[:50] # Sanitize topic for filename

    # --- Save Final Script ---
    final_script_filename = f"{topic_slug}_podcast_script.txt" # Default name
    final_script_filepath = os.path.join(run_archive_dir, final_script_filename) if run_archive_dir else final_script_filename

    try:
        with open(final_script_filepath, 'w', encoding='utf-8') as sf:
            sf.write(final_script_text)
        print(f"Saved final script to {final_script_filepath}")
        log_to_file(f"Final script saved to {final_script_filepath}")
        return final_script_filepath
    except IOError as e:
        print(f"\nError: Could not save final script to {final_script_filepath}: {e}")
        log_to_file(f"Script Saving Error: Failed to save final script to {final_script_filepath}: {e}")
        # No fallback to CWD anymore, saving must happen in the archive dir
        return None # Saving failed completely