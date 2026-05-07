import { ChevronDown, FolderPlus } from "lucide-react";
import { useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Stamp, type StampTone } from "@/components/ui/stamp";
import { type ProjectSummary, useProjects } from "@/lib/api/endpoints/project";
import {
  type WorkspaceSummary,
  useWorkspaces,
} from "@/lib/api/endpoints/workspace";

const UNWORKSPACED_HEADING = "Unworkspaced";
const NO_WORKSPACE = "__none__";

/**
 * v0.10.0 — top-of-rail project switcher.
 *
 * Replaces the legacy `<ProjectChip>` click-through-to-picker so users
 * can flit between every registered project (and any workspace's
 * member projects) without leaving the current page.
 *
 * Grouping: projects with `workspace_id` set are listed under their
 * workspace's name; the rest fall into the "Unworkspaced" bucket. When
 * `useWorkspaces()` returns an empty list (no `workspace_roots`
 * configured), the dropdown degrades to a single ungrouped list.
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
  const workspaces = useWorkspaces();
  const navigate = useNavigate();
  const location = useLocation();

  const groups = useMemo(
    () => groupProjectsByWorkspace(projects.data ?? [], workspaces.data ?? []),
    [projects.data, workspaces.data],
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
        {groups.length === 0 ? (
          <DropdownMenuItem disabled>No projects discovered</DropdownMenuItem>
        ) : (
          groups.map((group, gi) => (
            <SwitcherGroup
              key={group.workspaceId}
              group={group}
              showHeading={shouldShowHeading(groups)}
              isFirst={gi === 0}
              currentProjectId={projectId}
              onSelect={onSelect}
            />
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

interface ProjectGroup {
  workspaceId: string;
  workspaceName: string;
  projects: ProjectSummary[];
}

function shouldShowHeading(groups: ProjectGroup[]): boolean {
  // No reason to show "Unworkspaced" as a heading when it's the only
  // group — the dropdown is already implicitly "all your projects".
  return groups.length > 1;
}

function SwitcherGroup({
  group,
  showHeading,
  isFirst,
  currentProjectId,
  onSelect,
}: {
  group: ProjectGroup;
  showHeading: boolean;
  isFirst: boolean;
  currentProjectId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <>
      {!isFirst && showHeading ? <DropdownMenuSeparator /> : null}
      {showHeading ? (
        <DropdownMenuLabel className="font-mono text-[10px] uppercase tracking-[0.18em] text-(--color-ink-3)">
          {group.workspaceName}
        </DropdownMenuLabel>
      ) : null}
      {group.projects.map((p) => (
        <DropdownMenuItem
          key={p.id}
          onSelect={() => onSelect(p.id)}
          className="flex items-center justify-between gap-3"
          data-active={p.id === currentProjectId ? "true" : undefined}
        >
          <span className="truncate text-(--color-ink)">
            {p.name.replace(/^project-/, "")}
          </span>
          {p.phase ? <Stamp tone={phaseTone(p.phase)}>{p.phase}</Stamp> : null}
        </DropdownMenuItem>
      ))}
    </>
  );
}

/**
 * Group projects by `workspace_id`, ordered by workspace slug (stable
 * across renders), with the "Unworkspaced" group always last.
 *
 * Exported for unit testing.
 */
export function groupProjectsByWorkspace(
  projects: ProjectSummary[],
  workspaces: WorkspaceSummary[],
): ProjectGroup[] {
  const wsById = new Map(workspaces.map((w) => [w.id, w]));
  const groupsById = new Map<string, ProjectGroup>();

  for (const p of projects) {
    // If workspace_id is set but the workspace isn't in the discovery
    // result (cache races, /api/projects ahead of /api/workspaces, the
    // backend pointer resolved to a directory not registered in
    // workspace_roots), fall through to the Unworkspaced bucket
    // rather than spawning a phantom "Unknown workspace" group.
    const wsId =
      p.workspace_id && wsById.has(p.workspace_id)
        ? p.workspace_id
        : NO_WORKSPACE;
    if (!groupsById.has(wsId)) {
      groupsById.set(wsId, {
        workspaceId: wsId,
        workspaceName:
          wsId === NO_WORKSPACE
            ? UNWORKSPACED_HEADING
            : wsById.get(wsId)!.name,
        projects: [],
      });
    }
    groupsById.get(wsId)!.projects.push(p);
  }

  const ordered = [...groupsById.values()].sort((a, b) => {
    if (a.workspaceId === NO_WORKSPACE) return 1;
    if (b.workspaceId === NO_WORKSPACE) return -1;
    return a.workspaceName.localeCompare(b.workspaceName);
  });

  for (const group of ordered) {
    group.projects.sort((a, b) =>
      a.name.replace(/^project-/, "").localeCompare(b.name.replace(/^project-/, "")),
    );
  }

  return ordered;
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
