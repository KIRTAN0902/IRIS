import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// --- Time formatting (backend stores naive UTC; convert to user's local view) --

export function parseUtc(iso: string): Date {
  // Backend datetimes are naive UTC; ensure the browser treats them as UTC.
  return new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
}

export function fmtTime(iso: string): string {
  return parseUtc(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

/** 24h instrument clock — schedule rows, telemetry. */
export function fmtTime24(iso: string): string {
  return parseUtc(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

/** Naive-UTC ISO string (what the backend stores/compares). */
export function toNaiveUtc(d: Date): string {
  return d.toISOString().slice(0, 19);
}

export function fmtDay(iso: string): string {
  return parseUtc(iso).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" });
}

export function fmtDateTime(iso: string): string {
  const d = parseUtc(iso);
  const today = new Date();
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay
    ? `today ${fmtTime(iso)}`
    : `${fmtDay(iso)} ${fmtTime(iso)}`;
}

export function minutesUntil(iso: string): number {
  return Math.round((parseUtc(iso).getTime() - Date.now()) / 60000);
}

export function humanDuration(minutes: number | null | undefined): string {
  if (minutes == null) return "—";
  const m = Math.max(0, Math.round(minutes));
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return rem ? `${h}h ${rem}m` : `${h}h`;
}

/** Relative urgency label on the single vertical axis: top = now. */
export function urgencyLabel(iso: string): { text: string; tone: "critical" | "caution" | "dim" } {
  const mins = minutesUntil(iso);
  if (mins < 0) return { text: `overdue ${humanDuration(-mins)}`, tone: "critical" };
  if (mins <= 90) return { text: `due in ${mins}m`, tone: "critical" };
  if (mins <= 24 * 60) return { text: `due in ${humanDuration(mins)}`, tone: mins <= 3 * 60 ? "critical" : "caution" };
  return { text: `due ${fmtDateTime(iso)}`, tone: "dim" };
}

export function greeting(): string {
  const h = new Date().getHours();
  if (h < 5) return "Late night";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}
