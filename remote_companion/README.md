# IRIS Remote Coding Companion

This directory contains the standalone execution companion for **IRIS Milestone H & H.1**. It allows the IRIS Coding Co-worker to execute coding tasks in a remote cloud environment 24/7 without keeping your personal laptop running.

---

## Deployment Options ($0 Free Tiers, No Credit Card)

1. **[Recommended for High RAM] Google Colab (12.7 GB RAM · 2 vCPUs · $0 Free):**
   - See **[COLAB_DEPLOYMENT.md](COLAB_DEPLOYMENT.md)** to run the 1-click companion notebook [`IRIS_Colab_Companion.ipynb`](IRIS_Colab_Companion.ipynb) with a free Cloudflare tunnel.
2. **Render.com Web Service ($0 / No Credit Card Required):**
   - See **[RENDER_DEPLOYMENT.md](RENDER_DEPLOYMENT.md)** for step-by-step setup on Render.com free tier with automated keep-alive cron job.
3. **Hugging Face Spaces:**
   - See **[DEPLOYMENT.md](DEPLOYMENT.md)** for Hugging Face Spaces instructions (note: Hugging Face currently requires billing verification/PRO subscription to unlock compute-backed spaces).

---

## 1. Space Configuration

1. Create a new Space on [huggingface.co/new-space](https://huggingface.co/new-space).
2. Space Settings:
   - **Space Name:** `iris-sandbox` (or your choice)
   - **License:** `mit`
   - **Space SDK:** `Docker` ➔ `Blank`
   - **Space Hardware:** `CPU Basic · 2 vCPU · 16 GB RAM · Free`
   - **Visibility:** `Private`
3. Repository files:
   - Push all files from `remote_companion/` (`Dockerfile`, `requirements.txt`, `main.py`) directly to the root of your Hugging Face Space repository.

---

## 2. Secrets Configuration

In your Hugging Face Space, navigate to **Settings ➔ Variables and secrets**:

| Secret Name | Description | Example / Source |
| :--- | :--- | :--- |
| `IRIS_COMPANION_SECRET` | Shared secret bearer token used by IRIS Core to authenticate requests | `a6b8c4d2e...` |
| `GITHUB_PAT` | Optional fallback GitHub Personal Access Token (PAT) for cloning | `github_pat_...` |
| `AGY_ADC_AUTH` | Enables Google Cloud Application Default Credentials for Antigravity | `true` |
| `GEMINI_API_KEY` | Optional direct API key for Antigravity model execution | `AIzaSy...` |

---

## 3. Connecting to IRIS

In IRIS Core (or your `.env` / Vercel environment variables):
```env
REMOTE_COMPANION_URL=https://<your-hf-username>-iris-sandbox.hf.space
IRIS_COMPANION_SECRET=<your-shared-secret>
```

When you open a Coding Co-worker in IRIS, you can toggle between **`💻 Local PC`** and **`☁️ Remote Cloud`** to let Antigravity work 24/7 even when your personal laptop is powered off.
