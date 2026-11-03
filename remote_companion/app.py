"""Entrypoint for Hugging Face Spaces ($0 / Free Tier with Gradio SDK)."""
from __future__ import annotations

import os
from main import app as fastapi_app, health, ready

try:
    import gradio as gr

    with gr.Blocks(title="IRIS Remote Coding Companion") as demo:
        gr.Markdown(
            """
            # 🤖 IRIS Remote Coding Companion
            This Space hosts the persistent remote execution environment for the **IRIS Coding Co-worker**.

            - **Backend:** FastAPI + Uvicorn (mounted with Gradio)
            - **Status:** Online & Ready
            - **Endpoints:** `/health`, `/ready`, `/api/workspaces/...`
            """
        )
        with gr.Row():
            status_box = gr.JSON(label="System Health & Tooling Status", value=health)
        with gr.Row():
            refresh_btn = gr.Button("🔄 Refresh Health Probe")
            refresh_btn.click(fn=health, outputs=status_box)

    # Mount Gradio dashboard at root while Starlette matches FastAPI API routes first
    app = gr.mount_gradio_app(fastapi_app, demo, path="/")
except ImportError:
    app = fastapi_app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
