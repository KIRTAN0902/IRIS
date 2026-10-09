import type { ExerciseIn, WorkoutIn } from "@/types/api";

/**
 * Turn a workout table copied from Notion (or Docs, Sheets, a markdown table)
 * into a workout. Understands tab- or pipe-separated rows, a header row naming
 * the columns, and optional "Sunday – CST (Chest, Shoulders, Triceps)" and
 * "Total Time: ~75–85 minutes" lines above the table.
 */

const DAY_PREFIX: Record<string, string> = {
  mon: "Mon", tue: "Tue", wed: "Wed", thu: "Thu", fri: "Fri", sat: "Sat", sun: "Sun",
};

type Column = keyof ExerciseIn;
const HEADER_MATCHERS: [RegExp, Column][] = [
  [/exercise|movement|name/i, "name"],
  [/set|rep/i, "sets_reps"],
  [/muscle|target/i, "muscles"],
  [/weight|kg|load|lbs/i, "weight"],
  [/time|duration|rest/i, "time"],
  [/note/i, "notes"],
];
const DEFAULT_ORDER: Column[] = ["name", "sets_reps", "time", "muscles", "weight", "notes"];

const blank = (s: string) => (/^[\s—–-]*$/.test(s) ? "" : s.trim());

function splitRow(line: string): string[] | null {
  if (line.includes("\t")) return line.split("\t").map((c) => c.trim());
  if (line.includes("|")) {
    const cells = line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
    return cells.every((c) => /^:?-{2,}:?$/.test(c) || c === "") ? [] : cells; // [] = markdown separator row
  }
  return null;
}

export function parseWorkoutTable(text: string): { workout: Partial<WorkoutIn>; exercises: ExerciseIn[] } {
  const workout: Partial<WorkoutIn> = {};
  const rows: string[][] = [];

  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    const cells = splitRow(line);
    if (cells === null) {
      // Title or metadata line above the table.
      const total = line.match(/total\s*time\s*:?\s*~?\s*([\d–\-\s]+)\s*(min|minutes|mins|hr|hours?)?/i);
      if (total) {
        workout.duration = `${total[1].trim()} ${/h/i.test(total[2] ?? "") ? "hr" : "min"}`;
        continue;
      }
      const title = line.match(/^(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*[–—:-]\s*(.+?)\.?$/i);
      if (title) {
        workout.days_of_week = DAY_PREFIX[title[1].toLowerCase()];
        const named = title[2].match(/^(.*?)\s*\((.+)\)\s*$/);
        workout.name = (named ? named[1] : title[2]).trim();
        if (named) workout.focus = named[2].trim();
      }
      continue;
    }
    if (cells.length) rows.push(cells);
  }

  if (!rows.length) return { workout, exercises: [] };

  let columns = DEFAULT_ORDER;
  const looksLikeHeader = rows[0].some((c) => /exercise|sets|reps|weight|muscle/i.test(c));
  if (looksLikeHeader) {
    columns = rows[0].map((h) => HEADER_MATCHERS.find(([re]) => re.test(h))?.[1] ?? "notes");
    rows.shift();
  }

  const exercises = rows
    .map((cells) => {
      const ex: ExerciseIn = { name: "" };
      cells.forEach((cell, i) => {
        const col = columns[i];
        const value = blank(cell);
        if (!col || !value) return;
        ex[col] = col === "notes" && ex.notes ? `${ex.notes}; ${value}` : value;
      });
      return ex;
    })
    .filter((e) => e.name);

  return { workout, exercises };
}
