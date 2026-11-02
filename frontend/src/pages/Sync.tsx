import { type FormEvent, useId, useState } from "react";
import { Link, Navigate, useSearchParams } from "react-router";
import { isRunning, useCurrentJob, usePlaylists, useStartSync } from "../api/queries";
import type {
  ApplyJobResult,
  JobOut,
  RestoreJobResult,
  SyncJobResult,
} from "../api/types";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { Loading, Notice } from "../components/Feedback";
import { Field, TextInput, Toggle } from "../components/form";
import { PageHeader } from "../components/PageHeader";
import { StartJobError } from "../jobs/JobConflict";
import { JobPanel } from "../jobs/JobPanel";
import { PlanReview } from "../plans/PlanReview";

export default function Sync() {
  const [params, setParams] = useSearchParams();
  const jobId = params.get("job");
  const currentJob = useCurrentJob();

  if (jobId) {
    return (
      <>
        <PageHeader
          title="Sync"
          description="Refresh the Sources, download missing tracks, then review the Plan."
          actions={
            <Button
              onClick={() => setParams({})}
              title="Close this job view and set up a new sync"
            >
              New sync
            </Button>
          }
        />
        <JobPanel key={jobId} jobId={jobId}>
          {(job) => <JobOutcome job={job} />}
        </JobPanel>
      </>
    );
  }

  // Attach to a job that is already running when the page opens.
  if (isRunning(currentJob.data)) {
    return (
      <Navigate replace to={`/sync?job=${encodeURIComponent(currentJob.data.id)}`} />
    );
  }

  return (
    <>
      <PageHeader
        title="Sync"
        description="Refresh the Sources, download missing tracks, then review the Plan."
      />
      {currentJob.isPending ? (
        <Loading />
      ) : (
        <SyncForm onStarted={(job) => setParams({ job: job.id })} />
      )}
    </>
  );
}

function JobOutcome({ job }: { job: JobOut }) {
  if (job.status !== "succeeded" || !job.result) return null;
  if (job.kind === "sync") {
    const result = job.result as unknown as SyncJobResult;
    return (
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 pt-2">
          <h2 className="text-lg font-semibold">Plan review</h2>
          <Link
            to={`/plans/${result.run_id}`}
            className="text-sm text-accent hover:underline"
          >
            Open the Plan on its own page
          </Link>
        </div>
        <PlanReview runId={result.run_id} />
      </div>
    );
  }
  if (job.kind === "apply") {
    const result = job.result as unknown as ApplyJobResult;
    return (
      <Notice tone={result.failed > 0 ? "warning" : "success"} title="Apply finished">
        {result.applied} applied, {result.failed} failed.{" "}
        <Link className="underline" to={`/history/${result.run_id}`}>
          See the details in History
        </Link>
        .
      </Notice>
    );
  }
  if (job.kind === "restore") {
    const result = job.result as unknown as RestoreJobResult;
    return (
      <Notice tone="success" title="Restore finished">
        Backup {result.backup} was restored.
      </Notice>
    );
  }
  return null;
}

function SyncForm({ onStarted }: { onStarted: (job: JobOut) => void }) {
  const [playlist, setPlaylist] = useState("");
  const [download, setDownload] = useState(true);
  const [offline, setOffline] = useState(false);
  const [full, setFull] = useState(false);
  const startSync = useStartSync();
  const playlists = usePlaylists();
  const listId = useId();

  const submit = (event: FormEvent) => {
    event.preventDefault();
    startSync.mutate(
      {
        playlist: playlist.trim() || null,
        download: download && !offline,
        offline,
        full: full && !offline,
        allow_shrink: false,
      },
      { onSuccess: onStarted },
    );
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <Card title="Options">
        <div className="space-y-5">
          <Field
            label="Playlist (optional)"
            hint="Leave empty to sync all playlists. Use the exact Playlist name."
          >
            {(props) => (
              <TextInput
                {...props}
                list={listId}
                value={playlist}
                onChange={(event) => setPlaylist(event.target.value)}
                placeholder="All playlists"
                autoComplete="off"
              />
            )}
          </Field>
          <datalist id={listId}>
            {playlists.data?.map((p) => (
              <option key={p.id} value={p.name} />
            ))}
          </datalist>
          <Toggle
            label="Download missing tracks"
            hint="Fetch Tidal tracks that have no audio file yet into the Music folder."
            checked={download && !offline}
            disabled={offline}
            onChange={setDownload}
          />
          <Toggle
            label="Offline: skip Tidal and downloads"
            hint="Only read the Bandcamp folder and the Music folder, then build a Plan."
            checked={offline}
            onChange={setOffline}
          />
          <Toggle
            label="Fetch all Tidal playlists again"
            hint="Slower. Reads every Tidal playlist, also the ones that look unchanged."
            checked={full && !offline}
            disabled={offline}
            onChange={setFull}
          />
        </div>
      </Card>
      {startSync.error && (
        <StartJobError error={startSync.error} title="Could not start the sync" />
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" busy={startSync.isPending}>
          Start sync
        </Button>
        <p className="text-xs text-muted">
          A sync never writes to Rekordbox. You review and apply the Plan afterwards.
        </p>
      </div>
    </form>
  );
}
