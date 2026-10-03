import { MODULES, PLANNED_MODULES } from "@/modules/registry";
import { NavLink } from "react-router-dom";
import { Lamp } from "@/components/ui/Panel";
import { cn } from "@/lib/format";

/**
 * MODULES — the OS bay view. Enabled modules are live links; planned bays are
 * announced honestly: registered, empty, no fake data.
 */
export function ModulesPage() {
  return (
    <div className="space-y-6">
      <header className="max-w-2xl space-y-1">
        <h1 className="text-[30px] font-bold leading-tight tracking-[-0.02em] text-ink">Modules</h1>
        <p className="text-[13px] leading-relaxed text-ink-dim">
          IRIS is built to absorb more of your life over time. Each module plugs into the same
          command center, the same intelligence layer, the same registry.
        </p>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {MODULES.map((mod) => (
          <NavLink
            key={mod.id}
            to={mod.route!}
            end={mod.route === "/"}
            className={({ isActive }) =>
              cn(
                "group flex items-center gap-4 border px-4 py-4 transition-colors",
                isActive
                  ? "border-caution bg-ops-raised"
                  : "border-ops-line bg-ops-panel/50 hover:border-ops-line-bright",
              )
            }
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center border border-ops-line-bright text-ink-dim group-hover:text-ink">
              <mod.icon size={17} strokeWidth={1.5} />
            </span>
            <span>
              <span className="block text-[14px] font-semibold text-ink">
                {mod.name}
              </span>
              <span className="label-caps text-go">Online</span>
            </span>
            <Lamp tone="go" className="ml-auto" />
          </NavLink>
        ))}

        {PLANNED_MODULES.map((mod) => (
          <div key={mod.id} aria-disabled className="flex items-center gap-4 border border-dashed border-ops-line bg-transparent px-4 py-4 opacity-80">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center border border-ops-line text-ink-faint">
              <mod.icon size={17} strokeWidth={1.5} />
            </span>
            <span className="min-w-0">
              <span className="block text-[14px] font-semibold text-ink-dim">
                {mod.name}
              </span>
              <span className="block truncate text-[12px] leading-snug text-ink-faint">{mod.brief}</span>
            </span>
            <span className="ml-auto flex shrink-0 flex-col items-end gap-1.5">
              <Lamp tone="dim" />
              <span className="label-caps text-[9px]">Planned</span>
            </span>
          </div>
        ))}
      </div>

      <p className="tnum max-w-xl border-t border-ops-line pt-4 text-[11px] leading-relaxed text-ink-faint">
        {PLANNED_MODULES.length} bays reserved · future integrations register through src/modules/registry.ts
      </p>
    </div>
  );
}
