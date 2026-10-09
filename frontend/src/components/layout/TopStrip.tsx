import { useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { ChevronRight, LayoutGrid } from "lucide-react";
import { PRIMARY_NAV_ITEMS } from "@/modules/registry";
import { cn } from "@/lib/format";

/** Always on the bottom bar; every other section lives under "More". */
const MOBILE_TABS = new Set(["home", "schedule", "tasks"]);

const tabClass = (active: boolean) =>
  cn(
    "flex flex-col items-center gap-0.5 py-2 text-[11px] transition-colors cursor-pointer",
    active ? "text-ink font-medium" : "text-ink-faint hover:text-ink",
  );

/** Mobile bottom navigation: the main sections, plus a "More" panel for the rest. */
export function MobileBottomNav() {
  const location = useLocation();
  const [moreOpen, setMoreOpen] = useState(false);
  const tabs = PRIMARY_NAV_ITEMS.filter((item) => MOBILE_TABS.has(item.id));
  const more = PRIMARY_NAV_ITEMS.filter((item) => !MOBILE_TABS.has(item.id));
  const onMorePage = more.some((item) => location.pathname.startsWith(item.route));

  // Collapse after navigating anywhere.
  useEffect(() => setMoreOpen(false), [location.pathname, location.search]);

  return (
    <>
      {moreOpen && (
        <div className="fixed inset-0 z-30 bg-black/50 md:hidden" onClick={() => setMoreOpen(false)} aria-hidden />
      )}
      <div
        id="more-sections"
        className={cn(
          "fixed inset-x-0 z-40 border-t border-ops-line-bright bg-ops-panel px-4 pt-3 shadow-[0_-12px_32px_rgba(0,0,0,0.6)] transition-transform duration-200 md:hidden",
          moreOpen ? "translate-y-0" : "pointer-events-none translate-y-[120%]",
        )}
        style={{ bottom: "calc(56px + env(safe-area-inset-bottom))" }}
        aria-hidden={!moreOpen}
      >
        <p className="px-1 pb-1 text-[11px] uppercase tracking-[0.18em] text-ink-faint">More</p>
        <ul className="pb-3">
          {more.map((item) => (
            <li key={item.id}>
              <NavLink
                to={item.route}
                tabIndex={moreOpen ? 0 : -1}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-xl px-2 py-3 text-[15px] transition-colors",
                    isActive ? "bg-ops-raised text-ink font-medium" : "text-ink-dim hover:bg-ops-raised/60 hover:text-ink",
                  )
                }
              >
                <item.icon size={18} strokeWidth={1.75} aria-hidden />
                <span className="flex-1">{item.name}</span>
                <ChevronRight size={16} className="text-ink-faint" />
              </NavLink>
            </li>
          ))}
        </ul>
      </div>

      <nav
        aria-label="Primary Mobile Navigation"
        className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-ops-line bg-ops-ground/95 backdrop-blur md:hidden"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        {tabs.map((item) => (
          <NavLink key={item.id} to={item.route} end={item.route === "/"} className={({ isActive }) => tabClass(isActive)}>
            <item.icon size={18} strokeWidth={1.75} aria-hidden />
            <span>{item.name}</span>
          </NavLink>
        ))}
        <button
          onClick={() => setMoreOpen((o) => !o)}
          aria-expanded={moreOpen}
          aria-controls="more-sections"
          className={tabClass(moreOpen || onMorePage)}
        >
          <LayoutGrid size={18} strokeWidth={1.75} aria-hidden />
          <span>More</span>
        </button>
      </nav>
    </>
  );
}
