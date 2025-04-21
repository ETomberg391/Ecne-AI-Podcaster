Workflow comes in several parts:
1. Research, and Report/Script building
2. Audio Building
Extra: Image generator for Backgrounds, and Host/Guest sticker characters.
Installation: Dynamic script to help with basic requirements to run at least parts 1+2 

The normal workflow is running parts 1+2. The extra part is for your convenience in editing/builing upon the graphics. 


AI Podcast Generator Steps 1+2:

Installation:
1. bash orpheus_Installer.sh and follow instructions. 

Starting servers:

1. Start the llama.cpp backend server (llama-server):
   - Open a NEW terminal window/tab.
   - Navigate to the directory containing the server executable:
     cd "orpheus_tts_setup/llama.cpp/build/bin"
   - Run the server using the identified executable path:
     ./llama-server -m "../../../models/orpheus-model.Q6_K.gguf" --ctx-size 8192 --n-predict 8192 --rope-scaling linear -ngl 35 --port 8080
     (Adjust '-ngl 35' based on your GPU VRAM [e.g., try 30-35 for 8GB]. Use 0 for CPU fallback.)
   - Keep this server running.

2. Start the Orpheus-FastAPI frontend server:
   - Open ANOTHER new terminal window/tab.
   - Navigate to the FastAPI directory:
     cd "orpheus_tts_setup/Orpheus-FastAPI"
   - Activate the virtual environment:
     source venv/bin/activate
   - Start the server:
     python3 app.py
   - Keep this server running. You can access the Web UI at http://127.0.0.1:5005

3. Test the setup:
   - Make sure both servers from steps 1 & 2 are running.
   - In a THIRD terminal:
     Navigate to the directory where you saved this script and 'test_orpheus_tts.py'.
   - Run the test script:
     python3 test_orpheus_tts.py --port 5005
   - If successful, it will create an 'output_speech.wav' file.


So far recommend at the bare minimum if the user want to build every piece themselves from the text, to the audio:

Minimum:
Decent i5/ryzen 5 CPU
16 GB Ram
6GB Vram GPU
100GB's storage (5~15GB's turned into swapspace)

Recommnded:
i7/Ryzen7 CPU
32GB Ram
8GB Vram GPU
100GB's storage (5~15GB's turned into swapspace)

Additionally you will need an LLM. For under 8GB Vram +16GB Ram, you might consider some llama-server GGUF (Since we already use llama-server for the audio TTS), in which case a 14B Q4 with at least 32k context is within the ballpark estimates for part 1. Recommended though is QwQ-32B or Mistral Small 24B if possible. Having a smaller context window below 64k you put at risk of needing to change the following:

# Limit text size sent to AI if necessary (check API limits)
        max_summary_input_chars = 150000 # Example limit, adjust as needed
        truncated_text = text[:max_summary_input_chars]

        I might put an extraoption to change this within the command line. Rule is divide by 4, so 150k/4 = 37,500 tokens required, and expect summary 2~5k tokens = at least 43k tokens context needed for the normal script.

python3 test_orpheus_tts.py --script ../archive/20250402_220141/podcast_script.txt --host-voice leo --guest-voice tara --output podcast_QwQ32B_Updated.wav --silence 0.5 --dev

python3 main.py --api brave --keywords "LLM benchmarks, AI coding tests" --topic "Evaluating Large Language Models for Code Generation" --from_date 2025-03-15 --to_date 2025-04-02

./run_podcast_generator.py --keywords "large language models,evaluation" --topic "Evaluating LLMs" --api brave --from_date 2025-03-15 --to_date 2025-04-02 --host-voice dan --guest-voice tara --silence 0.5 --dev

python3 test_orpheus_tts.py --script ../archive/20250407_214334_What_are_the_best_AI_Art_or_Image_Generators_Model/podcast_script_final.txt --host-voice leo --guest-voice tara --output podcast_AI_Imager_Consistentv2.wav --silence 0.5 --dev

python3 mainv3.py --api brave --keywords "AI Image Generator, SOTA Image AI Generators, Consistent Characters AI Art Image Models, SOTA Image Model New" --topic "What are the best AI Art or Image Generators Models for Consistent Character designs?" --max-web-results 12 --max-reddit-results 3 --per-keyword-results 3 --from_date 2025-03-10 --to_date 2025-07-04 --report



python3 test_orpheus_tts.py --script ../archive/20250404_140806/podcast_script.txt --host-voice leo --guest-voice tara --output LLM_test --silence 0.5 --dev --guest-breakup

python3 generate_podcast_videov3.py ../../final_output/What_are_the_best_AI_Art_or_Image_Generators_Model_20250410_120702/What_are_the_best_AI_Art_or_Image_Generators_Model_20250410_120702_config.wav.json ImageGeneratorsConsistent.mp4 --encoder cpu --preset slow --bitrate 50M  --keep-temp-files


python3 mainv3.py --llm-model gemini_flash --keywords "Open Source LLM for Coding, SOTA open source LLM Coding, AI LLM local Coding Benchmarks new, AI LLM local Coding Model New" --topic "What are the current best SOTA open source LLM models for coding?" --report --guidance "Please only use LLM models from 2025, or Deepseek R1, Deepseek V3, Llama meta's newest maverick and scout, Qwen's new QwQ-32B, Qwen's upcoming Qwen 3 models, claude 3.7 sonnet, and anything additional that is based on January 2025 and newer. Do not include any model created before October 2024." --direct-articles llm-links.txt --no-search

python3 mainv3.py --api brave --llm-model gemini_flash --keywords "Open Source LLM for Coding, SOTA open source LLM Coding, AI LLM local Coding Benchmarks new, AI LLM local Coding Model New" --topic "What are the current best SOTA open source LLM models for coding?" --guidance "Please only use LLM models from 2025, or Deepseek R1, Deepseek V3, Llama meta's newest maverick and scout, Qwen's new QwQ-32B, Qwen's upcoming Qwen 3 models, claude 3.7 sonnet, and anything additional that is based on January 2025 and newer. Do not include any model created before October 2024." --max-web-results 12 --max-reddit-results 3 --per-keyword-results 3 --from_date 2025-04-07 --to_date 2025-04-14 --report --direct-articles llm-links.txt



python3 orpheus_ttsv2.py --script archive/20250418_001418_What_are_precise_reforges_in_Mabinogi_and_how_do_w/podcast_script_final.txt --host-voice leo --guest-voice tara --output podcast_Mabinogi_Reforges --dev


python3 script_builder.py --llm-model gemini_flash --topic "What are te best most efficient ways to get Precise Reforges?" --report --guidance "Please include what are precise reforges, how to get, what might not be worth the effort,and a small section on what Journeyman reforges are." --reference-docs-folder Mabi-reforges/ --no-search