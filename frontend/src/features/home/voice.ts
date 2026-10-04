import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/api/client";
import { voiceApi, type VoiceStatus } from "@/api/endpoints";

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
const SILENCE_MS = 1000;
/** Stop listening if nothing is said for this long. */
const NO_SPEECH_MS = 9000;
const MAX_UTTERANCE_MS = 30_000;
/** After a provider rate limit, use the phone's voice for this long. */
const TTS_COOLDOWN_MS = 60_000;
/** Don't wait longer than this for the voice model; the phone's voice is instant. */
const TTS_WAIT_MS = 7000;
/** Talking over IRIS for this long interrupts it. */
const BARGE_IN_MS = 450;
/** Ignore the start of IRIS's reply, when its own voice is loudest in the mic. */
const BARGE_IN_GRACE_MS = 700;

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
  /** Stream replies as they're generated (falls back to whole clips). */
  ttsStream: boolean;
  ttsBlockedUntil: number;
  audio: HTMLAudioElement;
  ctx: AudioContext | null;
  analyser: AnalyserNode | null;
  stream: MediaStream | null;
  /** Latest microphone loudness (RMS) while recording. */
  level: number;
  /** The room's background loudness, learned while listening. */
  floor: number;
  /** What IRIS last said, to tell its own echo apart from the user. */
  lastSaid: string;
  /** The user started talking over IRIS's reply. */
  bargedIn: boolean;
  /** Finish the current recording now (the user tapped "done"). */
  finish?: () => void;
  /** Cut off the reply being spoken. */
  interrupt?: () => void;
}

export function useVoiceConversation(onUtterance: (text: string) => Promise<string | null>) {
  const [phase, setPhase] = useState<VoicePhase>("off");
  const [heard, setHeard] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  /** What IRIS is saying right now (shown as a caption). */
  const [said, setSaid] = useState("");
  const session = useRef<Session | null>(null);
  const onUtteranceRef = useRef(onUtterance);
  onUtteranceRef.current = onUtterance;

  const end = useCallback(() => {
    const s = session.current;
    if (!s) return;
    s.active = false;
    s.audio.pause();
    s.finish?.();
    s.interrupt?.();
    s.stream?.getTracks().forEach((t) => t.stop());
    s.ctx?.close().catch(() => {});
    session.current = null;
    setPhase("off");
  }, []);

  useEffect(() => end, [end]);

  // --- listening ---------------------------------------------------------------

  /** Record until the user pauses; null if they said nothing. ``talking``: they already started. */
  const record = (s: Session, talking = false) =>
    new Promise<Blob | null>((resolve) => {
      const mimeType = RECORDING_TYPES.find((t) => MediaRecorder.isTypeSupported?.(t));
      const rec = new MediaRecorder(s.stream!, mimeType ? { mimeType } : undefined);
      const chunks: Blob[] = [];
      const samples = new Float32Array(s.analyser!.fftSize);
      const started = performance.now();
      let floor = talking ? s.floor : 0.01; // the room's background level, tracked continuously
      let voiceLevel = 0; // how loud the user speaks
      let loudFrames = talking ? 3 : 0;
      let spoke = talking;
      let lastVoice = started;

      rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      rec.onstop = () => {
        clearInterval(timer);
        s.level = 0;
        s.floor = floor;
        s.finish = undefined;
        resolve(spoke && chunks.length ? new Blob(chunks, { type: rec.mimeType || mimeType || "audio/webm" }) : null);
      };
      const stop = () => rec.state !== "inactive" && rec.stop();
      s.finish = () => {
        if (performance.now() - started > 600) spoke = true;
        stop();
      };

      // Voice activity: clearly louder than the room for a few frames = speech.
      // After that, quiet relative to the user's own voice (not an absolute level,
      // which a fan or traffic can stay above) for SILENCE_MS = they're done.
      const timer = setInterval(() => {
        s.analyser!.getFloatTimeDomainData(samples);
        let sum = 0;
        for (const v of samples) sum += v * v;
        const rms = Math.sqrt(sum / samples.length);
        s.level = rms;
        const now = performance.now();
        if (!talking && now - started < 250) {
          floor = Math.min(Math.max(floor, rms), 0.05); // first guess at the room
          return;
        }
        const speechThreshold = Math.max(0.015, floor * 2.5);
        const silenceThreshold = spoke ? Math.max(floor * 1.6, voiceLevel * 0.3) : speechThreshold;
        if (rms > (spoke ? silenceThreshold : speechThreshold)) {
          lastVoice = now;
          voiceLevel = voiceLevel ? voiceLevel * 0.9 + rms * 0.1 : rms;
          if (++loudFrames >= 3) spoke = true;
        } else {
          if (!spoke) loudFrames = 0;
          floor = floor * 0.97 + rms * 0.03; // follow the room when nobody is talking
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
  const listen = async (s: Session, talking = false): Promise<string | null> => {
    if (s.stt === "browser") return recognize(s);
    const clip = await record(s, talking);
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

  /** Play raw 16-bit mono PCM while it streams in, scheduled gap-free on the AudioContext. */
  const playPcm = (s: Session, response: Response, rate: number) =>
    new Promise<void>((resolve) => {
      const ctx = s.ctx!;
      const reader = response.body!.getReader();
      const sources: AudioBufferSourceNode[] = [];
      let head = ctx.currentTime + 0.08;
      let carry: Uint8Array | null = null;
      let stopped = false;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        s.interrupt = undefined;
        resolve();
      };
      s.interrupt = () => {
        stopped = true;
        reader.cancel().catch(() => {});
        sources.forEach((src) => {
          try {
            src.stop();
          } catch {
            /* not started yet */
          }
        });
        finish();
      };

      void (async () => {
        try {
          for (;;) {
            const { value, done } = await reader.read();
            if (done || stopped) break;
            let bytes = value;
            if (carry) {
              bytes = new Uint8Array(carry.length + value.length);
              bytes.set(carry);
              bytes.set(value, carry.length);
            }
            const even = bytes.length - (bytes.length % 2);
            carry = even < bytes.length ? bytes.slice(even) : null;
            if (!even) continue;
            const pcm = new Int16Array(bytes.slice(0, even).buffer);
            const buffer = ctx.createBuffer(1, pcm.length, rate);
            const channel = buffer.getChannelData(0);
            for (let i = 0; i < pcm.length; i++) channel[i] = pcm[i] / 32768;
            const src = ctx.createBufferSource();
            src.buffer = buffer;
            src.connect(ctx.destination);
            head = Math.max(head, ctx.currentTime + 0.02); // a late chunk starts now
            src.start(head);
            head += buffer.duration;
            sources.push(src);
          }
        } catch {
          /* network hiccup: play what arrived */
        }
        if (!stopped) window.setTimeout(finish, Math.max(0, (head - ctx.currentTime) * 1000) + 60);
      })();
    });

  /** While IRIS talks, listen for the user talking over it. */
  const watchForBargeIn = (s: Session) => {
    if (!s.analyser) return () => {};
    const samples = new Float32Array(s.analyser.fftSize);
    const started = performance.now();
    let loud = 0;
    const timer = window.setInterval(() => {
      if (performance.now() - started < BARGE_IN_GRACE_MS || !s.interrupt) return;
      s.analyser!.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const v of samples) sum += v * v;
      const rms = Math.sqrt(sum / samples.length);
      loud = rms > Math.max(0.08, s.floor * 4) ? loud + 1 : 0;
      if (loud * 50 >= BARGE_IN_MS) {
        window.clearInterval(timer);
        s.bargedIn = true;
        s.interrupt?.();
      }
    }, 50);
    return () => window.clearInterval(timer);
  };

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
    s.lastSaid = text;
    const rateLimited = (err: unknown) => err instanceof ApiError && err.status === 429;

    // 1. Streamed: starts playing while the rest of the audio is generated.
    if (s.ttsServer && s.ttsStream && s.ctx && Date.now() > s.ttsBlockedUntil) {
      try {
        const response = await withTimeout(voiceApi.speakStream(text), TTS_WAIT_MS);
        if (s.active) await playPcm(s, response, Number(response.headers.get("X-Sample-Rate")) || 24000);
        return;
      } catch (err) {
        if (rateLimited(err)) s.ttsBlockedUntil = Date.now() + TTS_COOLDOWN_MS;
        else if (err instanceof ApiError) s.ttsStream = false; // provider can't stream: use whole clips
      }
    }
    // 2. Whole clip.
    if (s.ttsServer && !s.ttsStream && Date.now() > s.ttsBlockedUntil) {
      try {
        const audio = await withTimeout(voiceApi.speak(text), TTS_WAIT_MS);
        if (s.active) await play(s, audio);
        return;
      } catch (err) {
        if (rateLimited(err)) s.ttsBlockedUntil = Date.now() + TTS_COOLDOWN_MS;
        else if (err instanceof ApiError && err.code === "VOICE_UNAVAILABLE") s.ttsServer = false;
      }
    }
    // 3. The phone's own voice.
    if (s.active) await speakWithPhone(s, text);
  };

  // --- the conversation loop ------------------------------------------------------

  const converse = async (s: Session) => {
    let misses = 0;
    try {
      while (s.active) {
        setPhase("listening");
        setHeard("");
        setSaid("");
        const interrupted = s.bargedIn;
        s.bargedIn = false;
        const text = await listen(s, interrupted);
        if (!s.active) break;
        if (interrupted && text && isEcho(text, s.lastSaid)) continue; // the mic heard IRIS itself
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
        const spoken = toSpeech(reply);
        setSaid(spoken);
        setPhase("speaking");
        const stopWatching = watchForBargeIn(s);
        await speak(s, spoken);
        stopWatching();
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
    const ctx = typeof AudioContext !== "undefined" ? new AudioContext() : null;
    ctx?.resume().catch(() => {});

    const s: Session = {
      active: true,
      stt: "browser",
      ttsServer: false,
      ttsStream: true,
      ttsBlockedUntil: 0,
      audio,
      ctx,
      analyser: null,
      stream: null,
      level: 0,
      floor: 0.01,
      lastSaid: "",
      bargedIn: false,
    };
    session.current = s;
    setNotice(null);
    setHeard("");
    setPhase("starting");

    statusRequest ??= voiceApi.status().catch(() => {
      statusRequest = null;
      return null;
    });
    const status = await statusRequest;
    s.ttsServer = !!status?.tts.enabled;
    s.stt = status?.stt.enabled && ctx && canRecord() ? "server" : "browser";
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

  /** Mic loudness for visuals, 0..1. */
  const level = useCallback(() => Math.min(1, Math.max(0, ((session.current?.level ?? 0) - 0.01) * 7)), []);

  return { phase, heard, said, notice, level, start, end, tap, dismissNotice: () => setNotice(null) };
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

function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    promise,
    new Promise<never>((_, reject) => window.setTimeout(() => reject(new Error("timeout")), ms)),
  ]);
}

const words = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter(Boolean);

/** True when what the mic heard is mostly IRIS's own reply (speaker echo). */
export function isEcho(heard: string, said: string): boolean {
  const h = words(heard);
  if (h.length < 2) return false;
  const spoken = new Set(words(said));
  return h.filter((w) => spoken.has(w)).length / h.length >= 0.6;
}

let statusRequest: Promise<VoiceStatus | null> | null = null;

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
