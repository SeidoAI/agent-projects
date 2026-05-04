import type { WorkflowDefinition } from "@/lib/api/endpoints/workflow";

export interface WorkflowNavigatorProps {
  workflows: WorkflowDefinition[];
  activeId: string | null;
  onPick: (id: string) => void;
}

/** Flat horizontal pill rail of workflow bands.
 *
 *  In unified-canvas mode the navigator is a "jump to band" affordance,
 *  not a switcher — clicking a pill calls onPick which scrolls/zooms the
 *  canvas to the named band. The actor-grouped column layout was dropped:
 *  every workflow in this project involves multiple actors, so grouping
 *  by single-actor was a fiction.
 */
export function WorkflowNavigator({
  workflows,
  activeId,
  onPick,
}: WorkflowNavigatorProps) {
  return (
    <div
      data-testid="workflow-navigator"
      style={{
        display: "flex",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 6,
        padding: "8px 10px",
        marginBottom: 14,
        background: "var(--color-paper-2)",
        border: "1px solid var(--color-edge)",
        borderRadius: 4,
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 9.5,
          letterSpacing: "0.18em",
          color: "var(--color-ink-3)",
          marginRight: 8,
        }}
      >
        WORKFLOWS
      </div>
      {workflows.map((wf) => {
        const active = wf.id === activeId;
        return (
          <button
            key={wf.id}
            type="button"
            data-testid={`workflow-nav-tile-${wf.id}`}
            aria-pressed={active}
            onClick={() => onPick(wf.id)}
            style={{
              cursor: "pointer",
              padding: "6px 12px",
              background: active ? "var(--color-ink)" : "var(--color-paper)",
              color: active ? "var(--color-paper)" : "var(--color-ink)",
              border: `1px solid ${active ? "var(--color-ink)" : "var(--color-edge)"}`,
              fontFamily: "var(--font-sans)",
              fontSize: 12.5,
              fontWeight: 500,
              lineHeight: 1.15,
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              borderRadius: 3,
            }}
          >
            <span>{wf.id}</span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 9.5,
                color: active ? "#d8d2c2" : "var(--color-ink-3)",
                letterSpacing: "0.06em",
              }}
            >
              {wf.statuses.length} st · {wf.routes.length} rt
            </span>
          </button>
        );
      })}
    </div>
  );
}
