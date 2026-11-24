# 🎬 OMNI STUDIO — Generic Multi-Niche Multi-Agent AI Video Engine

A production-ready, local-first & cloud-deployable **Streamlit** web application utilizing a 4-Agent Orchestrator to generate high-retention **5–8 minute YouTube videos & 9:16 Shorts** on **any topic or niche** (Education, Finance, AI, Gadgets, Tech, Business, History, Stories, Science, Health) and publish them directly to YouTube.

---

## 📁 Unified Architecture

```text
C:\OmniCreator_Studio\
├── app.py                              # Mobile- & tablet-responsive 4-step Streamlit UI
├── worker.py                           # Asynchronous background worker (ThreadPoolExecutor + SQLite queue)
├── .env.example                        # Environment configuration template (Gemini, Vertex, YouTube OAuth)
├── requirements.txt                    # Python dependencies
├── assets/
│   └── likeness/                       # @jwalashiva likeness references (image_12..14.png) & style sample (image_11.png)
├── storage/
│   ├── db.py                           # SQLite models (projects, generation_queue, oauth_tokens, publish_records)
│   └── omni_studio.db                  # Local SQLite database (auto-initialized)
├── backend/
│   ├── config.py                       # Latest GA Gemini SDK config, multi-niche visual taxonomy & retry helpers
│   ├── schemas.py                      # Strict Pydantic v2 contracts across Agents 1-4
│   ├── agent1_seo_storyboard.py        # Agent 1: YouTube Data API v3 mining + SEO + High-Retention Storyboard
│   ├── agent2_scene_scripter.py        # Agent 2: 30-50 granular 8-12s scenes + Veo/Omni/Flow prompts + SSML vocal cues
│   ├── agent3_media_composer.py        # Agent 3: Async TTS, AI Video/Keyframes, Motion Graphics, .ass Subs, -24dB BGM & Thumbnail
│   └── agent4_youtube_publisher.py     # Agent 4: OAuth 2.0 (SQLite tokens) + 4MB chunked resumable upload + chapters & playlist
└── render_engine/
    ├── motion_graphics.py              # Zero-hallucination procedural Manim / Matplotlib / high-DPI vector charts
    ├── subtitle_engine.py              # Word-level active-highlight `.ass` subtitle generator (faster-whisper / alignment)
    ├── audio_mixer.py                  # Chirp 3 HD / Gemini 3.8 TTS / Edge-TTS + Lyria 3.5 BGM ducked at -24dB + SFX
    └── thumbnail_studio.py             # High-CTR Thumbnail generator strictly preserving @jwalashiva likeness
```

---

## 🚀 Quick Start (Local Windows)

1. Copy `.env.example` to `.env` and populate your `GEMINI_API_KEY`, `YOUTUBE_API_KEY`, and OAuth paths.
2. Launch the Studio:
   ```powershell
   Set-Location C:\OmniCreator_Studio
   C:\YouTube_Studio_Engine\.venv\Scripts\streamlit.exe run C:\OmniCreator_Studio\app.py --server.port 8501
   ```
3. Check background worker & SQLite queue status via CLI anytime:
   ```powershell
   C:\YouTube_Studio_Engine\.venv\Scripts\python.exe C:\OmniCreator_Studio\worker.py --status
   ```

## ☁️ Streamlit Community Cloud (`staging` Branch)

- **Repository:** `ShivPrakash499/omnicreator-studio`
- **Branch:** `staging`
- **Main file path:** `app.py`
- `packages.txt` automatically installs `ffmpeg` and fonts for 16:9 & 9:16 video stitching and `.ass` subtitle burning.
