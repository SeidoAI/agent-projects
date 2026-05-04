import { ArrowRight, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useNavigationType } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { projectApi, useProjects } from "@/lib/api/endpoints/project";

// Augment Window with the experimental File System Access API surface
// the picker uses. Available in Chromium-family browsers; the call
// site has its own fallback path. Declared inline rather than via a
// global ambient module so this file owns the typing it depends on.
type DirectoryPickerOptions = {
  mode?: "read" | "readwrite";
  id?: string;
  startIn?: string;
};
declare global {
  interface Window {
    showDirectoryPicker?: (options?: DirectoryPickerOptions) => Promise<FileSystemDirectoryHandle>;
  }
}

export function ProjectPicker() {
  const navigate = useNavigate();
  const navType = useNavigationType();
  const { data: projects, isLoading } = useProjects();
  const [finding, setFinding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (navType !== "POP") return;
    if (projects?.length === 1) {
      const first = projects[0];
      if (first) navigate(`/p/${first.id}`, { replace: true });
    }
  }, [projects, navigate, navType]);

  async function openPicker() {
    setError(null);
    if (!window.showDirectoryPicker) {
      setError("This browser doesn't support the folder picker.");
      return;
    }
    let dirHandle: FileSystemDirectoryHandle;
    try {
      dirHandle = await window.showDirectoryPicker({ mode: "read" });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setError("Could not open folder picker.");
      return;
    }

    let content: string;
    try {
      const fileHandle = await dirHandle.getFileHandle("project.yaml");
      const file = await fileHandle.getFile();
      content = await file.text();
    } catch {
      setError("No project.yaml found in the selected folder. Is this a Tripwire project?");
      return;
    }

    const name = content
      .match(/^name:\s*(.+)$/m)?.[1]
      ?.trim()
      .replace(/^['"]|['"]$/g, "");
    const key_prefix = content
      .match(/^key_prefix:\s*(.+)$/m)?.[1]
      ?.trim()
      .replace(/^['"]|['"]$/g, "");

    if (!name || !key_prefix) {
      setError("Could not read name or key_prefix from project.yaml.");
      return;
    }

    setFinding(true);
    try {
      const summary = await projectApi.find(name, key_prefix);
      navigate(`/p/${summary.id}`);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setError(
          `Found "${name}" but it isn't in a discoverable location. ` +
            `Start Tripwire from inside that directory and reload.`,
        );
      } else {
        setError("Something went wrong. Try again.");
      }
    } finally {
      setFinding(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-(--color-paper) px-6">
      <div className="w-full max-w-xl">
        <img src="/img/mark-accent.svg" alt="tripwire" className="mb-8 h-14 w-auto" />

        <h1 className="font-sans font-semibold text-[28px] text-(--color-ink) leading-tight tracking-[-0.02em]">
          Open a project
        </h1>
        <p className="mt-1 font-serif text-[14px] italic text-(--color-ink-2)">
          Select a Tripwire project folder to get started.
        </p>

        {!isLoading && projects && projects.length > 1 && (
          <div className="mt-8 flex flex-col gap-2">
            <div className="font-mono text-[10px] text-(--color-ink-3) uppercase tracking-[0.18em]">
              recent projects
            </div>
            {projects.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => navigate(`/p/${p.id}`)}
                className="flex w-full items-center justify-between rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper-2) px-4 py-3 text-left transition-colors hover:bg-(--color-paper-3)"
              >
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="font-sans font-medium text-[14px] text-(--color-ink)">
                    {p.name.replace(/^project-/, "")}
                  </span>
                  <span className="font-mono text-[10px] text-(--color-ink-3) tracking-[0.04em]">
                    {p.key_prefix} · {p.issue_count} issues · {p.node_count} concepts
                  </span>
                  {p.dir && (
                    <span
                      title={p.dir}
                      className="font-mono text-[10px] text-(--color-ink-3) leading-snug break-all"
                    >
                      {p.dir}
                    </span>
                  )}
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-(--color-ink-3)" aria-hidden />
              </button>
            ))}
          </div>
        )}

        <div className="mt-8">
          <Button
            variant="outline"
            className="w-full gap-2"
            disabled={finding}
            onClick={openPicker}
          >
            <FolderOpen className="h-4 w-4" />
            {finding ? "Opening…" : "Open project folder…"}
          </Button>
        </div>

        {error && (
          <p className="mt-4 font-serif text-[13px] italic text-(--color-rule) leading-snug">
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
