import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { ApiError } from "@/lib/api/client";
import {
  type ArtifactStatus,
  useApproveArtifact,
  useRejectArtifact,
} from "@/lib/api/endpoints/artifacts";

interface ApprovalControlsProps {
  projectId: string;
  sessionId: string;
  name: string;
  status?: ArtifactStatus;
}

export function ApprovalControls({ projectId, sessionId, name, status }: ApprovalControlsProps) {
  const approve = useApproveArtifact(projectId, sessionId, name);
  const reject = useRejectArtifact(projectId, sessionId, name);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectFeedback, setRejectFeedback] = useState("");
  const [rejectError, setRejectError] = useState<string | null>(null);

  const existingApproval = status?.approval ?? null;

  function onApprove() {
    approve.mutate(undefined, {
      onSuccess: () => toast.success("Artifact approved."),
      onError: (err) => toast.error(err instanceof ApiError ? err.message : "Approve failed."),
    });
  }

  function onRejectSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = rejectFeedback.trim();
    if (!trimmed) {
      setRejectError("Feedback is required for a rejection.");
      return;
    }
    reject.mutate(trimmed, {
      onSuccess: () => {
        setRejectOpen(false);
        setRejectFeedback("");
        setRejectError(null);
        toast.success("Artifact rejected.");
      },
      onError: (err) => {
        const msg = err instanceof ApiError ? err.message : "Reject failed.";
        setRejectError(msg);
        toast.error(msg);
      },
    });
  }

  if (existingApproval) {
    const { approved, reviewer, reviewed_at, feedback } = existingApproval;
    return (
      <section
        aria-label="Approval recorded"
        className="rounded-md border bg-muted/30 p-3 text-sm"
        data-approval-state={approved ? "approved" : "rejected"}
      >
        <p className="font-semibold text-foreground">
          {approved ? "Approved" : "Rejected"}{" "}
          <span className="text-muted-foreground">by {reviewer}</span>
        </p>
        <p className="text-xs text-muted-foreground">{new Date(reviewed_at).toLocaleString()}</p>
        {feedback ? <p className="mt-1.5 whitespace-pre-wrap text-sm">{feedback}</p> : null}
        <Button variant="outline" size="sm" className="mt-2" disabled title="Revoke comes in v2.">
          Revoke
        </Button>
      </section>
    );
  }

  return (
    <section
      aria-label="Approval controls"
      className="flex items-center gap-2"
      data-testid="approval-controls"
    >
      <Button variant="default" size="sm" onClick={onApprove} disabled={approve.isPending}>
        {approve.isPending ? (
          <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
        ) : (
          <CheckCircle2 className="mr-1 h-3.5 w-3.5" />
        )}
        Approve
      </Button>

      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogTrigger asChild>
          <Button variant="destructive" size="sm" disabled={reject.isPending}>
            <XCircle className="mr-1 h-3.5 w-3.5" />
            Reject
          </Button>
        </DialogTrigger>
        <DialogContent>
          <form onSubmit={onRejectSubmit}>
            <DialogHeader>
              <DialogTitle>Reject artifact</DialogTitle>
              <DialogDescription>
                Feedback is required so the producing agent knows what to change.
              </DialogDescription>
            </DialogHeader>
            <textarea
              aria-label="Rejection feedback"
              className="mt-4 min-h-32 w-full rounded border bg-background p-2 text-sm"
              value={rejectFeedback}
              onChange={(e) => {
                setRejectFeedback(e.target.value);
                if (rejectError) setRejectError(null);
              }}
              placeholder="What needs to change?"
            />
            {rejectError ? (
              <p className="mt-1 text-xs text-red-500" role="alert">
                {rejectError}
              </p>
            ) : null}
            <DialogFooter className="mt-4 flex gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setRejectOpen(false)}
              >
                Cancel
              </Button>
              <Button type="submit" variant="destructive" size="sm" disabled={reject.isPending}>
                {reject.isPending ? <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" /> : null}
                Send rejection
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
