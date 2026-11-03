# IRIS Remote Coding Companion — Hugging Face Deployment Guide

This guide walks you through deploying the **IRIS Remote Execution Companion** to **Hugging Face Spaces** using the free Docker tier (**$0 / no credit card required**).

The companion acts as a remote, persistent workspace where the IRIS Coding Co-worker runs Google Antigravity autonomously—even when your personal laptop is turned off.

---

## 1. Prerequisites

- A [Hugging Face](https://huggingface.co) account (free).
- A [GitHub Personal Access Token (PAT)](https://github.com/settings/tokens) with `repo` permissions (classic or fine-grained with read & write access to repository contents).
- A secret token for IRIS companion authorization. You can generate one with:
  ```bash
  python -c "import secrets; print(secrets.token_hex(24))"
  ```

---

## 2. Step 1 — Create the Hugging Face Space

> [!NOTE]
> **Why does Docker show "Paid"?**
> Hugging Face recently updated their platform anti-abuse policy: creating **Docker SDK** spaces now requires adding a billing method/credit card to unlock.
> 
> **The 100% Free ($0 / Zero Credit Card) Solution:**
> Choose **`Gradio`** as the Space SDK!
> Gradio Spaces are **100% free with no credit card required**. Because Gradio is built natively on top of FastAPI and Uvicorn, our entire remote companion runs directly inside it with zero compromises, exposing all the exact same `/health`, `/ready`, and `/api/workspaces/...` endpoints!

1. Navigate to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Configure the following settings:
   - **Space name:** `iris-coworker-sandbox` (or a name of your choice)
   - **License:** `mit`
   - **Select the Space SDK:** Choose **`Gradio`** (Free, no credit card required)
   - **Choose a template:** Choose **`Blank`**
   - **Space Hardware:** **`CPU basic · 2 vCPU · 16 GB · Free`** ($0 / month, no credit card required)
   - **Visibility:** Select **`Private`** (Recommended to keep your workspace, git diffs, and companion private)
3. Click **Create Space**.

---

## 3. Step 2 — Configure Environment Secrets

In your newly created Space, navigate to **Settings** ➔ **Variables and secrets** ➔ **New secret**:

| Secret Name | Required | Description | Example / Note |
| :--- | :--- | :--- | :--- |
| `IRIS_COMPANION_SECRET` | **Yes** | Shared bearer secret that IRIS backend uses to authenticate with this companion | Your generated token (e.g., `d4f8...`) |
| `ENVIRONMENT` | **Yes** | Signals production mode to enforce strict security checks | `production` |
| `GITHUB_PAT` | Optional | Default fallback GitHub PAT for cloning and pushing | `ghp_...` or `github_pat_...` |
| `GEMINI_API_KEY` | Optional | Direct Gemini API key for Antigravity model execution | `AIzaSy...` |
| `AGY_ADC_AUTH` | Optional | Enables Google Cloud Application Default Credentials if configured | `true` |

> [!IMPORTANT]
> In production mode (`ENVIRONMENT=production`), the companion **will reject** requests if `IRIS_COMPANION_SECRET` is unset or left as the default development value (`dev-secret-token`). Always configure a strong secret.

---

## 4. Step 3 — Deploy Companion Files to Hugging Face

Push the companion files (`app.py`, `main.py`, `requirements.txt`, `packages.txt`):

### Option A: Via Hugging Face Web UI (Easiest)

1. In your newly created Hugging Face Space, click the **Files** tab.
2. Click **Add file** ➔ **Upload files**.
3. Drag and drop the following files from `remote_companion/`:
   - `app.py`
   - `main.py`
   - `requirements.txt`
   - `packages.txt`
4. Click **Commit changes to main**.

### Option B: Via Git CLI

From your local IRIS repository:

```bash
# 1. Open a terminal in the remote_companion directory
cd remote_companion

# 2. Initialize a temporary git repository or add Hugging Face remote
git init
git checkout -b main
git add app.py main.py requirements.txt packages.txt
git commit -m "feat: deploy IRIS remote companion"

# 3. Add your Hugging Face Space repository as a remote
# Format: https://huggingface.co/spaces/<your-hf-username>/<your-space-name>
git remote add hf https://huggingface.co/spaces/<YOUR_HF_USERNAME>/iris-coworker-sandbox

# 4. Push to Hugging Face (you will be prompted for your Hugging Face username and token)
git push -f hf main
```

*(Note: When prompted for your password, use your Hugging Face Access Token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) with `write` permission).*

---

## 5. Step 4 — Verify Deployment & Readiness

Hugging Face will automatically build the container and start the FastAPI service on port 7860.

1. Go to the **Logs** tab in your Space and wait until you see:
   ```text
   INFO:     Uvicorn running on http://0.0.0.0:7860 (Press CTRL+C to quit)
   ```
2. Your public Space URL will be:
   `https://<your-hf-username>-iris-coworker-sandbox.hf.space`
3. Test readiness using your secret token:
   ```bash
   curl -H "Authorization: Bearer <YOUR_IRIS_COMPANION_SECRET>" https://<your-hf-username>-iris-coworker-sandbox.hf.space/ready
   ```
   **Expected Response (HTTP 200):**
   ```json
   {
     "ready": true,
     "storage_writable": true,
     "git": true,
     "timestamp": "2026-11-02T..."
   }
   ```

---

## 6. Step 5 — Connect Remote Companion to IRIS

Now connect your IRIS backend to your Hugging Face Space:

1. In your local `.env` or in Vercel project environment settings, set:
   ```env
   REMOTE_COMPANION_URL=https://<your-hf-username>-iris-coworker-sandbox.hf.space
   IRIS_COMPANION_SECRET=<YOUR_IRIS_COMPANION_SECRET>
   ```
2. Open the IRIS web application in your browser.
3. Open **Coworkers** ➔ **Coding Co-worker Chat**:
   - In the top action bar, click **`☁️ Remote Cloud`**.
   - Create or select a remote workspace.
   - You can now prompt your Coding Co-worker to write code, review diffs, commit changes, and push feature branches directly from the cloud.

---

## 7. Storage Durability & Inactivity Recovery

### Free Tier Lifecycle
- Hugging Face Spaces free CPU instances sleep after 48 hours of inactivity.
- Any ephemeral filesystem storage inside the container may be reset when the container spins down.

### Zero Data Loss Architecture
- **Git as Source of Truth:** All committed work is pushed to your GitHub repository task branch.
- **Supabase Durable Checkpoints:** While tasks are executing, IRIS automatically captures unified diff patches and persists them into your Supabase PostgreSQL database (`remote_workspaces.uncommitted_patch` with SHA-256 integrity verification).
- **Auto-Recovery:** When you resume work on a sleeping space:
  1. IRIS wakes up the container via HTTP.
  2. IRIS clones the task branch from GitHub.
  3. IRIS runs `git apply --check` to dry-run the saved patch.
  4. IRIS restores your exact working tree with zero loss of uncommitted edits.

---

## 8. Troubleshooting & FAQ

- **HTTP 401 Unauthorized:**
  - Verify that `IRIS_COMPANION_SECRET` configured in your Space matches the secret configured in IRIS Core.
- **HTTP 409 Conflict:**
  - Another task is currently executing in that workspace. Use the `/stop` endpoint or click **Stop** in the IRIS chat UI before dispatching another prompt.
- **HTTP 422 Patch Dry-Run Error:**
  - The uncommitted patch conflicted with the current HEAD. IRIS preserves the original patch in the database (`previous_patch`) so no code is ever lost.
- **Protected Branch Rejection (HTTP 403):**
  - By design, the companion will never push directly to `main`, `master`, `production`, or other protected branches. All work is committed to task branches (`iris/task/...`) and merged via Pull Requests.
