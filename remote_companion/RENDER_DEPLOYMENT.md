# Deploy IRIS Remote Companion to Render.com ($0 Free Tier, No Credit Card)

This guide walks you through deploying the **IRIS Remote Execution Companion** to **Render.com** on the free tier (**$0 / month, zero credit card required**), with an automated keep-alive cron job so it stays awake 24/7.

---

## 1. Why Render.com?

- **100% Free ($0):** No credit card required at sign up.
- **750 Free Instance Hours/Month:** More than enough to run 24 hours a day for all 31 days (744 hours/month).
- **Native Python & Git:** Runs Python 3.11 with pre-installed `git` and fast SSD `/tmp` scratch space.
- **Auto-Deploys:** Re-deploys automatically when you push updates to your repository.

---

## 2. Step 1 — Create a Render Account (No Credit Card)

1. Go to [dashboard.render.com/register](https://dashboard.render.com/register).
2. Choose **GitHub** to sign up with your GitHub account (`Kirtan0902`).
3. No payment details or credit cards are requested.

---

## 3. Step 2 — Create the Web Service

1. From the Render Dashboard, click **New +** ➔ **Web Service**.
2. Select **Build and deploy from a Git repository** ➔ Click **Next**.
3. Connect your **`IRIS`** repository.
4. Fill in the service settings:
   - **Name:** `iris-remote-companion` (or any name you prefer)
   - **Region:** Pick any region close to you (e.g., Singapore, Frankfurt, Oregon)
   - **Branch:** `main`
   - **Root Directory:** `remote_companion`
   - **Runtime:** `Python 3`
   - **Build Command:**
     ```bash
     pip install -r requirements.txt
     ```
   - **Start Command:**
     ```bash
     uvicorn main:app --host 0.0.0.0 --port $PORT
     ```
   - **Instance Type:** Select **`Free`** ($0 / month)

---

## 4. Step 3 — Configure Environment Variables

Scroll down to the **Environment Variables** section on the same page (or under **Environment** after creation) and add:

| Key | Value | Notes |
| :--- | :--- | :--- |
| `PYTHON_VERSION` | `3.11.9` | Ensures standard Python 3.11 runtime |
| `ENVIRONMENT` | `production` | Enforces production security checks |
| `IRIS_COMPANION_SECRET` | *(Your secret token)* | E.g., generated with `python -c "import secrets; print(secrets.token_hex(24))"` |
| `GITHUB_PAT` | *(Optional)* | Personal access token with repo scope |
| `GEMINI_API_KEY` | *(Optional)* | Your Gemini API key for Antigravity |
| `AGY_ADC_AUTH` | `true` *(Optional)* | If using Google Cloud ADC credentials |

Click **Deploy Web Service** (or **Create Web Service**).

Render will build and deploy your container. Once complete, you will see a green status badge and your service URL:
`https://<service-name>.onrender.com`

---

## 5. Step 4 — Set Up the Inactivity Keep-Alive Cron Job

Render free-tier instances sleep after 15 minutes of inactivity. To keep your companion active 24/7 so it never sleeps, use either of these **free** keep-alive methods:

### Method A: Built-in GitHub Actions Cron (Recommended)
This repository already includes `.github/workflows/keep-companion-alive.yml` which runs on a cron every 12 minutes to ping `/health`.

To enable it:
1. Open your GitHub repo: `https://github.com/KIRTAN0902/IRIS/settings/variables/actions`
2. Click **New repository variable**.
3. **Name:** `REMOTE_COMPANION_URL`
4. **Value:** `https://<service-name>.onrender.com` (your Render service URL).
5. Click **Add variable**.

GitHub Actions will now ping your Render companion every 12 minutes, keeping it awake 24/7!

### Method B: External Free Ping Service (Alternative)
You can also use a free ping monitor like [cron-job.org](https://cron-job.org) or [uptimerobot.com](https://uptimerobot.com) (both 100% free with no credit card):
- **URL to Ping:** `https://<service-name>.onrender.com/health`
- **Schedule:** Every 10 or 12 minutes.
- **Request Type:** `GET`

---

## 6. Step 5 — Connect Remote Companion to IRIS

1. In your local `.env` or in Vercel project environment settings, configure:
   ```env
   REMOTE_COMPANION_URL=https://<service-name>.onrender.com
   IRIS_COMPANION_SECRET=<YOUR_IRIS_COMPANION_SECRET>
   ```
2. Open the IRIS web application in your browser.
3. Open **Coworkers ➔ Coding Co-worker Chat**:
   - In the top action bar, click **`☁️ Remote Cloud`**.
   - Create or select your remote workspace.
   - The Coding Co-worker is now connected to your free remote cloud instance 24/7!
