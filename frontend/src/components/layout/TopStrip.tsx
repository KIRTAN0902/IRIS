import { NavLink } from "react-router-dom";
import { PRIMARY_NAV_ITEMS } from "@/modules/registry";
import { cn } from "@/lib/format";

/** Mobile bottom navigation: the same sections as the sidebar. */
export function MobileBottomNav() {
  return (
    <nav
      aria-label="Primary Mobile Navigation"
      className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-4 border-t border-ops-line bg-ops-ground/95 backdrop-blur md:hidden"
      style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {PRIMARY_NAV_ITEMS.map((item) => (
        <NavLink
          key={item.id}
          to={item.route}
          end={item.route === "/"}
          className={({ isActive }) =>
            cn(
              "flex flex-col items-center gap-0.5 py-2 text-[11px] transition-colors",
              isActive ? "text-ink font-medium" : "text-ink-faint hover:text-ink",
            )
          }
        >
          <item.icon size={18} strokeWidth={1.75} aria-hidden />
          <span>{item.name}</span>
        </NavLink>
      ))}
    </nav>
  );
}
