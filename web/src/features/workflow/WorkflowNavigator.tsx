import type { WorkflowDefinition } from "@/lib/api/endpoints/workflow";
import { ACTOR_COLOR, ACTOR_HEADING, ACTOR_ORDER, isKnownActor } from "./tokens";

export interface WorkflowNavigatorProps {
  workflows: WorkflowDefinition[];
  activeId: string;
  onPick: (id: string) => void;
}

export function WorkflowNavigator({
  workflows,
  activeId,
  onPick,
}: WorkflowNavigatorProps) {
  const groups = groupByActor(workflows);
  const presentActors = ACTOR_ORDER.filter((a) => (groups.get(a)?.length ?? 0) > 0);
  // Surface unknown actors at the end so we don't silently drop a workflow.
  const extras = Array.from(groups.keys()).filter((k) => !isKnownActor(k));

  return (
    <div
      data-testid="workflow-navigator"
      style={{
        display: "flex",
        alignItems: "stretch",
        marginBottom: 14,
        background: "var(--color-paper-2)",
        border: "1px solid var(--color-edge)",
        borderRadius: 4,
      }}
    >
      {[...presentActors, ...extras].map((actor, i) => {
        const list = groups.get(actor) ?? [];
        const heading = isKnownActor(actor) ? ACTOR_HEADING[actor] : actor.toUpperCase();
        const accent = isKnownActor(actor) ? ACTOR_COLOR[actor] : "var(--color-ink)";
        return (
          <div
            key={actor}
            style={{
              flex: "1 1 0",
              borderLeft: i > 0 ? "1px dashed var(--color-edge)" : "none",
            }}
          >
            <div
              style={{
                padding: "8px 14px 0",
                fontFamily: "var(--font-mono)",
                fontSize: 9.5,
                letterSpacing: "0.18em",
                color: "var(--color-ink-3)",
              }}
            >
              ACTOR · {heading}
            </div>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                padding: "6px 6px 8px",
              }}
            >
              {list.map((wf) => {
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
                      textAlign: "left",
                      padding: "8px 10px",
                      margin: 0,
                      marginRight: 6,
                      marginBottom: 4,
                      background: active ? "var(--color-ink)" : "var(--color-paper)",
                      color: active ? "var(--color-paper)" : "var(--color-ink)",
                      border: `1px solid ${active ? "var(--color-ink)" : "var(--color-edge)"}`,
                      fontFamily: "var(--font-sans)",
                      fontSize: 12.5,
                      fontWeight: 500,
                      lineHeight: 1.15,
                      minWidth: 160,
                      display: "flex",
                      flexDirection: "column",
                      gap: 2,
                    }}
                  >
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}
                    >
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background: accent,
                        }}
                      />
                      {wf.id}
                    </span>
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
          </div>
        );
      })}
    </div>
  );
}

function groupByActor(workflows: WorkflowDefinition[]): Map<string, WorkflowDefinition[]> {
  const groups = new Map<string, WorkflowDefinition[]>();
  workflows.forEach((wf) => {
    const list = groups.get(wf.actor) ?? [];
    list.push(wf);
    groups.set(wf.actor, list);
  });
  return groups;
}
