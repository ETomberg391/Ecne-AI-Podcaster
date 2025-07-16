Update Notes 7/16/2025:
- Fixed a series of bugs associated with the podcast builder GUI where if you redo a segment for some reason the padding gets set to 0 in the segment forcing and further redos to be 0 padding making the final product no spacing between speakers... So not it is set to 750ms between speakers, and 100ms between same speaker segments IF padding = 0. Just some workaround, along with better handling padding for redos just in case.
- Additionally attempting to fix some gliched end-audio. I have a speculation I might need to increase the trimming by 10ms maybe. All the refinements cause a glitched end audio that the trimming handles. So I've noticed a split-second glitch on some ends of segments only revealed when finalized the full video. Seeing about trimming, and additional viewing tools per segment to make sure no glitch is included.
Update Notes 7/15/2025:
- Fixed bugs in resuming feature, and added a save and close button to save progress instead of saving and generating the final podcast. As a means to pick it back up in the json file for later with the resume feature.
- Fixed "Missing Audio" error that deadstops a segment, and enabled redo to regenerate a segment to clear and corrupt audio issues.
- Reworked some of the Script Builder to default youtube descriptions building enabled, and placed all additional settings under a dropdown menu for a cleaner look.

Update Notes 7/12/2025:
- Added an Easy mode for script building. Just click it, describe what you want to research and select your AI LLM backend. It will then automate a topic, 3 key words, and guidance.
- Added a resume feature to podcast building. This will allow you to return to a completed podcast in case a segment wasn't perfect, giving you the ability to edit and rebuild without starting from scratch all over again.
- Also reworked the output folders to better track scripts, archived podcasts, and finalized podcast videos.

Still working on:
- Working on restructuring the installation scripts to be easier, but also include no built-in sudo, and a installation_readme writeup on what is being installed for transparency.
- Also working on documentation folder to describe how to customize the podcast (Characters, images, background, music, voices, etc). All of it relatively easy to customize.
- No plans currently for dia-tts, but keeping my eyes open for any new developing tts services to incorporate that might work better (Preferrably in the same docker format and vram requirements of no more than 6gb vram). Chatterbox might be a good alternative.


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
