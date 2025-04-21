# Ecne AI Podcaster

## Overview

Ecne AI Podcaster is a tool designed to automate the creation of AI-generated podcasts. It takes a topic, keywords, and optional guidance, researches relevant information, generates a script, synthesizes speech, and produces a final podcast video file.

## Workflow

The podcast generation process follows these steps:

1.  **Setup:** Run the `installer.sh` script to install necessary dependencies, including Python packages, Docker, Docker Compose, ffmpeg, and potentially system libraries like Tkinter, libsndfile, and PortAudio. The installer also clones the required `Orpheus-FastAPI` repository and sets up the necessary Docker environment.
2.  **Script Building:** Execute `script_builder.py`. Provide it with keywords, a topic, and optional guidance.
    * The script can use search APIs (Google or Brave) to find relevant articles based on the keywords, or you can provide a list of direct article URLs or a folder/files containing reference documents (txt, pdf, docx).
    * If `--no-search` is used, you must provide direct article URLs or reference documents.
    * It utilizes an AI model (configurable via `ai_models.yml`) to discover sources, scrape and summarize content, and generate an initial podcast script.
    * The script is then refined by the AI for natural flow and TTS preparation (expanding abbreviations, numbers, etc.).
    * Optionally, it can also generate a written report based on the gathered information.
    * The final script is saved as `podcast_script_final.txt`.
3.  **Text-to-Speech & Video Assembly:** Run `orpheus_tts.py` with the generated `podcast_script_final.txt`.
    * Specify host and guest voices.
    * Use the `--dev` option to launch a GUI (based on Tkinter) for reviewing and regenerating individual audio segments (intro, dialogue segments, outro). The GUI allows tweaking audio processing settings (like gain, padding, FFmpeg filters including de-essing, noise reduction, compression, normalization), selecting background/character images, and choosing intro/outro music.
    * The script interacts with the Orpheus TTS FastAPI endpoint.
    * It finalizes the reviewed segments into a single `.mp4` podcast video file.
4.  **Final Product:** The resulting `.mp4` file is a complete AI-generated podcast, ready for further editing or direct publishing.

## Key Components/Scripts

* **`installer.sh` (`orpheus_Installer.txt`)**:
    * Checks for and installs prerequisites (Git, Docker, Python, pip, ffmpeg, common audio/GUI libraries). Attempts OS detection for automated dependency installation.
    * Clones the `Orpheus-FastAPI` repository.
    * Sets up a Python virtual environment for host scripts (`script_builder.py`, `orpheus_tts.py`) and installs dependencies (`requirements_host.txt`, NLTK data).
    * Relies on Docker Compose and `docker-compose-gpu.yml` to manage the TTS backend (FastAPI app, llama.cpp server, Orpheus GGUF model). Requires NVIDIA Container Toolkit for GPU acceleration.
* **`script_builder.py` (`script_builder.txt`)**:
    * Orchestrates the research and scriptwriting process.
    * Uses `requests`, `python-dotenv`, `PyYAML` for configuration and API calls.
    * Performs web scraping using `newspaper4k`, `BeautifulSoup4`, and `selenium`.
    * Reads local documents using `PyPDF2` and `python-docx`.
    * Optionally searches the web using Google Custom Search API or Brave Search API. Requires API keys set in `.env`.
    * Leverages a configurable LLM via an OpenAI-compatible API for:
        * Discovering relevant web/Reddit sources.
        * Summarizing and scoring scraped/reference content.
        * Generating the initial podcast script.
        * Refining the script for naturalness and TTS compatibility.
    * Saves outputs (logs, prompts, summaries, final script, optional report) to a timestamped archive directory.
* **`orpheus_tts.py` (`orpheus_tts.txt`)**:
    * Handles the Text-to-Speech conversion and audio/video assembly.
    * Uses `requests` to call the Orpheus TTS FastAPI endpoint.
    * Uses `soundfile`, `numpy`, `scipy` for audio reading/writing/processing.
    * Uses `pydub` (optional) for audio manipulation (gain, trimming, padding, concatenation).
    * Uses `ffmpeg` (must be installed) for advanced audio filtering (Noise Reduction, Compression, Normalization, De-essing) configured via YAML voice profiles.
    * Provides an optional development GUI (`--dev`) using `tkinter`, `Pillow`, and `matplotlib` for segment review, audio playback (requires `pygame`), waveform visualization, and parameter adjustment.
    * Uses `nltk` for sentence tokenization when `--guest-breakup` is enabled.
    * Loads voice-specific configurations (gain, trim, FFmpeg parameters) from YAML files in `settings/voices/`.
    * Generates the final `.mp4` video using images and audio segments (Note: Specific video generation logic seems intended but might be in a separate linked script/module not provided, as `generate_podcast_videov4` is mentioned but its code is missing).

## Examples

The following are examples of podcasts created using this workflow:

1.  **Mabinogi Reforging Guide:**  (https://youtu.be/gHvIbpv95iQ?si=yjsy_GlQMz_QKqHH)
[![Dundell's Cyberspace Podcast- Mabinogi Reforging system talk](https://i.ytimg.com/vi/gHvIbpv95iQ/hqdefault.jpg)](https://www.youtube.com/watch?v=gHvIbpv95iQ&t "Dundell's Cyberspace Podcast- Mabinogi Reforging system talk")
3.  **Evaluating LLMs for Code Generation:** (https://youtu.be/9pTBPMgRlBU?si=EYcKWf7voCcyHx5h)
[![Dundell's Cyberspace Podcast- Mabinogi Reforging system talk](https://i.ytimg.com/vi/9pTBPMgRlBU/hqdefault.jpg)](https://www.youtube.com/watch?v=9pTBPMgRlBU&t "Dundell's Cyberspace Podcast - Evaluating LLMs for Code Generation")



## Dependencies & Credits

This project relies on several external tools, libraries, and services:

* **Core Tools:** Python 3, pip, Git, Docker, Docker Compose, FFmpeg
* **TTS Backend:**
    * Orpheus TTS (by Canopy Labs)
    * Orpheus-FastAPI (by Lex-au)
    * Llama.cpp (implied)
    * Hugging Face (for model download)
* **Python Libraries (Primary):**
    * `script_builder.py`: requests, newspaper4k, PyPDF2, python-docx, selenium, python-dotenv, PyYAML, beautifulsoup4
    * `orpheus_tts.py`: requests, soundfile, numpy, PyYAML, tkinter, Pillow, nltk, pydub (optional), matplotlib, scipy, pygame (optional)
* **APIs (Optional):**
    * AI API (OpenAI-compatible endpoint configured via `ai_models.yml`)
    * Google Custom Search API
    * Brave Search API
* **System Libraries (Potential):** Tkinter, libsndfile, PortAudio, NVIDIA Container Toolkit (for GPU)

Credit is due to the creators of these libraries and services. Please ensure compliance with their respective licenses and terms of service.
