/**
 * Screen capture utility for IRIS.
 * Provides a resilient 3-tier capture strategy:
 * 1. Native Android Capacitor Bridge (via AppLauncher.captureScreen with PixelCopy hardware snapshots).
 * 2. Web getDisplayMedia API (for desktop browsers and Electron with OS-level window/screen selection).
 * 3. Client-side DOM canvas rendering via html2canvas (universal fallback for Android WebView without native bridge).
 */

export interface CapturedScreen {
  file: File;
  preview: string;
}

export function isScreenCaptureSupported(): boolean {
  // Always true because we have native bridge, getDisplayMedia, and client-side DOM fallbacks.
  return true;
}

async function captureViaNativeBridge(): Promise<CapturedScreen | null> {
  const cap = typeof window !== "undefined" ? (window as unknown as { Capacitor?: { isNativePlatform?: () => boolean; Plugins?: { AppLauncher?: { captureScreen?: () => Promise<{ success: boolean; image_base64?: string }> } } } }).Capacitor : undefined;
  if (!cap || !cap.isNativePlatform?.() || !cap.Plugins?.AppLauncher?.captureScreen) {
    return null;
  }

  try {
    const res = await cap.Plugins.AppLauncher.captureScreen();
    if (res?.success && res.image_base64) {
      const response = await fetch(res.image_base64);
      const blob = await response.blob();
      const fileName = `screen-capture-${Date.now()}.jpg`;
      const file = new File([blob], fileName, { type: "image/jpeg" });
      return { file, preview: res.image_base64 };
    }
  } catch (err) {
    console.warn("Native screen capture bridge returned error:", err);
  }
  return null;
}

async function captureViaGetDisplayMedia(): Promise<CapturedScreen | null> {
  if (
    typeof navigator === "undefined" ||
    !navigator.mediaDevices ||
    typeof navigator.mediaDevices.getDisplayMedia !== "function"
  ) {
    return null;
  }

  let stream: MediaStream | null = null;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: { displaySurface: "default" },
      audio: false,
    });

    const videoTrack = stream.getVideoTracks()[0];
    if (!videoTrack) return null;

    const video = document.createElement("video");
    video.srcObject = stream;
    video.playsInline = true;
    video.muted = true;

    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => {
        video.play().then(resolve).catch(reject);
      };
      video.onerror = () => reject(new Error("Failed to load screen video stream."));
      setTimeout(resolve, 800);
    });

    await new Promise((r) => setTimeout(r, 200));

    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext("2d");
    if (!ctx) return null;

    ctx.drawImage(video, 0, 0, width, height);

    stream.getTracks().forEach((track) => track.stop());
    stream = null;

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", 0.85);
    });

    if (!blob) return null;

    const fileName = `screen-capture-${Date.now()}.jpg`;
    const file = new File([blob], fileName, { type: "image/jpeg" });
    const preview = URL.createObjectURL(blob);
    return { file, preview };
  } catch (err: unknown) {
    if (stream) {
      (stream as MediaStream).getTracks().forEach((track) => track.stop());
    }
    const errObj = err as { name?: string; message?: string };
    if (
      errObj?.name === "NotAllowedError" ||
      errObj?.name === "AbortError" ||
      errObj?.message?.toLowerCase().includes("permission denied") ||
      errObj?.message?.toLowerCase().includes("cancelled")
    ) {
      return null;
    }
    throw err;
  }
}

async function captureViaDom(): Promise<CapturedScreen | null> {
  try {
    const html2canvasModule = await import("html2canvas");
    const html2canvas = html2canvasModule.default;

    // Temporarily hide full-screen voice overlay dialog so we capture the actual screen content underneath
    const voiceDialog = document.querySelector<HTMLElement>('div[aria-label="Voice conversation with IRIS"]');
    const prevOpacity = voiceDialog ? voiceDialog.style.opacity : "";
    if (voiceDialog) {
      voiceDialog.style.opacity = "0";
      await new Promise((r) => setTimeout(r, 60));
    }

    try {
      const canvas = await html2canvas(document.body, {
        logging: false,
        useCORS: true,
        allowTaint: true,
        scale: Math.min(window.devicePixelRatio || 1, 2),
      });

      const blob = await new Promise<Blob | null>((resolve) => {
        canvas.toBlob(resolve, "image/jpeg", 0.85);
      });

      if (!blob) return null;

      const fileName = `screen-capture-${Date.now()}.jpg`;
      const file = new File([blob], fileName, { type: "image/jpeg" });
      const preview = URL.createObjectURL(blob);
      return { file, preview };
    } finally {
      if (voiceDialog) {
        voiceDialog.style.opacity = prevOpacity;
      }
    }
  } catch (err) {
    console.error("DOM screen capture failed:", err);
    return null;
  }
}

export async function captureCurrentScreen(): Promise<CapturedScreen | null> {
  // 1. Try Native Android Bridge if in Capacitor
  try {
    const nativeRes = await captureViaNativeBridge();
    if (nativeRes) return nativeRes;
  } catch (e) {
    console.debug("Native bridge capture skipped:", e);
  }

  // 2. Try browser getDisplayMedia API (Desktop Chrome / Electron)
  try {
    const displayMediaRes = await captureViaGetDisplayMedia();
    if (displayMediaRes) return displayMediaRes;
  } catch (e) {
    console.debug("getDisplayMedia skipped or unsupported:", e);
  }

  // 3. Fallback to client-side DOM rendering (Universal mobile & WebView fallback)
  try {
    const domRes = await captureViaDom();
    if (domRes) return domRes;
  } catch (e) {
    console.error("DOM fallback failed:", e);
  }

  throw new Error("Unable to capture screen on this device.");
}
