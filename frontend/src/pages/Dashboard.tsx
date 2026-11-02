import { Link, useNavigate } from "react-router";
import { isRunning, useStartSync, useStatus } from "../api/queries";
import type { Check, RunOut, SyncIn } from "../api/types";
import { StatusBadge } from "../components/Badge";
import { Button, ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { cx } from "../components/cx";
import { ErrorNotice, Loading, Notice } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { RunTotals } from "../components/RunTotals";
import { StartJobError } from "../jobs/JobConflict";
import {
  formatCount,
  formatDateTime,
  formatDuration,
  formatRelative,
  labelize,
  parseUtc,
} from "../lib/format";
import { SticksCard } from "../sticks/SticksCard";

const COUNT_LABELS: Record<string, string> = {
  playlists: "Playlists",
  tracks: "Tracks",
  tidal_tracks: "Tidal tracks",
  tracks_in_rekordbox: "Tracks in Rekordbox",
};

const SYNC_NOW: SyncIn = {
  playlist: null,
  download: true,
  offline: false,
  full: false,
  allow_shrink: false,
};
const PLAN_OFFLINE: SyncIn = {
  playlist: null,
  download: false,
  offline: true,
  full: false,
  allow_shrink: false,
};

export default function Dashboard() {
  const status = useStatus();
  const startSync = useStartSync();
  const navigate = useNavigate();

  const start = (body: SyncIn) =>
    startSync.mutate(body, {
      onSuccess: (job) => void navigate(`/sync?job=${encodeURIComponent(job.id)}`),
    });

  const job = status.data?.current_job;
  const jobRunning = isRunning(job);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Keep your Rekordbox library in line with your Tidal and Bandcamp playlists."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={() => start(PLAN_OFFLINE)}
              busy={startSync.isPending && startSync.variables === PLAN_OFFLINE}
              disabled={startSync.isPending || jobRunning}
              title="Build a new Plan from the database and the folders, without Tidal and downloads"
            >
              Plan again (offline)
            </Button>
            <Button
              variant="primary"
              onClick={() => start(SYNC_NOW)}
              busy={startSync.isPending && startSync.variables === SYNC_NOW}
              disabled={startSync.isPending || jobRunning}
            >
              Sync now
            </Button>
          </>
        }
      />

      <div className="space-y-6">
        {startSync.error && (
          <StartJobError error={startSync.error} title="Could not start the sync" />
        )}

        {status.isPending && <Loading />}
        {status.isError && (
          <ErrorNotice
            error={status.error}
            title="Could not load the status"
            onRetry={() => void status.refetch()}
          />
        )}

        {status.data && (
          <>
            {status.data.v1_import_available && (
              <Notice tone="info" title="Data from Cratekeeper v1 found">
                Run{" "}
                <code className="rounded bg-black/5 px-1 py-0.5 font-mono text-xs dark:bg-white/10">
                  cratekeeper migrate
                </code>{" "}
                in a terminal to import your playlists and tracks.
              </Notice>
            )}

            {jobRunning && (
              <Notice
                tone="info"
                title={`${job.label || "A job"} is running`}
                actions={
                  <ButtonLink size="sm" to={`/sync?job=${encodeURIComponent(job.id)}`}>
                    View progress
                  </ButtonLink>
                }
              >
                {job.step ? `Step: ${job.step}` : "Starting…"}
              </Notice>
            )}

            <section aria-label="Library">
              <dl className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                {Object.entries(status.data.counts).map(([key, value]) => (
                  <div
                    key={key}
                    className="rounded-lg border border-line bg-surface px-4 py-3"
                  >
                    <dt className="text-xs text-muted">
                      {COUNT_LABELS[key] ?? labelize(key)}
                    </dt>
                    <dd className="tabular mt-1 text-2xl font-semibold">
                      {formatCount(value)}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>

            <div className="grid gap-6 lg:grid-cols-2">
              <LastRunCard title="Last sync" run={status.data.last_sync ?? null} />
              <LastRunCard title="Last apply" run={status.data.last_apply ?? null} />
            </div>

            <SticksCard jobRunning={jobRunning} />

            <Card title="Health">
              <ul className="divide-y divide-line">
                {status.data.checks.map((check) => (
                  <CheckRow key={check.key} check={check} />
                ))}
              </ul>
            </Card>

            <p className="text-xs break-all text-muted">
              Cratekeeper {status.data.version} · Home: {status.data.home}
            </p>
          </>
        )}
      </div>
    </>
  );
}

function CheckRow({ check }: { check: Check }) {
  const ok = check.ok ?? null;
  const dot =
    ok === true
      ? "bg-emerald-500"
      : ok === false
        ? "bg-red-500"
        : "bg-zinc-400 dark:bg-zinc-500";
  const state = ok === true ? "OK" : ok === false ? "Problem" : "Info";
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2.5 first:pt-0 last:pb-0">
      <span
        className={cx("size-2.5 shrink-0 translate-y-[-1px] rounded-full", dot)}
        aria-hidden="true"
      />
      <span className="sr-only">{state}:</span>
      <span className="w-40 shrink-0 text-sm font-medium">{check.label}</span>
      <span
        className={cx(
          "min-w-0 flex-1 basis-48 text-sm break-all",
          ok === false ? "text-red-700 dark:text-red-400" : "text-muted",
        )}
      >
        {check.detail}
      </span>
    </li>
  );
}

function LastRunCard({ title, run }: { title: string; run: RunOut | null }) {
  if (!run) {
    return (
      <Card title={title}>
        <p className="text-sm text-muted">Nothing yet.</p>
      </Card>
    );
  }
  const started = parseUtc(run.started_at);
  const finished = run.finished_at ? parseUtc(run.finished_at) : null;
  return (
    <Card
      title={title}
      actions={
        <Link to={`/history/${run.id}`} className="text-sm text-accent hover:underline">
          Open in History
        </Link>
      }
    >
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted">Status</dt>
        <dd>
          <StatusBadge status={run.status} />
        </dd>
        <dt className="text-muted">Started</dt>
        <dd title={formatDateTime(started)}>{formatRelative(started)}</dd>
        <dt className="text-muted">Duration</dt>
        <dd className="tabular">
          {run.status === "running" ? "running" : formatDuration(started, finished)}
        </dd>
        {run.scope && (
          <>
            <dt className="text-muted">Scope</dt>
            <dd className="break-words">{run.scope}</dd>
          </>
        )}
        {run.kind === "sync" && (
          <>
            <dt className="text-muted">Plan</dt>
            <dd>
              <RunTotals totals={run.totals} />
            </dd>
          </>
        )}
        {run.error && (
          <>
            <dt className="text-muted">Error</dt>
            <dd className="break-words text-red-700 dark:text-red-400">{run.error}</dd>
          </>
        )}
      </dl>
      {run.has_plan && (
        <div className="mt-4">
          <ButtonLink size="sm" to={`/plans/${run.id}`}>
            Review the Plan
          </ButtonLink>
        </div>
      )}
    </Card>
  );
}
