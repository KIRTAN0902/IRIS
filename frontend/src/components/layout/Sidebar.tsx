import { NavLink } from "react-router-dom";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { PRIMARY_NAV_ITEMS } from "@/modules/registry";
import { cn } from "@/lib/format";
import { useUiStore } from "@/stores";

/**
 * Left navigation rail.
 * Primary Navigation:
 * - Home (⌾)
 * - Schedule (▦)
 * - Tasks (☷)
 * - Projects (⌁)
 */
export function Sidebar() {
  const fold = useUiStore((s) => s.navFold);
  const toggle = useUiStore((s) => s.toggleNavFold);

  return (
    <nav
      aria-label="Primary Navigation"
      className={cn(
        "hidden md:flex flex-col border-r border-ops-line bg-ops-panel",
        "transition-[width] duration-150 ease-out select-none",
        fold ? "w-14" : "w-52",
      )}
    >
      {/* IRIS mark */}
      <NavLink
        to="/"
        className="flex h-14 items-center gap-3 border-b border-ops-line px-4 hover:bg-ops-raised transition-colors"
      >
        <IrisMark />
        {!fold && (
          <span className="font-[family-name:var(--font-display)] text-[14px] font-bold tracking-[0.22em] text-ink">
            IRIS
          </span>
        )}
      </NavLink>

      {/* 4 Primary Navigation Items */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {PRIMARY_NAV_ITEMS.map((item) => (
          <NavLink
            key={item.id}
            to={item.route}
            end={item.route === "/"}
            title={fold ? item.name : undefined}
            className={({ isActive }) =>
              cn(
                "group relative flex items-center gap-3 rounded-lg px-3 py-2",
                "text-[13px] font-medium tracking-wide transition-colors",
                isActive
                  ? "bg-ops-raised text-ink font-semibold border border-ops-line-bright"
                  : "text-ink-dim hover:text-ink hover:bg-ops-raised/60",
                "focus-visible:ring-2 focus-visible:ring-ink-dim outline-none",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  className={cn(
                    "flex h-5 w-5 shrink-0 items-center justify-center font-[family-name:var(--font-telemetry)] text-[14px] transition-colors",
                    isActive ? "text-ink font-bold" : "text-ink-faint group-hover:text-ink-dim",
                  )}
                  aria-hidden
                >
                  {item.glyph}
                </span>
                {!fold && (
                  <span className="font-[family-name:var(--font-body)] text-[13px] tracking-wide">
                    {item.name}
                  </span>
                )}
                {isActive && (
                  <span
                    className="ml-auto h-1.5 w-1.5 rounded-full bg-ink-dim"
                    aria-hidden
                  />
                )}
              </>
            )}
          </NavLink>
        ))}
      </div>

      {/* Fold / Unfold Toggle */}
      <button
        onClick={toggle}
        aria-label={fold ? "Expand navigation" : "Fold navigation"}
        className="flex h-10 items-center justify-center border-t border-ops-line text-ink-faint hover:text-ink hover:bg-ops-raised transition-colors cursor-pointer"
      >
        {fold ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
      </button>
    </nav>
  );
}

/** The IRIS identity mark: clean solid monochrome aperture. */
export function IrisMark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden className="shrink-0">
      <rect x="2" y="2" width="20" height="20" rx="4" stroke="#353c46" strokeWidth="1.2" />
      <circle cx="12" cy="12" r="6" stroke="#f2f4f6" strokeWidth="1.4" />
      <circle cx="12" cy="12" r="2.2" fill="#dbe4ee" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3" stroke="#353c46" strokeWidth="1.2" />
    </svg>
  );
}

/** Mobile top bar — solid clean header. */
export function MobileTopBar({ askTrigger }: { askTrigger: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-40 flex h-12 items-center gap-3 border-b border-ops-line bg-ops-ground px-4 md:hidden">
      <NavLink to="/" className="flex items-center gap-2">
        <IrisMark size={18} />
        <span className="font-[family-name:var(--font-display)] text-[13px] font-bold tracking-[0.22em] text-ink">
          IRIS
        </span>
      </NavLink>
      <div className="ml-auto flex items-center gap-2">
        {askTrigger}
      </div>
    </header>
  );
}


