# TopperLab 3D Studio — Clean-Slate Faceless 3D STEM & Exam Video Engine

Dedicated faceless production & publishing studio for **TopperLab 3D** (`@TopperLab3D`, YouTube Channel ID `UCuYzy1OoXmzldjRP8cgUmRw`), targeting Indian High-School Students (**Class 9–12 • CBSE/ICSE • JEE Mains/Adv • NEET UG**) with **Clean Indian-English (`en-IN`)** narration and **100% pure 3D visuals**.

---

## 1. Free 24/7 Cloud Hosting on Streamlit Community Cloud (`staging` Branch)

1. Open [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub (`ShivPrakash499`).
2. Click **Create app** → select:
   - **Repository:** `ShivPrakash499/omnicreator-studio`
   - **Branch:** `staging`
   - **Main file path:** `app.py`
3. Under **Advanced settings → Secrets**, add:
   ```toml
   GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
   STUDIO_ACCESS_CODE = "TopperLab2026"
   ```
4. Click **Deploy!** (`packages.txt` automatically installs `ffmpeg` for `16:9` and `9:16` MP4 stitching).

---

## 2. Run Locally on Windows

```powershell
Set-Location C:\OmniCreator_Studio
C:\YouTube_Studio_Engine\.venv\Scripts\streamlit.exe run C:\OmniCreator_Studio\app.py --server.port 8501
```
Open `http://localhost:8501` and sign in with `jwalashiva@gmail.com` and passcode `TopperLab2026`.
