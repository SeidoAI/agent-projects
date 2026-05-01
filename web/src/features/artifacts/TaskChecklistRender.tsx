import type { TaskProgress } from "@/lib/api/endpoints/sessions";
import { TaskProgressBar } from "../sessions/TaskProgressBar";

interface TaskChecklistRenderProps {
  body: string;
}

const TABLE_ROW = /^\s*\|\s*(?<cols>.*?)\s*\|?\s*$/;
const BULLET_ROW = /^\s*[-*]\s*\[(?<mark>[ xX])\]\s+/;

export interface ParsedChecklist extends TaskProgress {
  rows: Array<{ label: string; status: string }>;
}

export function parseChecklist(body: string): ParsedChecklist {
  const lines = body.split(/\r?\n/);
  const rows: Array<{ label: string; status: string }> = [];

  // Try table form first
  const tableRows: string[][] = [];
  for (const line of lines) {
    const m = line.match(TABLE_ROW);
    if (!m) continue;
    const cols = (m.groups?.cols ?? "").split("|").map((c) => c.trim());
    if (cols.every((c) => !c || /^[-:]+$/.test(c))) continue;
    tableRows.push(cols);
  }

  let done = 0;
  let total = 0;
  const headerRow = tableRows[0];
  if (tableRows.length >= 2 && headerRow) {
    const header = headerRow.map((c) => c.toLowerCase());
    let statusIdx = header.findIndex((h) => h === "status" || h === "state");
    if (statusIdx < 0) statusIdx = header.length - 1;
    const labelIdx = header.findIndex((h) => h === "task" || h === "name" || h === "title");
    for (const row of tableRows.slice(1)) {
      const cell = (row[statusIdx] ?? "").trim().toLowerCase();
      if (!cell) continue;
      const labelCol = labelIdx >= 0 ? labelIdx : Math.max(0, statusIdx - 1);
      const label = row[labelCol] ?? row[0] ?? "";
      rows.push({ label, status: cell });
      total += 1;
      if (cell === "done") done += 1;
    }
  }

  if (rows.length === 0) {
    // Bullet fallback
    for (const line of lines) {
      const m = line.match(BULLET_ROW);
      if (!m) continue;
      const isDone = (m.groups?.mark ?? "").toLowerCase() === "x";
      const label = line.replace(BULLET_ROW, "").trim();
      rows.push({ label, status: isDone ? "done" : "todo" });
      total += 1;
      if (isDone) done += 1;
    }
  }

  return { done, total, rows };
}

export function TaskChecklistRender({ body }: TaskChecklistRenderProps) {
  const parsed = parseChecklist(body);
  return (
    <section
      aria-label="Task checklist progress"
      className="rounded-md border bg-muted/30 p-3"
      data-testid="task-checklist-progress"
    >
      <TaskProgressBar progress={{ done: parsed.done, total: parsed.total }} />
    </section>
  );
}
