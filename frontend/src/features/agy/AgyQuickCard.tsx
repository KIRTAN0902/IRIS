import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, Loader2, SquareTerminal } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Lamp } from "@/components/ui/Panel";
import { agyApi, type AgySession } from "@/features/agy/agyApi";

export function AgyQuickCard() {
  const [session, setSession] = useState<AgySession | null>(null);
  const [prompt, setPrompt] = useState("");
  const [sending, setSending] = useState(false);

  const refresh = async () => {
    try {
      const res = await agyApi.list();
      const key = res.current_session_key;
      setSession(res.sessions.find((item) => item.key === key) ?? res.sessions[0] ?? null);
    } catch {
      setSession(null);
    }
  };

  useEffect(() => {
    void refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  const send = async () => {
    if (!session || !prompt.trim()) return;
    setSending(true);
    try {
      await agyApi.input(prompt.trim(), session.key);
      setPrompt("");
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="rounded-xl border border-ops-line-bright bg-ops-panel/50 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SquareTerminal size={17} className="text-ai" />
        <h2 className="text-[14px] font-semibold text-ink">Antigravity Remote Terminal</h2>
        <span className="flex items-center gap-1.5 rounded-full border border-ops-line bg-ops-raised/50 px-2 py-0.5">
          <Lamp tone={session?.state === "BUSY" ? "ai" : session ? "go" : "dim"} pulse={session?.state === "BUSY"} />
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink-dim">
            {session ? `${session.alias} · ${session.state}` : "No session"}
          </span>
        </span>
        <Link
          to="/agy"
          className="ml-auto inline-flex items-center gap-1 text-[12px] text-ai hover:underline"
        >
          Full deck <ArrowUpRight size={12} />
        </Link>
      </div>
      <p className="mt-1.5 text-[12px] text-ink-dim">
        One persistent `agy` session drives phone prompts, Mesh commands, and the Operator agent.
      </p>
      {session ? (
        <div className="mt-3 space-y-2">
          <p className="truncate font-mono text-[10.5px] text-ink-faint">{session.directory}</p>
          <div className="flex gap-2">
            <input
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && void send()}
              placeholder="Send a coding instruction from your phone…"
              className="min-w-0 flex-1 rounded-md border border-ops-line-bright bg-ops-ground/70 px-3 py-1.5 font-mono text-[12px] text-ink outline-none focus:border-ai"
            />
            <Button size="sm" onClick={send} disabled={!prompt.trim() || sending}>
              {sending ? <Loader2 size={12} className="animate-spin" /> : null}
              Send
            </Button>
          </div>
          {session.last_summary && (
            <p className="text-[11.5px] text-ink-faint">Last: {session.last_summary}</p>
          )}
        </div>
      ) : (
        <div className="mt-3">
          <Link
            to="/agy"
            className="inline-flex h-7 items-center rounded-md border border-ops-line-bright px-2.5 text-[12px] text-ink transition-colors hover:bg-ops-raised"
          >
            Attach a workspace
          </Link>
        </div>
      )}
    </section>
  );
}
