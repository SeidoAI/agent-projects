import { useSourceFile } from "@/lib/api/endpoints/source";

export interface SourceViewerProps {
  path: string;
  onClose: () => void;
  onOpenLocally?: () => void;
}

export function SourceViewer({ path, onClose, onOpenLocally }: SourceViewerProps) {
  const { data, isPending, isError, error } = useSourceFile(path);

  return (
    <div
      data-testid="workflow-source-viewer"
      role="dialog"
      aria-label={`Source viewer: ${path}`}
      style={{
        position: "fixed",
        right: 24,
        top: 80,
        bottom: 24,
        width: 720,
        maxWidth: "60vw",
        background: "var(--color-paper)",
        border: "1.5px solid var(--color-ink)",
        boxShadow: "0 18px 50px rgba(26,24,21,0.20)",
        display: "flex",
        flexDirection: "column",
        zIndex: 200,
      }}
    >
      {/* header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          padding: "10px 14px",
          borderBottom: "1px solid var(--color-edge)",
          background: "var(--color-paper-2)",
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 10,
              letterSpacing: "0.18em",
              color: "var(--color-ink-3)",
              textTransform: "uppercase",
            }}
          >
            source
          </div>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              color: "var(--color-ink)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              direction: "rtl",
              textAlign: "left",
            }}
            title={path}
          >
            {path}
          </div>
        </div>
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(path)}
          style={btnStyle}
          title="Copy path to clipboard"
        >
          copy path
        </button>
        {onOpenLocally && (
          <button
            type="button"
            onClick={onOpenLocally}
            style={btnStyle}
            title="Open in default app"
          >
            open locally
          </button>
        )}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close source viewer"
          style={{ ...btnStyle, padding: "4px 10px" }}
        >
          ×
        </button>
      </div>
      {/* body */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: 0,
          background: "var(--color-paper)",
        }}
      >
        {isPending && (
          <div style={statePlaceholder}>loading source…</div>
        )}
        {isError && (
          <div style={statePlaceholder}>
            failed to load source: {(error as Error)?.message ?? "unknown error"}
          </div>
        )}
        {data && (
          <pre
            style={{
              margin: 0,
              padding: 16,
              fontFamily: "var(--font-mono)",
              fontSize: 12,
              lineHeight: 1.5,
              color: "var(--color-ink)",
              whiteSpace: "pre",
              overflow: "auto",
            }}
          >
            {data.content}
          </pre>
        )}
      </div>
    </div>
  );
}

const btnStyle: React.CSSProperties = {
  cursor: "pointer",
  border: "1px solid var(--color-ink)",
  background: "var(--color-paper)",
  padding: "4px 10px",
  fontFamily: "var(--font-mono)",
  fontSize: 10,
  color: "var(--color-ink)",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const statePlaceholder: React.CSSProperties = {
  padding: 24,
  fontFamily: "var(--font-serif)",
  fontStyle: "italic",
  fontSize: 13,
  color: "var(--color-ink-3)",
};
