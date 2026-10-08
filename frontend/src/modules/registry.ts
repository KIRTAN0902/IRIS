/**
 * IRIS module registry — the navigation and future-expansion contract.
 *
 * The shell renders EVERYTHING from this list. A new life domain plugs in by
 * adding one entry here plus its feature folder; no layout or component
 * surgery. `enabled: false` modules are announced as PLANNED equipment bays —
 * they never render fake pages or fake data.
 */

import {
  Activity,
  BrainCircuit,
  Briefcase,
  CalendarDays,
  Compass,
  CreditCard,
  FolderTree,
  GraduationCap,
  HeartPulse,
  LayoutGrid,
  ListChecks,
  Mail,
  Rocket,
  Target,
  Wallet,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type ModuleCategory = "command" | "work" | "startup" | "life" | "insight" | "planned";

export interface ModuleDefinition {
  id: string;
  name: string;
  icon: LucideIcon;
  /** Route path within IRIS; omitted for unbuilt modules. */
  route?: string;
  category: ModuleCategory;
  enabled: boolean;
  /** One line shown on the Modules page for planned bays. */
  brief?: string;
  glyph?: string;
}

export interface NavItem {
  id: string;
  name: string;
  route: string;
  glyph: string;
  icon: LucideIcon;
}

/**
 * The FOUR primary navigation concepts of IRIS:
 * 1. Home (⌾) — Talk to IRIS
 * 2. Schedule (▦) — When am I doing things?
 * 3. Tasks (☷) — What do I need to do? (Startup, Internship, College)
 * 4. Projects (⌁) — What am I building/managing?
 */
export const PRIMARY_NAV_ITEMS: NavItem[] = [
  {
    id: "home",
    name: "Home",
    route: "/",
    glyph: "⌾",
    icon: Compass,
  },
  {
    id: "schedule",
    name: "Schedule",
    route: "/schedule",
    glyph: "▦",
    icon: CalendarDays,
  },
  {
    id: "tasks",
    name: "Tasks",
    route: "/tasks",
    glyph: "☷",
    icon: ListChecks,
  },
  {
    id: "finance",
    name: "Finance",
    route: "/finance",
    glyph: "₹",
    icon: Wallet,
  },
  {
    id: "projects",
    name: "Projects",
    route: "/projects",
    glyph: "⌁",
    icon: FolderTree,
  },
];

export const MODULES: ModuleDefinition[] = [
  // --- Primary Navigation ---------------------------------------------------
  {
    id: "home",
    name: "Home",
    icon: Compass,
    route: "/",
    category: "command",
    enabled: true,
    glyph: "⌾",
  },
  {
    id: "schedule",
    name: "Schedule",
    icon: CalendarDays,
    route: "/schedule",
    category: "work",
    enabled: true,
    glyph: "▦",
  },
  {
    id: "tasks",
    name: "Tasks",
    icon: ListChecks,
    route: "/tasks",
    category: "work",
    enabled: true,
    glyph: "☷",
  },
  {
    id: "projects",
    name: "Projects",
    icon: FolderTree,
    route: "/projects",
    category: "work",
    enabled: true,
    glyph: "⌁",
  },

  // --- Supporting Sub-modules & Views ----------------------------------------
  {
    id: "goals",
    name: "Goals",
    icon: Target,
    route: "/goals",
    category: "work",
    enabled: true,
  },
  {
    id: "startup",
    name: "Startup",
    icon: Rocket,
    route: "/startup",
    category: "startup",
    enabled: true,
  },
  {
    id: "college",
    name: "College",
    icon: GraduationCap,
    route: "/college",
    category: "life",
    enabled: true,
  },
  {
    id: "internship",
    name: "Internship",
    icon: Briefcase,
    route: "/internship",
    category: "life",
    enabled: true,
  },
  {
    id: "insights",
    name: "Insights",
    icon: Activity,
    route: "/insights",
    category: "insight",
    enabled: true,
  },
  {
    id: "today",
    name: "Today",
    icon: LayoutGrid,
    route: "/today",
    category: "command",
    enabled: true,
  },
];

/** Future life domains — announced, not faked. Registered, never rendered as pages. */
export const PLANNED_MODULES: ModuleDefinition[] = [
  { id: "finance", name: "Finance", icon: CreditCard, category: "planned", enabled: false, brief: "Expenses, budgets, runway." },
  { id: "email", name: "Email", icon: Mail, category: "planned", enabled: false, brief: "Multiple accounts with intelligence." },
  { id: "calendar-integrations", name: "Calendar Sync", icon: CalendarDays, category: "planned", enabled: false, brief: "Google Calendar two-way sync." },
  { id: "drive", name: "Drive", icon: FolderTree, category: "planned", enabled: false, brief: "Personal documents at hand." },
  { id: "habits", name: "Habits & Health", icon: HeartPulse, category: "planned", enabled: false, brief: "Streaks, energy, wellbeing." },
  { id: "agents", name: "AI Agents", icon: BrainCircuit, category: "planned", enabled: false, brief: "Delegated autonomous tasks." },
];

export const ENABLED_MODULES = PRIMARY_NAV_ITEMS;

export function findModule(id: string): ModuleDefinition | undefined {
  return [...MODULES, ...PLANNED_MODULES].find((m) => m.id === id);
}
