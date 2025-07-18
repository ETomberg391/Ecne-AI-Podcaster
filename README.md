Update Summary for 7/18/2025:

*   **Podcast Builder Enhancements:**
    *   Fixed padding issues in GUI, ensuring consistent spacing between speakers (750ms) and same-speaker segments (100ms).
    *   Added "Save and Close" for progress saving and a resume feature for editing completed podcasts.
    *   Resolved "Missing Audio" errors, enabling segment regeneration for corrupt audio.
*   **Audio Quality & Trimming:**
    *   Addressed some of the split-second audio glitches at segment ends, exploring increased trimming (10-150ms) and new viewing tools.
*   **Script Builder Improvements:**
    *   Defaulted YouTube description building and streamlined settings into a dropdown menu.
    *   Introduced "Easy mode" for automated script topic, keywords, and guidance.
*   **Project Organization:**
    *   Reworked output folders for better tracking of scripts, archived, and finalized podcast videos.
*   **Future Work:**
    *   Simplifying installation scripts (no sudo, transparent `installation_readme`).
    *   Creating documentation for podcast customization (characters, images, music, voices).
    *   Researching new TTS services with Docker FastAPI (e.g., Chatterbox) with low VRAM requirements (max 6GB).

# Ecne AI Podcaster

Automated AI podcast generation from topic/keywords to final video. Leverages web research, LLMs for scripting, and TTS for audio synthesis.

![image](https://github.com/user-attachments/assets/ca081333-1955-4419-a09c-8ec79a11ad38)


<div style="display: flex; gap: 10px;">
  <img src="https://github.com/user-attachments/assets/1c910199-bb0c-4181-9a6f-05dc4b351348" alt="Screenshot_20250526_230535" style="width: 50%;"><img src="https://github.com/user-attachments/assets/c06ed2f3-d9aa-4851-8c0c-098f6042bc8f" alt="Screenshot_20250526_230602" style="width: 50%;">
</div>

![ecneAI_Podcast](https://github.com/user-attachments/assets/8ee380bd-aea0-45f1-8651-40784778b7ee)

## ✨ Features

- **Web Control Panel:** Easy-to-use browser interface for the complete podcast creation workflow
- **Script Generation:** AI-powered research and script writing from topics, keywords, or documents
- **Podcast Production:** High-quality TTS with Orpheus and video assembly
- **Docker Integration:** Automated TTS backend setup via Docker
- **Multi-Voice Support:** Distinct host and guest voices with audio processing

---

## 🚀 Quick Start

### 1. Installation
Note: Installer.sh made for Linux OS's (Arch Linux tested). Windows installer Pending.
```bash
git clone https://github.com/ETomberg391/Ecne-AI-Podcaster
cd Ecne-AI-Podcaster
chmod +x Installer.sh
./Installer.sh
```

### 2. Start the WebGUI Control Panel
```bash
./run_control_panel.sh
```

### 3. Access the Web Interface
Open your browser and go to: **http://localhost:5000**

---

## 🎛️ Control Panel Features

The web control panel provides everything you need:

### **Dashboard**
- Quick overview and navigation
- System status monitoring

### **Script Builder**
- Topic and keyword input
- Document upload support (PDF, DOCX, TXT)
- Web search integration (Google/Brave APIs)
- AI model selection
- Real-time progress streaming

### **Podcast Builder**
- Script selection from generated scripts
- Voice configuration (host/guest)
- Audio and video settings
- Development mode for segment review

### **Settings**
- API key management (OpenAI, Google, Brave, etc.)
- LLM model configuration
- Voice profiles and audio processing

### **History**
- Browse generated scripts and videos
- Download completed podcasts
- Archive management

### **Docker Management**
- Start/stop Orpheus TTS services
- Container status monitoring
- Automated setup

---

## 📋 Prerequisites

- Linux OS (Ubuntu/Debian recommended)
- Git, Python 3.8+, Docker, FFmpeg
- NVIDIA GPU with Container Toolkit (recommended for TTS)

The installer handles most dependencies automatically.

---

## 🎯 Workflow

1. **Configure Settings:** Add your API keys and select LLM models
2. **Generate Script:** Enter topic/keywords or upload documents
3. **Create Podcast:** Select script, choose voices, generate video
4. **Download:** Access your completed podcast from the History page

---

## 🎬 Examples

*   **Mabinogi Reforging Guide:**
*    [![YouTube](https://img.youtube.com/vi/gHvIbpv95iQ/0.jpg)](https://youtu.be/gHvIbpv95iQ?si=yjsy_GlQMz_QKqHH)
*   **Dundell's Cyberspace - What are Game Emulators?:**
*    [![YouTube](https://img.youtube.com/vi/9pTBPMgRlBU/0.jpg)](https://youtu.be/zbZmEwGinoA?si=hSPlLnpuAsajUtsb)

---

## 🙏 Credits

Built with [Orpheus-FastAPI](https://github.com/Lex-au/Orpheus-FastAPI) for TTS and [Orpheus TTS](https://github.com/canopyai/Orpheus-TTS) model.

## 📜 License

Apache License 2.0
