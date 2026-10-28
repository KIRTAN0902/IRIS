/**
 * Screen capture utility for IRIS.
 * Uses Web getDisplayMedia API (supported natively on modern mobile and desktop browsers)
 * to capture the current screen as a JPEG image and attach it to the vision pipeline.
 */

export interface CapturedScreen {
  file: File;
  preview: string;
}

export function isScreenCaptureSupported(): boolean {
  return typeof navigator !== "undefined" &&
    !!navigator.mediaDevices &&
    typeof navigator.mediaDevices.getDisplayMedia === "function";
}

export async function captureCurrentScreen(): Promise<CapturedScreen | null> {
  if (!isScreenCaptureSupported()) {
    throw new Error("Screen perception is not supported by this browser engine.");
  }

  let stream: MediaStream | null = null;
  try {
    stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        displaySurface: "default",
      },
      audio: false,
    });

    const videoTrack = stream.getVideoTracks()[0];
    if (!videoTrack) {
      throw new Error("No video track received from screen capture.");
    }

    const video = document.createElement("video");
    video.srcObject = stream;
    video.playsInline = true;
    video.muted = true;

    await new Promise<void>((resolve, reject) => {
      video.onloadedmetadata = () => {
        video.play().then(resolve).catch(reject);
      };
      video.onerror = () => reject(new Error("Failed to load screen video stream."));
      // Timeout fallback in case autoplay blocks
      setTimeout(resolve, 1000);
    });

    // Small delay to ensure the display frame has rendered
    await new Promise((r) => setTimeout(r, 200));

    const width = video.videoWidth || 1280;
    const height = video.videoHeight || 720;

    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;

    const ctx = canvas.getContext("2d");
    if (!ctx) {
      throw new Error("Could not initialize 2D canvas context for screen capture.");
    }

    ctx.drawImage(video, 0, 0, width, height);

    // Stop all media tracks immediately
    stream.getTracks().forEach((track) => track.stop());
    stream = null;

    const blob = await new Promise<Blob | null>((resolve) => {
      canvas.toBlob((b) => resolve(b), "image/jpeg", 0.85);
    });

    if (!blob) {
      throw new Error("Failed to convert screen canvas to image blob.");
    }

    const fileName = `screen-capture-${Date.now()}.jpg`;
    const file = new File([blob], fileName, { type: "image/jpeg" });
    const preview = URL.createObjectURL(blob);

    return { file, preview };
  } catch (err: any) {
    if (stream) {
      (stream as MediaStream).getTracks().forEach((track) => track.stop());
    }
    // If user cancelled the Android/browser prompt, resolve cleanly with null
    if (
      err.name === "NotAllowedError" ||
      err.name === "AbortError" ||
      (err.message && err.message.toLowerCase().includes("permission denied")) ||
      (err.message && err.message.toLowerCase().includes("cancelled"))
    ) {
      return null;
    }
    throw err;
  }
}
