import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowUpRight,
  ChevronDown,
  CircleDot,
  GitCompareArrows,
  Loader2,
  Mic,
  MicOff,
  Plug,
  SquareTerminal,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Lamp } from "@/components/ui/Panel";
import { voiceApi } from "@/api/endpoints";
import {
  agyApi,
  agyStreamUrl,
  type AgySession,
  type AgyWorkspace,
} from "@/features/agy/agyApi";

const QUICK_COMMANDS = ["/resume", "/models", "/usage", "/status", "/compact", "/help"];

type WireMessage = {
  type: string;
  data?: string;
  backlog?: string;
  session?: AgySession;
  state?: string;
};

function stateTone(state: AgySession["state"] | undefined) {
  if (state === "BUSY") return "ai" as const;
  if (state === "IDLE") return "go" as const;
  return "caution" as const;
}

export function AgyTerminalDeck({
  variant = "page",
  onClose,
}: {
  variant?: "page" | "drawer";
  onClose?: () => void;
}) {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<AgySession[]>([]);
  const [workspaces, setWorkspaces] = useState<AgyWorkspace[]>([]);
  const [currentKey, setCurrentKey] = useState<string | null>(null);
  const [selectedWorkspace, setSelectedWorkspace] = useState("");
  const [output, setOutput] = useState("");
  const [input, setInput] = useState("");
  const [connected, setConnected] = useState(false);
  const [attaching, setAttaching] = useState(false);
  const [recording, setRecording] = useState(false);
  const [showDiff, setShowDiff] = useState(false);
  const [diff, setDiff] = useState("");
  const [diffStat, setDiffStat] = useState("");
  const [error, setError] = useState("");

  const socketRef = useRef<WebSocket | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const current = sessions.find((session) => session.key === currentKey) ?? null;

  const loadSessions = useCallback(async () => {
    try {
      const res = await agyApi.list();
      setSessions(res.sessions);
      setWorkspaces(res.workspaces);
      if (res.current_session_key) {
        setCurrentKey((prev) => prev ?? res.current_session_key);
      }
      setSelectedWorkspace((prev) => prev || res.workspaces[0]?.alias || "");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not reach the Antigravity bridge.");
    }
  }, []);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    if (!currentKey) {
      setConnected(false);
      return;
    }
    setOutput("");
    const socket = new WebSocket(agyStreamUrl(currentKey));
    socketRef.current = socket;
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onerror = () => setConnected(false);
    socket.onmessage = (event) => {
      let message: WireMessage;
      try {
        message = JSON.parse(event.data as string) as WireMessage;
      } catch {
        return;
      }
      if (message.type === "session" && message.session) {
        const session = message.session;
        setSessions((prev) => {
          const rest = prev.filter((item) => item.key !== session.key);
          return [...rest, session];
        });
        setOutput(message.backlog ?? "");
      } else if (message.type === "output" && message.data) {
        setOutput((prev) => (prev + message.data).slice(-160_000));
      } else if (message.type === "ack" && message.state && currentKey) {
        setSessions((prev) =>
          prev.map((item) =>
            item.key === currentKey
              ? { ...item, state: message.state as AgySession["state"] }
              : item,
          ),
        );
      }
    };
    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [currentKey]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [output]);

  const attach = async () => {
    if (!selectedWorkspace) return;
    setAttaching(true);
    setError("");
    try {
      const res = await agyApi.attach(selectedWorkspace);
      setSessions((prev) => {
        const rest = prev.filter((item) => item.key !== res.session.key);
        return [...rest, res.session];
      });
      setOutput(res.recent_output || "");
      setCurrentKey(res.session.key);
      setShowDiff(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not attach to workspace.");
    } finally {
      setAttaching(false);
    }
  };

  const send = async (text: string, slash = false) => {
    const clean = text.trim();
    if (!clean || !currentKey) return;
    setError("");
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: slash ? "slash" : "input", data: clean }));
    } else {
      try {
        if (slash) await agyApi.slash(clean, currentKey);
        else await agyApi.input(clean, currentKey);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Send failed.");
      }
    }
    setInput("");
  };

  const toggleDiff = async () => {
    if (!currentKey) return;
    try {
      const res = await agyApi.status(currentKey);
      setDiff(res.last_diff || "");
      setDiffStat(res.last_diff_stat || "");
      setShowDiff((prev) => !prev);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the git diff.");
    }
  };

  const closeSession = async () => {
    if (!currentKey) return;
    try {
      await agyApi.close(currentKey);
    } catch {
      // The session may already be gone; clear the local view either way.
    }
    setCurrentKey(null);
    setSessions((prev) => prev.filter((item) => item.key !== currentKey));
    setOutput("");
  };

  const toggleRecording = async () => {
    if (recording) {
      recorderRef.current?.stop();
      setRecording(false);
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size) chunksRef.current.push(event.data);
      };
      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        const blob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        try {
          const { text } = await voiceApi.transcribe(blob);
          setInput((prev) => (prev ? `${prev} ${text}` : text));
        } catch (err) {
          setError(err instanceof Error ? err.message : "Transcription failed.");
        }
      };
      recorder.start();
      recorderRef.current = recorder;
      setRecording(true);
    } catch {
      setError("Microphone permission is required for voice input.");
    }
  };

  const stateLabel = current ? current.state : "OFFLINE";
  const terminalHeight = variant === "drawer" ? "flex-1 min-h-0" : "h-[480px]";

  return (
    <div className={variant === "drawer" ? "flex h-full min-h-0 flex-col gap-3" : "mx-auto max-w-6xl space-y-5"}>
      <header className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <SquareTerminal size={20} className="text-ai" />
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.28em] text-ink-faint">
              Persistent ConPTY
            </p>
            <h1 className="font-['Chakra_Petch'] text-[26px] font-bold leading-none tracking-tight text-ink">
              ANTIGRAVITY
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-ops-line bg-ops-raised/40 px-3 py-1">
          <Lamp tone={stateTone(current?.state)} pulse={current?.state === "BUSY"} />
          <span className="font-mono text-[11px] uppercase tracking-wider text-ink-dim">
            {stateLabel}
          </span>
        </div>
        {current && (
          <span className="font-mono text-[11px] text-ink-faint">{current.directory}</span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            onClick={toggleDiff}
            disabled={!current}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-ops-line-bright px-2.5 text-[12px] text-ink-dim transition-colors hover:text-ink disabled:opacity-40"
          >
            <GitCompareArrows size={14} /> Git Diff
          </button>
          {variant === "drawer" && (
            <button
              type="button"
              onClick={() => {
                navigate("/agy");
                onClose?.();
              }}
              className="inline-flex h-8 items-center gap-1 rounded-md border border-ops-line-bright px-2.5 text-[12px] text-ink-dim transition-colors hover:text-ink"
            >
              <ArrowUpRight size={14} /> Full deck
            </button>
          )}
          {variant === "drawer" && onClose && (
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-dim hover:bg-ops-raised hover:text-ink"
              aria-label="Close Antigravity drawer"
            >
              <X size={16} />
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="rounded-md border border-critical/30 bg-critical-dim px-3 py-2 text-[12px] text-critical">
          {error}
        </div>
      )}

      {!current && (
        <div className="rounded-xl border border-ops-line-bright bg-ops-panel/60 p-4">
          <p className="mb-2 text-[13px] font-medium text-ink">Attach a persistent Antigravity session</p>
          <p className="mb-3 text-[12px] text-ink-dim">
            One long-lived `agy` process per project — the phone, Mesh relay and Operator all
            share the same context.
          </p>
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative">
              <select
                value={selectedWorkspace}
                onChange={(event) => setSelectedWorkspace(event.target.value)}
                className="h-8 appearance-none rounded-md border border-ops-line-bright bg-ops-raised pl-3 pr-8 font-mono text-[12px] text-ink outline-none focus:border-ai"
              >
                {workspaces.map((workspace) => (
                  <option key={workspace.alias} value={workspace.alias}>
                    {workspace.alias} — {workspace.path}
                  </option>
                ))}
              </select>
              <ChevronDown size={13} className="pointer-events-none absolute right-2 top-2.5 text-ink-faint" />
            </div>
            <Button size="sm" onClick={attach} disabled={attaching || !selectedWorkspace}>
              {attaching ? <Loader2 size={13} className="animate-spin" /> : <Plug size={13} />}
              {attaching ? "Attaching…" : "Attach session"}
            </Button>
          </div>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_260px]">
        <section className="flex min-w-0 flex-col overflow-hidden rounded-xl border border-ops-line-bright bg-[#080A0F]">
          <div className="flex items-center gap-2 border-b border-[#151B23] px-3 py-2">
            <span className="h-2 w-2 rounded-full bg-[#ff5f57]" />
            <span className="h-2 w-2 rounded-full bg-[#febc2e]" />
            <span className="h-2 w-2 rounded-full bg-[#28c840]" />
            <span className="ml-2 font-mono text-[11px] text-[#5b6b7c]">
              {current ? `${current.alias}@iris` : "iris@agy"}
            </span>
            <span className="ml-auto flex items-center gap-1 font-mono text-[10px] uppercase tracking-wider text-[#5b6b7c]">
              <CircleDot size={10} className={connected ? "text-emerald-400" : "text-amber-400"} />
              {connected ? "stream" : "poll"}
            </span>
          </div>

          <div
            ref={scrollRef}
            className={`${terminalHeight} overflow-y-auto px-3 py-2 font-mono text-[12.5px] leading-[1.55] text-[#c8d6e2]`}
          >
            {output ? (
              <pre className="whitespace-pre-wrap break-words">{output}</pre>
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-[#526171]">
                <SquareTerminal size={26} />
                <p className="font-mono text-[12px]">
                  {current
                    ? "Attached. Send a prompt or run a native command."
                    : "No active session. Attach a workspace above."}
                </p>
              </div>
            )}
          </div>

          {showDiff && (
            <div className="max-h-[220px] overflow-auto border-t border-[#151B23] bg-[#0D1117] px-3 py-2">
              <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-[#5b6b7c]">
                Harvested diff {diffStat ? `· ${diffStat.split("\n")[0]}` : ""}
              </p>
              <pre className="whitespace-pre-wrap break-words font-mono text-[11.5px] leading-relaxed text-[#93a7ba]">
                {diff || "No diff harvested yet."}
              </pre>
            </div>
          )}

          <div className="border-t border-[#151B23] p-2.5">
            <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1">
              {QUICK_COMMANDS.map((command) => (
                <button
                  key={command}
                  type="button"
                  disabled={!current}
                  onClick={() => void send(command, true)}
                  className="shrink-0 rounded border border-[#243040] bg-[#0D1117] px-2 py-0.5 font-mono text-[11px] text-[#8fa6bb] transition-colors hover:border-[#3a4b60] hover:text-[#d7e2ea] disabled:opacity-35"
                >
                  {command}
                </button>
              ))}
            </div>
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void send(input);
                  }
                }}
                rows={2}
                disabled={!current}
                placeholder={current ? "Ask Antigravity to build, refactor, or test…" : "Attach a session to type"}
                className="max-h-32 min-h-[52px] flex-1 resize-none rounded-md border border-[#243040] bg-[#0D1117] px-3 py-2 font-mono text-[12.5px] text-[#d7e2ea] outline-none placeholder:text-[#526171] focus:border-[#3b82f6] disabled:opacity-50"
              />
              <button
                type="button"
                onClick={() => void toggleRecording()}
                title={recording ? "Stop dictation" : "Dictate a prompt"}
                className={`inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md border transition-colors ${
                  recording
                    ? "border-red-500/50 bg-red-500/10 text-red-400"
                    : "border-[#243040] bg-[#0D1117] text-[#8fa6bb] hover:text-[#d7e2ea]"
                }`}
              >
                {recording ? <MicOff size={15} /> : <Mic size={15} />}
              </button>
              <Button
                size="sm"
                variant="solid"
                disabled={!input.trim() || !current}
                onClick={() => void send(input)}
                className="h-9"
              >
                Send
              </Button>
            </div>
          </div>
        </section>

        <aside className="space-y-3">
          <div className="rounded-xl border border-ops-line bg-ops-panel/40 p-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
              Sessions
            </p>
            <div className="space-y-1.5">
              {sessions.length === 0 && (
                <p className="text-[12px] text-ink-faint">No live sessions.</p>
              )}
              {sessions.map((session) => (
                <button
                  key={session.key}
                  type="button"
                  onClick={() => setCurrentKey(session.key)}
                  className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                    session.key === currentKey
                      ? "border-ai/40 bg-ai-dim"
                      : "border-transparent bg-ops-raised/40 hover:bg-ops-raised"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <Lamp tone={stateTone(session.state)} pulse={session.state === "BUSY"} />
                    <span className="truncate text-[12.5px] font-medium text-ink">
                      {session.alias}
                    </span>
                    <span className="ml-auto font-mono text-[10px] text-ink-faint">
                      {session.state}
                    </span>
                  </div>
                  <p className="mt-0.5 truncate font-mono text-[10.5px] text-ink-faint">
                    {session.directory}
                  </p>
                </button>
              ))}
            </div>
            {current && (
              <button
                type="button"
                onClick={() => void closeSession()}
                className="mt-2 w-full rounded-md border border-ops-line px-2 py-1.5 text-[11px] text-ink-dim transition-colors hover:border-critical/40 hover:text-critical"
              >
                Detach {current.alias}
              </button>
            )}
          </div>

          <div className="rounded-xl border border-ops-line bg-ops-panel/40 p-3">
            <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
              Workspaces
            </p>
            <div className="space-y-1">
              {workspaces.map((workspace) => (
                <button
                  key={workspace.alias}
                  type="button"
                  onClick={() => setSelectedWorkspace(workspace.alias)}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-ops-raised/60"
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      workspace.alias === selectedWorkspace ? "bg-ai" : "bg-ink-faint"
                    }`}
                  />
                  <span className="truncate font-mono text-[11.5px] text-ink-dim">
                    {workspace.alias}
                  </span>
                  {workspace.is_git && (
                    <span className="ml-auto font-mono text-[9.5px] text-ink-faint">git</span>
                  )}
                </button>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={attach}
              disabled={attaching || !selectedWorkspace}
              className="mt-2 w-full"
            >
              {attaching ? "Attaching…" : "Attach selected"}
            </Button>
          </div>

          {current?.last_summary && (
            <div className="rounded-xl border border-ops-line bg-ops-panel/40 p-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-ink-faint">
                Last harvest
              </p>
              <p className="text-[12px] leading-relaxed text-ink-dim">{current.last_summary}</p>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
