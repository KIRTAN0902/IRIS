/** Money and date helpers for the Finance section (rupees, Indian digit grouping). */

const INR = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

/** ₹1,23,456.5 */
export function inr(amount: number): string {
  const sign = amount < 0 ? "-" : "";
  return `${sign}₹${INR.format(Math.abs(amount))}`;
}

/** Short form for tight spots: ₹950 · ₹12.4K · ₹3.2L · ₹1.1Cr */
export function inrShort(amount: number): string {
  const a = Math.abs(amount);
  const sign = amount < 0 ? "-" : "";
  const fmt = (n: number, unit: string) => `${sign}₹${n >= 100 ? Math.round(n) : Number(n.toFixed(1))}${unit}`;
  if (a >= 1e7) return fmt(a / 1e7, "Cr");
  if (a >= 1e5) return fmt(a / 1e5, "L");
  if (a >= 1e3) return fmt(a / 1e3, "K");
  return `${sign}₹${Math.round(a)}`;
}

/** Local calendar date as YYYY-MM-DD. */
export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export const currentMonth = () => todayIso().slice(0, 7);

/** "2026-10" -> Date (local, 1st of the month). */
const monthDate = (month: string) => new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)) - 1, 1);

export function shiftMonth(month: string, by: number): string {
  const d = monthDate(month);
  d.setMonth(d.getMonth() + by);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export const monthName = (month: string, style: "long" | "short" = "long") =>
  monthDate(month).toLocaleDateString("en-IN", { month: style });

export const monthLabel = (month: string) =>
  monthDate(month).toLocaleDateString("en-IN", { month: "long", year: "numeric" });

/** "2026-10-08" -> Date at local midnight. */
export const parseDay = (iso: string) => new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)));

export const fmtDay = (iso: string) =>
  parseDay(iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });

/** "Today", "Yesterday", or "Wed, 8 Oct". */
export function dayHeading(iso: string): string {
  const diff = Math.round((parseDay(todayIso()).getTime() - parseDay(iso).getTime()) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Yesterday";
  return fmtDay(iso);
}

/** "Due today" / "Due in 3 days" / "2 days overdue". */
export function dueLabel(days: number): { text: string; tone: "critical" | "caution" | "normal" } {
  if (days < 0) return { text: `${-days} day${days === -1 ? "" : "s"} overdue`, tone: "critical" };
  if (days === 0) return { text: "Due today", tone: "caution" };
  if (days === 1) return { text: "Due tomorrow", tone: "caution" };
  return { text: `Due in ${days} days`, tone: days <= 3 ? "caution" : "normal" };
}

export const titleCase = (s: string) => s.charAt(0) + s.slice(1).toLowerCase();
