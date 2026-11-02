import { useState } from "react";
import { useNavigate } from "react-router";
import { api, isApiError } from "../api/client";
import type { JobOut } from "../api/types";
import { Button } from "../components/Button";
import { ErrorNotice, Notice } from "../components/Feedback";

/** Shown when starting a job returns 409: offers to open the running job. */
export function JobConflict({ message }: { message: string }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const viewRunningJob = async () => {
    setBusy(true);
    setError(null);
    try {
      const job = await api.get<JobOut | null>("/api/jobs/current");
      if (job && job.status === "running") {
        void navigate(`/sync?job=${encodeURIComponent(job.id)}`);
      } else {
        setError(
          "This server runs no job. Another Cratekeeper process (like the CLI) may be busy, or the job just ended. Try again in a moment.",
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Notice
      tone="warning"
      title="Another job is running"
      actions={
        <Button size="sm" onClick={() => void viewRunningJob()} busy={busy}>
          View running job
        </Button>
      }
    >
      <p>{message}</p>
      {error && <p className="mt-1 font-medium">{error}</p>}
    </Notice>
  );
}

/** Error from starting a job: a 409 offers the running job, others show the message. */
export function StartJobError({ error, title }: { error: unknown; title?: string }) {
  if (isApiError(error, 409)) return <JobConflict message={error.message} />;
  return <ErrorNotice error={error} title={title ?? "Could not start the job"} />;
}
