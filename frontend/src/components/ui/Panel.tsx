import type { ReactNode } from "react";
import { cn } from "@/lib/format";

/**
 * Structural container: sleek, rounded-xl panel with subtle border highlight.
 */
export function Panel({
  title,
  lamp,
  actions,
  className,
  bodyClassName,
  children,
}: {
  title?: string;
  lamp?: ReactNode;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("rounded-xl border border-ops-line bg-ops-panel shadow-sm overflow-hidden", className)}>
      {title && (
        <header className="flex items-center gap-2.5 border-b border-ops-line px-4 py-3 bg-ops-raised/50">
          {lamp && <span className="flex shrink-0 items-center">{lamp}</span>}
          <h2 className="label-caps flex-1 leading-none text-ink-dim font-bold">{title}</h2>
          {actions}
        </header>
      )}
      <div className={cn("px-4 py-3.5", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Status lamp: a smooth circular indicator. */
export function Lamp({
  tone = "dim",
  pulse = false,
  className,
}: {
  tone?: "go" | "caution" | "critical" | "ai" | "dim";
  pulse?: boolean;
  className?: string;
}) {
  const color =
    tone === "go"
      ? "bg-go"
      : tone === "caution"
        ? "bg-caution"
        : tone === "critical"
          ? "bg-critical"
          : tone === "ai"
            ? "bg-ink"
            : "bg-ink-faint";
  return (
    <span
      aria-hidden
      className={cn("inline-block h-2 w-2 rounded-full", color, pulse && "lamp-pulse", className)}
    />
  );
}

/**
 * Progress ladder — segmented instrument readout, ten ticks.
 * Discrete segments you can count; color carries the state.
 */
export function ProgressLadder({
  fraction,
  tone = "go",
  label,
  className,
}: {
  fraction: number | null | undefined;
  tone?: "go" | "caution" | "critical" | "ai";
  label?: string;
  className?: string;
}) {
  const f = Math.max(0, Math.min(1, fraction ?? 0));
  const filled = Math.round(f * 10);
  const tickColor =
    tone === "go" ? "bg-go" : tone === "caution" ? "bg-caution" : tone === "critical" ? "bg-critical" : "bg-ai";
  return (
    <div className={cn("flex items-center gap-3", className)}>
      <div className="flex h-2 flex-1 gap-[3px] rounded-full overflow-hidden" role="img" aria-label={label ?? `${Math.round(f * 100)} percent`}>
        {Array.from({ length: 10 }, (_, i) => (
          <span
            key={i}
            className={cn("flex-1 rounded-sm transition-colors", i < filled ? tickColor : "bg-ops-line")}
          />
        ))}
      </div>
      <span className="tnum text-[12px] font-medium text-ink-dim w-10 text-right">
        {Math.round(f * 100)}%
      </span>
    </div>
  );
}

/** Provenance chip — where an answer came from. AI cyan vs deterministic AUTO. */
export function ProvenanceChip({ source }: { source: "AI" | "DETERMINISTIC" }) {
  const isAI = source === "AI";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 font-[family-name:var(--font-display)] text-[10px] font-semibold uppercase tracking-[0.14em]",
        isAI ? "border-ai/40 bg-ai/10 text-ai" : "border-ops-line-bright bg-ops-panel text-ink-faint",
      )}
    >
      <Lamp tone={isAI ? "ai" : "dim"} />
      {isAI ? "AI" : "Auto"}
    </span>
  );
}

