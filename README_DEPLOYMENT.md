# OmniCreator Studio — Cloud & Multi-Device Deployment Guide

Access **OmniCreator Studio** (`Trading Titans`) from any device (laptop, phone, or tablet) by deploying to **Google Cloud Run**, **Streamlit Community Cloud (via GitHub)**, or running locally.

---

## Option 1: Deploy on Google Cloud Run (Google Ecosystem — Recommended)

This project includes a production [`Dockerfile`](Dockerfile) (with `ffmpeg` pre-installed for 16:9 & 9:16 video stitching) and [`cloudbuild.yaml`](cloudbuild.yaml).

### 1-Command Deploy with `gcloud`
1. Authenticate your Google Cloud CLI:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_GCP_PROJECT_ID
   ```
2. Deploy directly from source to Cloud Run (`asia-south1` Mumbai region):
   ```bash
   gcloud run deploy omnicreator-studio \
     --source . \
     --region=asia-south1 \
     --allow-unauthenticated \
     --memory=2Gi \
     --cpu=2 \
     --port=8080 \
     --project=YOUR_GCP_PROJECT_ID \
     --quiet
   ```
3. Cloud Run will output an HTTPS URL (e.g. `https://omnicreator-studio-xxxxx-el.a.run.app`) that works on **any phone, tablet, or computer** anywhere.

---

## Option 2: Deploy via GitHub + Streamlit Community Cloud (or GitHub Actions)

1. Push this repository to GitHub:
   ```bash
   git remote add origin https://github.com/YOUR_USERNAME/omnicreator-studio.git
   git branch -M main
   git push -u origin main
   ```
2. **For Streamlit Community Cloud (Free 1-Click Hosting):**
   - Go to [share.streamlit.io](https://share.streamlit.io), connect your GitHub repo, and select `app.py`.
   - Add `packages.txt` (already included with `ffmpeg`) and your `GEMINI_API_KEY` in **App Settings → Secrets**.
3. **For Automated Google Cloud Run Deploys on `git push`:**
   - The workflow [`.github/workflows/deploy-cloudrun.yml`](.github/workflows/deploy-cloudrun.yml) automatically builds and deploys to Google Cloud Run whenever you push to `main`.
