# Running the IRIS Remote Companion on Google Colab (12 GB RAM · $0 Free)

Yes! **Google Colab** is an outstanding remote cloud execution target for the IRIS Coding Co-worker.

Unlike platforms that limit you to 512 MB RAM, Google Colab provides:
- **12.7 GB of High-Speed RAM** (plenty for Google Antigravity, compilers, AST parsers, and test runners)
- **2 Fast vCPUs** (Intel Xeon / AMD EPYC)
- **100+ GB of fast SSD storage**
- **$0 / Month, Zero Credit Card Required**
- Pre-installed `git`, `python`, `node`, `curl`, and build tools
- Native Google ecosystem compatibility with your **Google AI Pro** account

---

## 1. How It Works

We use a 1-click Colab notebook that launches the companion service and creates an instant, secure public HTTPS tunnel using **Cloudflare Quick Tunnels** (`trycloudflare.com`). No Cloudflare account or registration is required.

---

## 2. Step-by-Step Instructions

### Step 1: Open the Notebook in Google Colab
1. Go to [colab.research.google.com](https://colab.research.google.com).
2. In the modal, select the **Upload** tab.
3. Upload the notebook file from your local repository:
   [`remote_companion/IRIS_Colab_Companion.ipynb`](file:///C:/kirtan/IRIS/remote_companion/IRIS_Colab_Companion.ipynb)
   *(Alternatively, choose the **GitHub** tab, enter `KIRTAN0902/IRIS`, and select `remote_companion/IRIS_Colab_Companion.ipynb`).*

### Step 2: Run the Notebook Cell
Click the **Play (▶)** button on the code cell.

Within 15–20 seconds, the notebook will:
1. Clone the companion repository and install dependencies.
2. Download Cloudflare Tunnel (`cloudflared`).
3. Start the FastAPI companion on port 7860.
4. Output your live public connection details:
   ```text
   ============================================================
   🎉 IRIS REMOTE CODING COMPANION IS LIVE IN GOOGLE COLAB!
   ============================================================

   👉 REMOTE_COMPANION_URL:  https://xxxx-xxxx-xxxx.trycloudflare.com
   👉 IRIS_COMPANION_SECRET: iris_colab_secret_2026

   ============================================================
   ```

### Step 3: Connect IRIS Core
1. In your local `.env` (or in Vercel project environment variables), set:
   ```env
   REMOTE_COMPANION_URL=https://xxxx-xxxx-xxxx.trycloudflare.com
   IRIS_COMPANION_SECRET=iris_colab_secret_2026
   ```
2. Open the IRIS web app, go to **Coworkers ➔ Coding Co-worker Chat**.
3. In the top action bar, click **`☁️ Remote Cloud`**.
4. Select your remote workspace and start collaborating with your Coding Co-worker!

---

## 3. Disconnection & Inactivity Recovery

### Colab Session Lifecycle
- Google Colab free sessions remain active for up to 12 hours while the browser tab is open.
- If you close the browser tab, Colab will eventually spin down after an idle timeout.

### Why You Never Lose Work
Thanks to the **durable checkpoint architecture** built into Milestone H.1:
- While your coworker works, IRIS automatically captures unified diff patches and persists them with SHA-256 hashes inside your Supabase PostgreSQL database.
- If Colab ever disconnects or restarts:
  1. Simply click **Play (▶)** in Colab to get a new tunnel URL.
  2. Update the `REMOTE_COMPANION_URL` in IRIS.
  3. In IRIS, click **Wake / Recover**: IRIS will pull your GitHub branch and restore your exact uncommitted patch with zero data loss.
