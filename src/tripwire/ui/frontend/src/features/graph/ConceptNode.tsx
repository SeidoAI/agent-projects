import { Handle, type NodeProps, Position } from "@xyflow/react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface ConceptNodeData extends Record<string, unknown> {
  label?: string;
  node_type?: string;
  ref_count?: number;
  is_stale?: boolean;
}

const TYPE_STYLES: Record<string, string> = {
  decision: "border-violet-500/50 bg-violet-500/10",
  contract: "border-cyan-500/50 bg-cyan-500/10",
  pattern: "border-emerald-500/50 bg-emerald-500/10",
  issue: "border-blue-500/50 bg-blue-500/10",
};

export function ConceptNode({ id, data, selected }: NodeProps) {
  const d = data as ConceptNodeData;
  const nodeType = d.node_type ?? "node";
  const style = TYPE_STYLES[nodeType] ?? "border-muted-foreground/40 bg-muted";
  const refCount = d.ref_count ?? 0;
  const label = d.label ?? id;

  return (
    <div
      className={cn(
        "min-w-[10rem] max-w-[14rem] rounded-md border bg-card px-3 py-2 text-card-foreground shadow-sm",
        style,
        d.is_stale && "ring-2 ring-destructive/60",
        selected && "ring-2 ring-primary",
      )}
      data-testid={`concept-node-${id}`}
    >
      {/* Handles are required for React Flow to route edges even when
          we don't surface them visually. */}
      <Handle
        type="target"
        position={Position.Top}
        className="!h-1.5 !w-1.5 !bg-muted-foreground"
      />
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-xs text-foreground">{id}</span>
        {refCount > 0 && (
          <Badge variant="outline" className="text-[10px]" title={`${refCount} references`}>
            {refCount}
          </Badge>
        )}
      </div>
      <div className="mt-1 truncate text-xs text-muted-foreground" title={label}>
        {label}
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
        {nodeType}
      </div>
      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-1.5 !w-1.5 !bg-muted-foreground"
      />
    </div>
  );
}
