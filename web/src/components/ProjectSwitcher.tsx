import { ChevronDown, FolderPlus } from "lucide-react";
import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Stamp, type StampTone } from "@/components/ui/stamp";
import { type ProjectSummary, useProjects } from "@/lib/api/endpoints/project";

/**
 * Top-of-rail project switcher.
 *
 * Replaces the legacy `<ProjectChip>` click-through-to-picker so users
 * can flit between every discovered project without leaving the
 * current page. Lists every project flat, sorted by friendly name —
 * users find their project by scanning, not by navigating workspace
 * groupings.
 *
 * Each row's right-side badge is the project's lifecycle phase, with
 * a tone keyed off the phase value so a glance tells you which
 * projects are scoping vs executing vs reviewing.
 *
 * Navigation preserves the sub-path: `/p/{currentId}/board` →
 * `/p/{newId}/board` works because React Router's `useParams` is
 * reactive against the URL — naive segment swap is enough.
 */
export interface ProjectSwitcherProps {
  /** Current project id from the route (`useParams().projectId`). */
  projectId: string;
  /** Friendly label for the trigger (typically `project.name`). */
  currentLabel: string;
}

export function ProjectSwitcher({ projectId, currentLabel }: ProjectSwitcherProps) {
  const projects = useProjects();
  const navigate = useNavigate();
  const location = useLocation();

  const sorted = useMemo(
    () => sortProjects(projects.data ?? []),
    [projects.data],
  );

  const onSelect = (newId: string) => {
    if (newId === projectId) return;
    navigate(swapProjectIdInPath(location.pathname, projectId, newId));
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="mx-4 mb-2 flex items-center gap-2 rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2 py-1.5 font-mono text-[11px] text-(--color-ink-2) transition-colors hover:border-(--color-ink-3) data-[state=open]:border-(--color-ink-3)"
        aria-label="Switch project"
      >
        <span className="flex-1 truncate text-left font-semibold text-(--color-ink)">
          {currentLabel}
        </span>
        <ChevronDown className="h-3 w-3 shrink-0 text-(--color-ink-3)" aria-hidden />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56" sideOffset={4}>
        {sorted.length === 0 ? (
          <DropdownMenuItem disabled>No projects discovered</DropdownMenuItem>
        ) : (
          sorted.map((p) => (
            <DropdownMenuItem
              key={p.id}
              onSelect={() => onSelect(p.id)}
              className="flex items-center justify-between gap-3"
              data-active={p.id === projectId ? "true" : undefined}
            >
              <span className="truncate text-(--color-ink)">
                {p.name.replace(/^project-/, "")}
              </span>
              {p.phase ? <Stamp tone={phaseTone(p.phase)}>{p.phase}</Stamp> : null}
            </DropdownMenuItem>
          ))
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/")}>
          <FolderPlus className="mr-2 h-3.5 w-3.5" aria-hidden />
          <span>Open another project…</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * Sort projects by friendly name (with the `project-` prefix stripped).
 *
 * Exported for unit testing.
 */
export function sortProjects(projects: ProjectSummary[]): ProjectSummary[] {
  const friendly = (p: ProjectSummary) => p.name.replace(/^project-/, "");
  return [...projects].sort((a, b) => friendly(a).localeCompare(friendly(b)));
}

/**
 * Map a project's lifecycle phase to a Stamp tone. Each phase gets a
 * distinct colour so a glance across the dropdown tells you which
 * projects are scoping vs executing vs reviewing.
 *
 * Palette rationale:
 *  - scoping  → info (blue)    — exploring, planning
 *  - scoped   → default (ink)  — plan locked, ready to start
 *  - executing → rule (red)    — active work, primary attention
 *  - reviewing → gate (yellow) — held on review/approval
 *
 * Unknown phases fall through to the default ink tone.
 *
 * Exported for unit testing.
 */
export function phaseTone(phase: string): StampTone {
  switch (phase) {
    case "scoping":
      return "info";
    case "scoped":
      return "default";
    case "executing":
      return "rule";
    case "reviewing":
      return "gate";
    default:
      return "default";
  }
}

/**
 * Replace the project-id segment in a path while preserving the rest.
 * `/p/A/board` + (A → B) → `/p/B/board`. If the path doesn't match
 * the expected `/p/{id}` prefix, falls back to `/p/{newId}`.
 *
 * Exported for unit testing.
 */
export function swapProjectIdInPath(
  pathname: string,
  oldId: string,
  newId: string,
): string {
  // Look for an exact `/p/{oldId}` segment so we don't accidentally
  // replace a substring that happens to match.
  const expectedPrefix = `/p/${oldId}`;
  if (pathname === expectedPrefix || pathname.startsWith(`${expectedPrefix}/`)) {
    return `/p/${newId}${pathname.slice(expectedPrefix.length)}`;
  }
  return `/p/${newId}`;
}
