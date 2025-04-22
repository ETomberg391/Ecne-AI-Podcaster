# Ecne AI Podcaster

Automated AI podcast generation from topic/keywords to final video. Leverages web research, LLMs for scripting, and TTS for audio synthesis.

![ecneAI_Podcast](https://github.com/user-attachments/assets/8ee380bd-aea0-45f1-8651-40784778b7ee)

---

## ✨ Features

*   **Automated Workflow:** Generates podcasts from topic/keywords with minimal user intervention.
*   **Flexible Research:** Uses web search (Google/Brave), direct URLs, or local documents (txt, pdf, docx) as source material.
*   **AI-Powered Scripting:** Employs Large Language Models (configurable via `ai_models.yml`) for:
    *   Source discovery and relevance scoring.
    *   Content summarization and extraction.
    *   Initial draft generation.
    *   Script refinement for natural flow and TTS optimization.
*   **High-Quality TTS:** Integrates with Orpheus TTS (via Orpheus-FastAPI) for realistic voice synthesis.
*   **Multi-Voice Support:** Assign distinct host and guest voices.
*   **Optional GUI Review:** `--dev` mode provides a Tkinter interface for reviewing, regenerating, and tweaking individual audio segments.
*   **Audio Post-Processing:** Configurable gain, padding, and advanced FFmpeg filters (de-essing, noise reduction, compression, normalization) per voice via YAML profiles.
*   **Video Output:** Assembles audio segments, background/character images, and intro/outro music into a final `.mp4` video file.
*   **Optional Reporting:** Can generate a written report summarizing the research findings.
*   **Dockerized Backend:** Thanks to the Orpheus-FastAPI project, the TTS backend setup is overly simplified using Docker from their repo.

---

## 🚀 Workflow Overview

1.  **Setup:** Run `installer.sh` to install dependencies (Python, Docker, FFmpeg, etc.) and set up the Orpheus-FastAPI backend environment.
2.  **Script Generation:** Execute `script_builder.py` with your topic, keywords, and optional guidance/sources. The LLM researches and writes `podcast_script_final.txt`.
3.  **Audio/Video Generation:** Run `orpheus_tts.py` using the script.
    *   Recommended use `--dev` for GUI-based segment review and adjustment.
    *   Specify host/guest voices.
    *   Configure images, music, and audio processing.
4.  **Final Product:** An `.mp4` podcast video is generated.

---

## ⚙️ Key Components

*   **`installer.sh` (`orpheus_Installer.sh`)**:
    *   Handles prerequisite checks and installation (Git, Docker, Python, FFmpeg, audio/GUI libs).
    *   Clones `Orpheus-FastAPI` repository.
    *   Sets up Python virtual environment for host scripts.
    *   Configures Docker Compose (`docker-compose-gpu.yml`) for the TTS backend (Requires NVIDIA Container Toolkit for GPU).
*   **`script_builder.py` (`script_builder.py`)**:
    *   Orchestrates research and script writing.
    *   **Input:** Topic, keywords, guidance, optional URLs/local files (`txt`, `pdf`, `docx`). `--no-search` requires provided sources.
    *   **Research:** Uses `newspaper4k`, `BeautifulSoup4`, `selenium` for scraping; `PyPDF2`, `python-docx` for local files. Optional Google/Brave Search API integration (requires `.env` keys).
    *   **AI Interaction:** Communicates with a configurable OpenAI-compatible LLM endpoint (`ai_models.yml`) for source discovery, summarization, scoring, script generation, and refinement.
    *   **Output:** Saves logs, prompts, summaries, `podcast_script_final.txt`, and optional report to a timestamped archive.
*   **`orpheus_tts.py` (`orpheus_tts.py`)**:
    *   Manages TTS conversion and audio/video assembly.
    *   **TTS Interaction:** Sends requests to the Orpheus TTS FastAPI endpoint.
    *   **Audio Handling:** Uses `soundfile`, `numpy`, `scipy`, `pydub` (optional) for basic audio manipulation.
    *   **Advanced Audio:** Leverages `ffmpeg` for filtering based on voice profiles (`settings/voices/*.yml`).
    *   **GUI (`--dev`):** Uses `tkinter`, `Pillow`, `matplotlib` for UI, review, and waveform display. `pygame` needed for playback.
    *   **Segmentation:** Uses `nltk` for sentence tokenization (`--guest-breakup`).
    *   **Video Assembly:** Combines audio, images (background, characters), and music (intro/outro) into the final `.mp4`.
*   **`settings folder` (`settings folder`)**:
    *   Manages characters profiles, all images, LLM profiles, intro/outro audio files, etc.
    *   **Highly Customizable:** All parts from the character cards, character images, background image, music, LLM settings, voice settings can all be changed from he settings folder.
    *   **Automated:** Customizing settings is recognized automatically by the system immediately upon refreshing.

---

## 🛠️ Setup

### Prerequisites

*   Linux-based OS (Installer attempts OS detection for package managers like `apt`, `yum`, `pacman`) (Working on Windows testing)
*   Git
*   Python 3.8+ & Pip
*   Docker & Docker Compose (Installer tried to handle)
*   FFmpeg (Installer tries to handle)
*   NVIDIA GPU with NVIDIA Container Toolkit (for GPU acceleration, recommended)
*   Potentially system libraries: Tkinter (`python3-tk`), libsndfile (`libsndfile1`), PortAudio (`portaudio19-dev`) - (installer attempts to handle these.)

### Installation Steps

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/ETomberg391/Ecne-AI-Podcaster
    cd Ecne-AI-Podcaster
    ```

2.  **Run the Installer:**
    *   Make the installer executable:
        ```bash
        chmod +x installer.sh
        ```
    *   Execute the installer script:
        ```bash
        ./installer.sh
        ```
    *   The script will guide you through dependency checks, installations, cloning Orpheus-FastAPI, setting up the Python virtual environment (`venv-host`), and configuring the Docker backend. Follow any prompts from the script.

---

## ▶️ Usage

1.  **Activate Host Virtual Environment:**
    ```bash
    source venv-host/bin/activate
    ```

2.  **Build the Script:**
    *   **Using Web Search:**
        ```bash
        python script_builder.py --topic "The future of renewable energy" --keywords "solar power, wind energy, battery storage, grid modernization" --guidance "Focus on recent technological advancements and challenges."
        ```
    *   **Using Specific URLs:**
        ```bash
        python script_builder.py --topic "Analysis of recent AI paper" --no-search --urls "https://example.com/article1" "https://anothersite.org/paper.pdf"
        ```
    *   **Using Local Files:**
        ```bash
        python3 script_builder.py --llm-model gemini_flash --topic "What are te best most efficient ways to get Precise Reforges?" --report --guidance "Please include what are precise reforges, how to get, what might not be worth the effort,and a small section on what Journeyman reforges are." --reference-docs-folder research/Example_Docs_Folder --no-search
        ```
    *   Check the `archive/` directory for `podcast_script_final.txt`.

3.  **Generate Podcast Audio/Video:**
    *   **Command-Line Generation:**
        ```bash
        python orpheus_tts.py --script archive/<timestamp>/podcast_script_final.txt --host-voice tara --guest-voice leo --bg-image assets/background.png --char-image assets/character.png --intro-music assets/intro.mp3 --outro-music assets/outro.mp3
        ```
    *   **Using Development GUI:**
        ```bash
        python orpheus_tts.py --script archive/<timestamp>/podcast_script_final.txt --host-voice tara --guest-voice leo --dev
        ```
        *   The GUI will launch, allowing you to review segments, adjust parameters, select files visually, and then finalize the podcast.

4.  **Output:** Find your final podcast in the specified output location (default: current directory as `podcast_final.mp4`).

---

## 🎬 Examples

Here are some podcasts created using Ecne AI Podcaster:

*   **Mabinogi Reforging Guide:** A discussion on the Mabinogi game's reforging system.
    *   [![Mabinogi Reforging Guide](https://img.youtube.com/vi/gHvIbpv95iQ/0.jpg)](https://youtu.be/gHvIbpv95iQ?si=yjsy_GlQMz_QKqHH)
    *   Watch on YouTube: [Dundell's Cyberspace Podcast - Mabinogi Reforging](https://youtu.be/gHvIbpv95iQ?si=yjsy_GlQMz_QKqHH)
*   **Evaluating LLMs for Code Generation:** An analysis of Large Language Models in the context of code generation tasks.
    *   [![Evaluating LLMs](https://img.youtube.com/vi/9pTBPMgRlBU/0.jpg)](https://youtu.be/9pTBPMgRlBU?si=EYcKWf7voCcyHx5h)
    *   Watch on YouTube: [Dundell's Cyberspace Podcast - Evaluating LLMs](https://youtu.be/9pTBPMgRlBU?si=EYcKWf7voCcyHx5h)

---

## 🔌 Dependencies & Credits

This project integrates and relies upon numerous fantastic open-source libraries, tools, and services.

**Core Infrastructure:**

*   Python 3.8+
*   Pip
*   Git
*   Docker & Docker Compose
*   FFmpeg

**TTS Backend (via `installer.sh` & Docker):**

*   **Orpheus-FastAPI** (by Lex-au): Provides the TTS API endpoint.
*   **Orpheus TTS Model** (by Canopy Labs): The underlying TTS model.
*   **llama.cpp** (Backend for Orpheus-FastAPI Docker setup).

**APIs (Optional):**

*   **AI Model API:** Any OpenAI-API compatible endpoint (configurable in `ai_models.yml`).
*   **Google Custom Search API:** For web search functionality.
*   **Brave Search API:** Alternative web search functionality.

**System Libraries (Handled by `installer.sh`):**

*   `Tkinter` (e.g., `python3-tk`)
*   `libsndfile` (e.g., `libsndfile1`)
*   `PortAudio` (e.g., `portaudio19-dev`)

🙏 Huge thanks to the creators and maintainers of all these projects! Please ensure compliance with their respective licenses and terms of service.

---

## 📜 License

This project is licensed under the [Apache License 2.0]
