# IRIS Remote Coding Companion (Hugging Face Docker Space)

This directory contains the standalone containerized execution companion for **IRIS Milestone H**. It is designed to be deployed directly to a free **Hugging Face Spaces (Docker runtime)** space ($0 / no credit card required).

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
