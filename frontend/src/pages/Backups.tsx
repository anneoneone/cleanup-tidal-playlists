import { useState } from "react";
import { useBackups, useRestoreBackup } from "../api/queries";
import type { BackupOut, RestoreJobResult } from "../api/types";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfirmPanel } from "../components/ConfirmPanel";
import { EmptyState, ErrorNotice, Loading, Notice } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { StartJobError } from "../jobs/JobConflict";
import { JobPanel } from "../jobs/JobPanel";
import { formatBytes, formatDateTime, formatRelative, parseUtc } from "../lib/format";

export default function Backups() {
  const backups = useBackups();
  const restore = useRestoreBackup();
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const startRestore = (backup: BackupOut) => {
    restore.mutate(backup.id, {
      onSuccess: (job) => {
        setJobId(job.id);
        setConfirmId(null);
      },
    });
  };

  return (
    <>
      <PageHeader
        title="Backups"
        description="Copies of the Cratekeeper database, plus the Rekordbox library when taken before an Apply."
      />
      <div className="space-y-4">
        {jobId && (
          <JobPanel key={jobId} jobId={jobId} title="Restore">
            {(job) =>
              job.status === "succeeded" && job.result ? (
                <Notice tone="success" title="Restore finished">
                  Backup {(job.result as unknown as RestoreJobResult).backup} was
                  restored.
                </Notice>
              ) : null
            }
          </JobPanel>
        )}
        {restore.error && (
          <StartJobError error={restore.error} title="Could not start the restore" />
        )}
        {backups.isPending && <Loading />}
        {backups.isError && (
          <ErrorNotice
            error={backups.error}
            title="Could not load the Backups"
            onRetry={() => void backups.refetch()}
          />
        )}
        {backups.data && backups.data.length === 0 && (
          <EmptyState title="No Backups yet">
            A Backup is taken before every sync and every Apply.
          </EmptyState>
        )}
        {backups.data && backups.data.length > 0 && (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {backups.data.map((backup) => (
              <BackupItem
                key={backup.id}
                backup={backup}
                confirming={confirmId === backup.id}
                busy={restore.isPending && restore.variables === backup.id}
                onRestore={() => {
                  restore.reset();
                  setConfirmId(backup.id);
                }}
                onCancel={() => setConfirmId(null)}
                onConfirm={() => startRestore(backup)}
              />
            ))}
          </ul>
        )}
      </div>
    </>
  );
}

function BackupItem({
  backup,
  confirming,
  busy,
  onRestore,
  onCancel,
  onConfirm,
}: {
  backup: BackupOut;
  confirming: boolean;
  busy: boolean;
  onRestore: () => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const [showFiles, setShowFiles] = useState(false);
  const created = parseUtc(backup.created_at);
  const full = backup.kind === "full";
  return (
    <li className="space-y-3 px-4 py-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div className="min-w-0 flex-1 basis-56">
          <p className="flex flex-wrap items-center gap-2 font-medium">
            <span title={formatDateTime(created)}>{formatDateTime(created)}</span>
            <Badge tone={full ? "accent" : "neutral"}>{full ? "full" : "database"}</Badge>
          </p>
          <p className="text-sm text-muted">
            {backup.label} · {formatRelative(created)}
          </p>
        </div>
        <div className="tabular text-sm text-muted">{formatBytes(backup.size_bytes)}</div>
        <button
          type="button"
          onClick={() => setShowFiles(!showFiles)}
          aria-expanded={showFiles}
          className="text-sm text-accent hover:underline"
        >
          {backup.files.length === 1 ? "1 file" : `${backup.files.length} files`}
        </button>
        <Button size="sm" onClick={onRestore} disabled={confirming}>
          Restore
        </Button>
      </div>
      {showFiles && (
        <ul className="rounded-md bg-surface-2 px-3 py-2 font-mono text-xs break-all">
          {backup.files.map((file) => (
            <li key={file}>{file}</li>
          ))}
          {backup.rekordbox_dir && (
            <li className="mt-1 text-muted">Rekordbox folder: {backup.rekordbox_dir}</li>
          )}
        </ul>
      )}
      {confirming && (
        <ConfirmPanel
          title={`Restore the Backup from ${formatDateTime(created)}?`}
          confirmLabel="Restore now"
          onConfirm={onConfirm}
          onCancel={onCancel}
          busy={busy}
          danger
        >
          <p>A Backup of the current state is taken first, so you can go back.</p>
          <p>
            {full
              ? "This replaces the Cratekeeper database and the Rekordbox library files. Rekordbox must be closed."
              : "This replaces the Cratekeeper database. The Rekordbox library is not changed."}
          </p>
        </ConfirmPanel>
      )}
    </li>
  );
}
