import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/api/client";
import { voiceApi } from "@/api/endpoints";

/**
 * Hands-free voice conversation: listen → transcribe → ask IRIS → speak → listen.
 *
 * Speech goes through the backend's configured models (AI_STT_* / AI_TTS_*).
 * When those are off, rate-limited or failing, it falls back to the phone's
 * own speech recognition and voice so a conversation never just stops.
 */

export type VoicePhase = "off" | "starting" | "listening" | "transcribing" | "thinking" | "speaking";

/** The phone's fallback recognizer: Hindi also picks up English words. */
const FALLBACK_LANG = "hi-IN";
/** A pause this long ends what the user is saying. */
const SILENCE_MS = 1300;
/** Stop listening if nothing is said for this long. */
const NO_SPEECH_MS = 9000;
const MAX_UTTERANCE_MS = 45_000;
/** After a provider rate limit, use the phone's voice for this long. */
const TTS_COOLDOWN_MS = 60_000;

const RECORDING_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

// The Web Speech API isn't in TypeScript's DOM types.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Recognizer = any;
function recognizerClass(): (new () => Recognizer) | null {
  const w = window as unknown as Record<string, unknown>;
  return (w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null) as (new () => Recognizer) | null;
}
const canRecord = () => typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

interface Session {
  active: boolean;
  stt: "server" | "browser";
  ttsServer: boolean;
  ttsBlockedUntil: number;
  audio: HTMLAudioElement;
  ctx: AudioContext | null;
  analyser: AnalyserNode | null;
  stream: MediaStream | null;
  /** Finish the current recording now (the user tapped "done"). */
  finish?: () => void;
  /** Cut off the reply being spoken. */
  interrupt?: () => void;
}

export function useVoiceConversation(onUtterance: (text: string) => Promise<string | null>) {
  const [phase, setPhase] = useState<VoicePhase>("off");
  const [heard, setHeard] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const session = useRef<Session | null>(null);
  const onUtteranceRef = useRef(onUtterance);
  onUtteranceRef.current = onUtterance;

  const end = useCallback(() => {
    const s = session.current;
    if (!s) return;
    s.active = false;
    s.finish?.();
    s.interrupt?.();
    s.stream?.getTracks().forEach((t) => t.stop());
    s.ctx?.close().catch(() => {});
    session.current = null;
    setPhase("off");
  }, []);

  useEffect(() => end, [end]);

  // --- listening ---------------------------------------------------------------

  /** Record until the user pauses; null if they said nothing. */
  const record = (s: Session) =>
    new Promise<Blob | null>((resolve) => {
      const mimeType = RECORDING_TYPES.find((t) => MediaRecorder.isTypeSupported?.(t));
      const rec = new MediaRecorder(s.stream!, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      const samples = new Float32Array(s.analyser!.fftSize);
      const started = performance.now();
      let floor = 0.01;
      let loudFrames = 0;
      let spoke = false;
      let lastVoice = started;

      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        clearInterval(timer);
        s.finish = undefined;
        resolve(spoke && chunks.length ? new Blob(chunks, { type: rec.mimeType || mimeType || "audio/webm" }) : null);
      };
      const stop = () => rec.state !== "inactive" && rec.stop();
      s.finish = () => {
        if (performance.now() - started > 600) spoke = true;
        stop();
      };

      // Voice activity: louder than the room for a few frames = speech; a long
      // enough quiet stretch after that = the end of what they said.
      const timer = setInterval(() => {
        s.analyser!.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const v of samples) sum += v * v;
        const rms = Math.sqrt(sum / samples.length);
        const now = performance.now();
        if (now - started < 250) {
          floor = Math.min(Math.max(floor, rms), 0.05); // calibrate to the room
          return;
        }
        if (rms > Math.max(0.02, floor * 2.2)) {
          lastVoice = now;
          if (++loudFrames >= 3) spoke = true;
        } else if (!spoke) {
          loudFrames = 0;
        }
        if (spoke && now - lastVoice > SILENCE_MS) stop();
        else if (!spoke && now - started > NO_SPEECH_MS) stop();
        else if (now - started > MAX_UTTERANCE_MS) stop();
      }, 50);

      rec.start(250);
    });

  /** The phone's own recognizer (fallback). */
  const recognize = (s: Session) =>
    new Promise<string | null>((resolve) => {
      const Ctor = recognizerClass();
      if (!Ctor) return resolve(null);
      const r = new Ctor();
      r.lang = FALLBACK_LANG;
      r.interimResults = true;
      r.continuous = false;
      let text = "";
      r.onresult = (e: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => {
        text = Array.from(e.results, (res) => res[0].transcript).join(" ");
        setHeard(text);
      };
      r.onerror = () => {};
      r.onend = () => {
        s.finish = undefined;
        resolve(text.trim() || null);
      };
      s.finish = () => r.stop();
      r.start();
    });

  /** What the user said: "" = couldn't make it out, null = said nothing. */
  const listen = async (s: Session): Promise<string | null> => {
    if (s.stt === "browser") return recognize(s);
    const clip = await record(s);
    if (!clip || !s.active) return null;
    setPhase("transcribing");
    try {
      return (await voiceApi.transcribe(clip)).text.trim();
    } catch (err) {
      if (!recognizerClass()) throw err;
      s.stt = "browser";
      setNotice(
        err instanceof ApiError && err.status === 429
          ? "The voice model hit its limit, so I'm using your phone's speech recognition. Please say that again."
          : "The voice model isn't responding, so I'm using your phone's speech recognition. Please say that again.",
      );
      setPhase("listening");
      return recognize(s);
    }
  };

  // --- speaking ----------------------------------------------------------------

  const play = (s: Session, blob: Blob) =>
    new Promise<void>((resolve) => {
      const url = URL.createObjectURL(blob);
      const a = s.audio;
      const done = () => {
        a.onended = a.onerror = null;
        s.interrupt = undefined;
        URL.revokeObjectURL(url);
        resolve();
      };
      a.onended = a.onerror = done;
      s.interrupt = () => {
        a.pause();
        done();
      };
      a.src = url;
      a.play().catch(done);
    });

  const speakWithPhone = (s: Session, text: string) =>
    new Promise<void>((resolve) => {
      if (!("speechSynthesis" in window)) return resolve();
      const u = new SpeechSynthesisUtterance(text);
      u.lang = /[઀-૿]/.test(text) ? "gu-IN" : /[ऀ-ॿ]/.test(text) ? "hi-IN" : "en-IN";
      const voice = speechSynthesis.getVoices().find((v) => v.lang.replace("_", "-") === u.lang);
      if (voice) u.voice = voice;
      const done = () => {
        s.interrupt = undefined;
        resolve();
      };
      u.onend = u.onerror = done;
      s.interrupt = () => {
        speechSynthesis.cancel();
        done();
      };
      speechSynthesis.speak(u);
    });

  const speak = async (s: Session, text: string) => {
    if (s.ttsServer && Date.now() > s.ttsBlockedUntil) {
      try {
        const audio = await voiceApi.speak(text);
        if (s.active) await play(s, audio);
        return;
      } catch (err) {
        if (err instanceof ApiError && err.status === 429) s.ttsBlockedUntil = Date.now() + TTS_COOLDOWN_MS;
        else if (err instanceof ApiError && err.code === "VOICE_UNAVAILABLE") s.ttsServer = false;
      }
    }
    if (s.active) await speakWithPhone(s, text);
  };

  // --- the conversation loop ------------------------------------------------------

  const converse = async (s: Session) => {
    let misses = 0;
    try {
      while (s.active) {
        setPhase("listening");
        setHeard("");
        const text = await listen(s);
        if (!s.active) break;
        if (text === null) {
          setNotice("I didn't hear anything, so I stopped listening.");
          break;
        }
        if (!text) {
          if (++misses >= 2) {
            setNotice("I couldn't make that out. Tap the mic to try again.");
            break;
          }
          setNotice("Sorry, I didn't catch that. Please say it again.");
          continue;
        }
        misses = 0;
        setHeard(text);
        setPhase("thinking");
        const reply = await onUtteranceRef.current(text);
        if (!s.active) break;
        if (!reply) {
          setNotice("Couldn't reach IRIS.");
          break;
        }
        setNotice(null);
        setPhase("speaking");
        await speak(s, toSpeech(reply));
      }
    } catch {
      setNotice("Voice stopped working. Tap the mic to try again.");
    } finally {
      if (session.current === s) end();
    }
  };

  const start = useCallback(async () => {
    if (session.current) return;
    // Unlock audio playback while we're still inside the user's tap.
    const audio = new Audio(silentWavUrl());
    audio.play().catch(() => {});
    if ("speechSynthesis" in window) speechSynthesis.speak(new SpeechSynthesisUtterance(""));
    const ctx = canRecord() ? new AudioContext() : null;
    ctx?.resume().catch(() => {});

    const s: Session = {
      active: true,
      stt: "browser",
      ttsServer: false,
      ttsBlockedUntil: 0,
      audio,
      ctx,
      analyser: null,
      stream: null,
    };
    session.current = s;
    setNotice(null);
    setHeard("");
    setPhase("starting");

    const status = await voiceApi.status().catch(() => null);
    s.ttsServer = !!status?.tts.enabled;
    s.stt = status?.stt.enabled && ctx ? "server" : "browser";
    if (s.stt === "browser" && !recognizerClass()) {
      setNotice("Voice input isn't supported in this browser.");
      return end();
    }
    if (s.stt === "server") {
      try {
        s.stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        if (!s.active) return s.stream.getTracks().forEach((t) => t.stop());
        s.analyser = ctx!.createAnalyser();
        s.analyser.fftSize = 1024;
        ctx!.createMediaStreamSource(s.stream).connect(s.analyser);
      } catch {
        setNotice("Microphone access is blocked. Allow it for this site in your browser settings.");
        return end();
      }
    }
    if (s.active) void converse(s);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [end]);

  /** Tap the orb: finish speaking now, or cut IRIS off and talk. */
  const tap = useCallback(() => {
    const s = session.current;
    if (!s) return;
    if (s.interrupt) s.interrupt();
    else s.finish?.();
  }, []);

  return { phase, heard, notice, start, end, tap, dismissNotice: () => setNotice(null) };
}

/** Plain, speakable text: no markdown, and short enough to read aloud. */
export function toSpeech(markdown: string, max = 600): string {
  const text = markdown
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]*)`/g, "$1")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/^\s*\|.*\|\s*$/gm, " ")
    .replace(/^\s*(#{1,6}|[-*+•]|\d+[.)])\s+/gm, "")
    .replace(/[*_~>#]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (text.length <= max) return text;
  const cut = text.slice(0, max);
  const end = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("? "), cut.lastIndexOf("! "), cut.lastIndexOf("। "));
  return end > max / 3 ? cut.slice(0, end + 1) : `${cut}…`;
}

let silentUrl: string | null = null;
/** A tiny silent clip, played on the first tap so later replies may autoplay. */
function silentWavUrl(): string {
  if (silentUrl) return silentUrl;
  const n = 800;
  const view = new DataView(new ArrayBuffer(44 + n * 2));
  const str = (o: number, s: string) => [...s].forEach((c, i) => view.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF");
  view.setUint32(4, 36 + n * 2, true);
  str(8, "WAVE");
  str(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 8000, true);
  view.setUint32(28, 16000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  str(36, "data");
  view.setUint32(40, n * 2, true);
  silentUrl = URL.createObjectURL(new Blob([view.buffer], { type: "audio/wav" }));
  return silentUrl;
}
