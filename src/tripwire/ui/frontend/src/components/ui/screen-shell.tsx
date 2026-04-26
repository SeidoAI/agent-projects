import { Settings } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink, useParams } from "react-router-dom";

import { cn } from "@/lib/utils";

/**
 * App chrome per spec §3.1 C0.3 — replaces the legacy
 * `Sidebar.tsx` + `TopBar.tsx` + `ProjectShell.tsx` glue.
 *
 * Layout:
 *   - 208px left rail (paper-2): wordmark, project switcher, nav with
 *     active 2px rule-red left border.
 *   - 56px top bar (paper-2, edge bottom rule): breadcrumbs, spacer,
 *     status cluster (env stamp, agent budget remaining, sync state),
 *     gear icon to open the Tweaks panel.
 *   - Body: paper bg, full remaining viewport, scrollable.
 */
export interface ScreenShellNavItem {
  to: string;
  label: string;
  number: string;
}

const NAV_ITEMS: ScreenShellNavItem[] = [
  { to: "", label: "overview", number: "01" },
  { to: "board", label: "board", number: "02" },
  { to: "workflow", label: "workflow", number: "03" },
  { to: "graph", label: "concepts", number: "04" },
  { to: "sessions", label: "sessions", number: "05" },
  { to: "tripwires", label: "tripwires", number: "06" },
];

export interface ScreenShellProps {
  projectId: string;
  topBarStatus?: ReactNode;
  children: ReactNode;
}

export function ScreenShell({ projectId, topBarStatus, children }: ScreenShellProps) {
  const onTweaksClick = () => {
    window.dispatchEvent(new CustomEvent("tripwire:tweaks-toggle"));
  };

  return (
    <div className="flex h-screen bg-(--color-paper) text-(--color-ink)">
      <SideRail projectId={projectId} />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar status={topBarStatus} onTweaksClick={onTweaksClick} />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}

function SideRail({ projectId }: { projectId: string }) {
  return (
    <aside className="flex w-52 shrink-0 flex-col border-(--color-edge) border-r bg-(--color-paper-2)">
      <div className="px-5 pt-5 pb-4">
        <span className="font-sans text-[20px] font-semibold tracking-tight text-(--color-ink)">
          tri<span className="text-(--color-rule)">p</span>wire
        </span>
      </div>
      <ProjectChip projectId={projectId} />
      <nav className="relative mt-2 flex flex-1 flex-col">
        <span
          className="absolute top-1 bottom-12 left-[1.4rem] w-px bg-(--color-rule) opacity-50"
          aria-hidden
        />
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to || "index"}
            to={item.to}
            end={item.to === ""}
            className={({ isActive }) =>
              cn(
                "relative flex items-center gap-3 px-4 py-2 text-[13px] transition-colors",
                "border-l-2 border-transparent",
                isActive
                  ? "border-(--color-rule) bg-(--color-paper) font-semibold text-(--color-ink)"
                  : "text-(--color-ink-2) hover:text-(--color-ink)",
              )
            }
          >
            {({ isActive }) => (
              <>
                <span
                  aria-hidden
                  className={cn(
                    "block h-2.5 w-2.5 rounded-full border-2 border-(--color-rule)",
                    isActive ? "bg-(--color-rule)" : "bg-(--color-paper-2)",
                  )}
                />
                <span className="flex-1">{item.label}</span>
                <span className="font-mono text-[10px] text-(--color-ink-3)">{item.number}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

function ProjectChip({ projectId }: { projectId: string }) {
  return (
    <div className="mx-4 mb-2 flex items-center gap-2 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2 py-1.5 font-mono text-[11px] text-(--color-ink-2)">
      <span className="font-semibold text-(--color-ink)">{projectId}</span>
    </div>
  );
}

interface TopBarProps {
  status?: ReactNode;
  onTweaksClick: () => void;
}

function TopBar({ status, onTweaksClick }: TopBarProps) {
  const { projectId } = useParams();
  return (
    <header className="flex h-14 shrink-0 items-center gap-4 border-(--color-edge) border-b bg-(--color-paper-2) px-5">
      <Breadcrumbs projectId={projectId ?? ""} />
      <div className="ml-auto flex items-center gap-3 text-(--color-ink-2)">
        {status}
        <button
          type="button"
          onClick={onTweaksClick}
          aria-label="Open Tweaks panel"
          className="inline-flex h-7 w-7 items-center justify-center rounded-(--radius-stamp) text-(--color-ink-3) hover:bg-(--color-paper-3) hover:text-(--color-ink)"
        >
          <Settings className="h-4 w-4" aria-hidden />
        </button>
      </div>
    </header>
  );
}

function Breadcrumbs({ projectId }: { projectId: string }) {
  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center gap-2 font-sans text-[13px] text-(--color-ink-2)"
    >
      <span className="text-(--color-ink-3)">Workspace</span>
      <span aria-hidden className="text-(--color-edge)">
        /
      </span>
      <span className="font-medium text-(--color-ink)">{projectId}</span>
    </nav>
  );
}
