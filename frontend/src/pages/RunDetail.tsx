import type { ReactNode } from "react";
import { Link, useParams } from "react-router";
import { isApiError } from "../api/client";
import { useRun } from "../api/queries";
import type { ApplyGroupResult } from "../api/types";
import { StatusBadge } from "../components/Badge";
import { ButtonLink } from "../components/Button";
import { Card } from "../components/Card";
import { cx } from "../components/cx";
import { EmptyState, ErrorNotice, Loading, Notice } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { RunTotals } from "../components/RunTotals";
import {
  formatCount,
  formatDateTime,
  formatDuration,
  labelize,
  parseUtc,
} from "../lib/format";
import { GroupResultList } from "../plans/PlanReview";

const SECTION_TITLES: Record<string, string> = {
  tidal: "Refresh Tidal",
  bandcamp: "Refresh Bandcamp",
  music: "Refresh Music folder",
  download: "Download",
};

export default function RunDetail() {
  const runId = Number(useParams().runId);
  if (!Number.isInteger(runId) || runId <= 0)
    return <EmptyState title="This run does not exist" />;
  return <RunDetailView runId={runId} />;
}

function RunDetailView({ runId }: { runId: number }) {
  const query = useRun(runId);
  if (query.isPending) return <Loading />;
  if (query.isError) {
    return (
      <>
        <BackLink />
        <ErrorNotice
          error={query.error}
          title={
            isApiError(query.error, 404) ? "Run not found" : "Could not load the run"
          }
          onRetry={isApiError(query.error, 404) ? undefined : () => void query.refetch()}
        />
      </>
    );
  }
  const run = query.data;
  const summary = run.summary ?? {};
  const started = parseUtc(run.started_at);
  const finished = run.finished_at ? parseUtc(run.finished_at) : null;
  const backup = typeof summary.backup === "string" ? summary.backup : null;
  const groups = Array.isArray(summary.groups)
    ? (summary.groups as ApplyGroupResult[])
    : [];
  const sections = Object.keys(SECTION_TITLES).filter((key) => isRecord(summary[key]));
  const known = new Set([
    "backup",
    "groups",
    "applied",
    "failed",
    "plan",
    ...Object.keys(SECTION_TITLES),
  ]);
  const other = Object.entries(summary).filter(([key]) => !known.has(key));

  return (
    <>
      <BackLink />
      <PageHeader
        title={`${labelize(run.kind)} #${run.id}`}
        description={<StatusBadge status={run.status} />}
        actions={
          <>
            {run.has_plan && (
              <ButtonLink variant="primary" to={`/plans/${run.id}`}>
                Review the Plan
              </ButtonLink>
            )}
            {run.plan_run_id != null && (
              <ButtonLink to={`/plans/${run.plan_run_id}`}>
                Open the applied Plan
              </ButtonLink>
            )}
          </>
        }
      />
      <div className="space-y-6">
        {run.error && (
          <Notice tone="danger" title="Error">
            {run.error}
          </Notice>
        )}
        <section
          className="rounded-lg border border-line bg-surface p-4"
          aria-label="Run details"
        >
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
            <Item label="Started">{formatDateTime(started)}</Item>
            <Item label="Duration">
              {run.status === "running" ? "running" : formatDuration(started, finished)}
            </Item>
            <Item label="Scope">{run.scope ?? "All playlists"}</Item>
            <Item label="Backup">
              {backup ? (
                <Link to="/backups" className="break-all text-accent hover:underline">
                  {backup}
                </Link>
              ) : (
                "–"
              )}
            </Item>
            {run.kind === "sync" && (
              <div className="sm:col-span-2 lg:col-span-4">
                <dt className="text-xs text-muted">Plan</dt>
                <dd className="mt-1">
                  <RunTotals totals={run.totals} />
                </dd>
              </div>
            )}
          </dl>
        </section>

        {sections.length > 0 && (
          <div className="grid gap-6 lg:grid-cols-2">
            {sections.map((key) => (
              <Card key={key} title={SECTION_TITLES[key]}>
                <Stats data={summary[key] as Record<string, unknown>} />
              </Card>
            ))}
          </div>
        )}

        {run.kind === "apply" && (
          <Card title="Groups">
            {groups.length > 0 ? (
              <>
                <p className="mb-3 text-sm">
                  {formatCount(Number(summary.applied ?? 0))} applied,{" "}
                  {formatCount(Number(summary.failed ?? 0))} failed.
                </p>
                <GroupResultList results={groups} />
              </>
            ) : (
              <p className="text-sm text-muted">No groups were applied.</p>
            )}
          </Card>
        )}

        {other.length > 0 && (
          <Card title="More">
            <Stats data={Object.fromEntries(other)} />
          </Card>
        )}
      </div>
    </>
  );
}

function BackLink() {
  return (
    <Link to="/history" className="mb-3 inline-block text-sm text-accent hover:underline">
      ← History
    </Link>
  );
}

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="break-words">{children}</dd>
    </div>
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Counters and messages from a run summary section. */
function Stats({ data }: { data: Record<string, unknown> }) {
  const numbers = Object.entries(data).filter(
    (entry): entry is [string, number] => typeof entry[1] === "number",
  );
  const texts = Object.entries(data).filter(
    (entry): entry is [string, string] => typeof entry[1] === "string",
  );
  const lists = Object.entries(data).filter(
    (entry): entry is [string, unknown[]] =>
      Array.isArray(entry[1]) && entry[1].length > 0,
  );
  return (
    <div className="space-y-3 text-sm">
      {texts.map(([key, value]) => (
        <p key={key}>
          <span className="text-muted">{labelize(key)}:</span> {value}
        </p>
      ))}
      {numbers.length > 0 && (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
          {numbers.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs text-muted">{labelize(key)}</dt>
              <dd className={cx("tabular font-medium", value === 0 && "text-muted")}>
                {formatCount(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
      {lists.map(([key, items]) => (
        <div key={key}>
          <p className="text-xs text-muted">
            {labelize(key)} ({items.length})
          </p>
          <ul
            className={cx(
              "mt-1 max-h-48 list-disc space-y-0.5 overflow-auto pl-4 text-xs break-words",
              key === "errors" && "text-red-700 dark:text-red-400",
              key === "warnings" && "text-amber-700 dark:text-amber-300",
            )}
          >
            {items.map((item, index) => (
              <li key={index}>
                {typeof item === "string" ? item : JSON.stringify(item)}
              </li>
            ))}
          </ul>
        </div>
      ))}
      {numbers.length === 0 && texts.length === 0 && lists.length === 0 && (
        <p className="text-muted">Nothing to show.</p>
      )}
    </div>
  );
}
