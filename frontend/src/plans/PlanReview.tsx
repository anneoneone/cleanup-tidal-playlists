import { type RefObject, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { isApiError } from "../api/client";
import { useApplyPlan, useJob, usePlan, useRun, useStatus } from "../api/queries";
import type { ApplyGroupResult, ApplyJobResult, PlanGroup, PlanOut } from "../api/types";
import { StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { ConfirmPanel } from "../components/ConfirmPanel";
import { cx } from "../components/cx";
import { EmptyState, ErrorNotice, Loading, Notice } from "../components/Feedback";
import { AlertIcon, ChevronIcon } from "../components/icons";
import { StartJobError } from "../jobs/JobConflict";
import { JobPanel } from "../jobs/JobPanel";
import {
  folderPath,
  formatDateTime,
  formatRelative,
  parseUtc,
  plural,
} from "../lib/format";
import { KindBadge, KindCountBadge } from "./changeKinds";
import {
  allSelected,
  changesOf,
  countByKind,
  DELETE_GROUP_KEY,
  groupsWithChanges,
  initialSelection,
  isDangerous,
  planTotals,
  type Selection,
  selectAll,
  selectedCount,
  selectedKeys,
  selectNone,
  toggleGroup,
} from "./selection";

/** Review a Plan, choose groups and apply them. Used on /plans/:runId and on /sync. */
export function PlanReview({ runId }: { runId: number }) {
  const plan = usePlan(runId);
  if (plan.isPending) return <Loading label="Loading the Plan…" />;
  if (plan.isError) {
    return (
      <ErrorNotice
        error={plan.error}
        title={
          isApiError(plan.error, 404) ? "No Plan for this run" : "Could not load the Plan"
        }
        onRetry={isApiError(plan.error, 404) ? undefined : () => void plan.refetch()}
      />
    );
  }
  return <PlanReviewBody key={runId} data={plan.data} />;
}

function PlanReviewBody({ data }: { data: PlanOut }) {
  const { plan, run_id: runId } = data;
  const groups = useMemo(() => groupsWithChanges(plan), [plan]);
  const [selection, setSelection] = useState<Selection>(() => initialSelection(groups));
  const [confirming, setConfirming] = useState(false);
  const [applyJobId, setApplyJobId] = useState<string | null>(null);
  const apply = useApplyPlan(runId);
  const applyJob = useJob(applyJobId);
  const applying = applyJobId !== null && applyJob.data?.status === "running";
  const appliedBy = data.applied_by_run ?? null;
  const supersededBy = data.superseded_by ?? null;
  const closed = appliedBy !== null || supersededBy !== null;
  const count = selectedCount(groups, selection);
  const deleteGroup = groups.find(isDangerous);
  const deleteSelected = deleteGroup !== undefined && selection.has(DELETE_GROUP_KEY);
  const locked = closed || confirming || applying || apply.isPending;
  const createdAt = parseUtc(plan.created_at);
  const jobRef = useRef<HTMLDivElement>(null);
  const applyButtonRef = useRef<HTMLButtonElement>(null);

  // The Apply progress shows below the groups: bring it into view when it starts.
  useEffect(() => {
    if (!applyJobId) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    jobRef.current?.scrollIntoView?.({
      behavior: reduce ? "auto" : "smooth",
      block: "start",
    });
  }, [applyJobId]);

  const startApply = () => {
    apply.mutate(selectedKeys(groups, selection), {
      onSuccess: (job) => {
        setApplyJobId(job.id);
        setConfirming(false);
      },
    });
  };

  return (
    <div className="space-y-4">
      <PlanSummary data={data} groups={groups} />

      {plan.warnings.length > 0 && (
        <Notice tone="warning" title={plural(plan.warnings.length, "warning")}>
          <ul className="list-disc space-y-1 pl-4">
            {plan.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </Notice>
      )}

      {appliedBy !== null && (
        <Notice tone="success" title="This Plan was applied">
          It was applied in{" "}
          <Link className="underline" to={`/history/${appliedBy}`}>
            run {appliedBy}
          </Link>
          . Run a new sync to plan further changes.
        </Notice>
      )}

      {appliedBy === null && supersededBy !== null && (
        <Notice tone="warning" title="A newer Plan exists">
          <Link className="underline" to={`/plans/${supersededBy}`}>
            Run {supersededBy}
          </Link>{" "}
          made a newer Plan from newer data. This one can no longer be applied.
        </Notice>
      )}

      {groups.length === 0 ? (
        <EmptyState title="Rekordbox is up to date">
          The Plan has no changes.{" "}
          {plan.unchanged_playlists > 0 &&
            `${plural(plan.unchanged_playlists, "playlist")} already match.`}
        </EmptyState>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-base font-semibold">
              {plural(groups.length, "group")} with changes
            </h2>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="ghost"
                disabled={locked || allSelected(groups, selection)}
                onClick={() => setSelection(selectAll(groups, selection))}
              >
                Select all
              </Button>
              <Button
                size="sm"
                variant="ghost"
                disabled={locked || count === 0}
                onClick={() => setSelection(selectNone())}
              >
                Select none
              </Button>
            </div>
          </div>
          {deleteGroup && (
            <p className="text-xs text-muted">
              Playlist deletions are never selected by default. Check them by hand if you
              want them.
            </p>
          )}
          <ul className="space-y-3">
            {groups.map((group) => (
              <PlanGroupCard
                key={group.key}
                group={group}
                selected={selection.has(group.key)}
                disabled={locked}
                onToggle={() =>
                  setSelection((current) => toggleGroup(current, group.key))
                }
              />
            ))}
          </ul>

          {!applying && (
            <div className="sticky bottom-0 z-10 -mx-4 space-y-3 border-t border-line bg-bg/95 px-4 py-3 backdrop-blur sm:mx-0 sm:rounded-lg sm:border">
              {confirming && !closed ? (
                <ApplyConfirm
                  count={count}
                  deleteCount={
                    deleteSelected && deleteGroup ? changesOf(deleteGroup).length : 0
                  }
                  busy={apply.isPending}
                  onConfirm={startApply}
                  onCancel={() => setConfirming(false)}
                  returnFocusRef={applyButtonRef}
                />
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-sm text-muted">
                    {appliedBy !== null
                      ? `Already applied in run ${appliedBy}`
                      : supersededBy !== null
                        ? `Replaced by the Plan of run ${supersededBy}`
                        : `${count} of ${groups.length} selected · Plan from ${formatRelative(createdAt)}`}
                  </p>
                  <Button
                    ref={applyButtonRef}
                    variant="primary"
                    disabled={count === 0 || closed}
                    onClick={() => setConfirming(true)}
                  >
                    Apply {plural(count, "group")}
                  </Button>
                </div>
              )}
              {apply.error && (
                <StartJobError error={apply.error} title="Could not start Apply" />
              )}
            </div>
          )}
        </>
      )}

      {applyJobId && (
        <div ref={jobRef} className="scroll-mt-20">
          <JobPanel key={applyJobId} jobId={applyJobId} title="Apply">
            {(job) => {
              const result = job.result as ApplyJobResult | null | undefined;
              return result?.run_id ? <ApplyResults applyRunId={result.run_id} /> : null;
            }}
          </JobPanel>
        </div>
      )}
    </div>
  );
}

function PlanSummary({ data, groups }: { data: PlanOut; groups: PlanGroup[] }) {
  const { plan } = data;
  const createdAt = parseUtc(plan.created_at);
  const totals = planTotals(groups);
  const newFolders = plan.new_folders;
  return (
    <section
      className="rounded-lg border border-line bg-surface p-4"
      aria-label="Plan summary"
    >
      <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-xs text-muted">Planned</dt>
          <dd title={formatDateTime(createdAt)}>
            {formatDateTime(createdAt)}{" "}
            <span className="text-muted">({formatRelative(createdAt)})</span>
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Scope</dt>
          <dd className="break-words">
            {plan.scope ? `Playlist "${plan.scope}"` : "All playlists"}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Playlists with changes</dt>
          <dd className="tabular">{groups.length}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">Unchanged playlists</dt>
          <dd className="tabular">{plan.unchanged_playlists}</dd>
        </div>
      </dl>
      {totals.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-1.5" aria-label="Changes by kind">
          {totals.map(([kind, n]) => (
            <KindCountBadge key={kind} kind={kind} count={n} />
          ))}
        </div>
      )}
      {newFolders.length > 0 && (
        <div className="mt-4 text-sm">
          <p className="text-xs text-muted">New Rekordbox folders</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {newFolders.map((folder) => (
              <li
                key={folder}
                className="rounded border border-line bg-surface-2 px-2 py-0.5 text-xs"
              >
                {folder}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="mt-4 truncate text-xs text-muted" title={plan.rekordbox_db}>
        Rekordbox library: {plan.rekordbox_db}
      </p>
    </section>
  );
}

function PlanGroupCard({
  group,
  selected,
  disabled,
  onToggle,
}: {
  group: PlanGroup;
  selected: boolean;
  disabled: boolean;
  onToggle: () => void;
}) {
  const id = useId();
  const [expanded, setExpanded] = useState(false);
  const changes = changesOf(group);
  const danger = isDangerous(group);
  const hasTarget = group.target_name || group.folder.length > 0;

  return (
    <li
      className={cx(
        "rounded-lg border bg-surface",
        danger
          ? "border-2 border-red-500/70 bg-red-50/50 dark:bg-red-950/20"
          : "border-line",
        selected && !danger && "border-accent/50 ring-1 ring-accent/30",
      )}
    >
      <div className="flex gap-3 p-4">
        <input
          id={id}
          type="checkbox"
          checked={selected}
          disabled={disabled}
          onChange={onToggle}
          aria-describedby={danger ? `${id}-danger` : undefined}
          className={cx(
            "mt-1 size-4 shrink-0 cursor-pointer disabled:cursor-not-allowed",
            danger ? "accent-red-600" : "accent-accent",
          )}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <label htmlFor={id} className="cursor-pointer font-medium break-words">
              {group.title}
            </label>
            <div className="flex flex-wrap gap-1.5">
              {countByKind(changes).map(([kind, n]) => (
                <KindCountBadge key={kind} kind={kind} count={n} />
              ))}
            </div>
          </div>
          {danger && (
            <p
              id={`${id}-danger`}
              className="mt-1 flex items-center gap-1.5 text-sm font-medium text-red-700 dark:text-red-400"
            >
              <AlertIcon className="size-4" /> Deletes playlists in Rekordbox
            </p>
          )}
          {hasTarget && (
            <p className="mt-1 text-xs break-words text-muted">
              {folderPath(group.folder)}
              {group.target_name && (
                <>
                  {" / "}
                  <span className="font-medium text-fg">{group.target_name}</span>
                </>
              )}
            </p>
          )}
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            aria-expanded={expanded}
            aria-controls={`${id}-changes`}
            className="mt-2 inline-flex items-center gap-1 rounded text-xs font-medium text-accent hover:underline"
          >
            <ChevronIcon
              className={cx("size-3.5 transition-transform", expanded && "rotate-90")}
            />
            {expanded ? "Hide" : "Show"} {plural(changes.length, "change")}
          </button>
          {expanded && (
            <ul
              id={`${id}-changes`}
              className="mt-2 space-y-1.5 border-t border-line pt-2 text-sm"
            >
              {changes.map((change, index) => (
                <li key={index} className="flex items-start gap-2">
                  <KindBadge kind={change.kind} />
                  <span className="min-w-0 break-words">{change.summary}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </li>
  );
}

function ApplyConfirm({
  count,
  deleteCount,
  busy,
  onConfirm,
  onCancel,
  returnFocusRef,
}: {
  count: number;
  deleteCount: number;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
}) {
  const status = useStatus();
  const rekordboxRunning = status.data?.rekordbox_running ?? false;
  return (
    <ConfirmPanel
      title={`Apply ${plural(count, "group")} to Rekordbox?`}
      confirmLabel="Apply now"
      onConfirm={onConfirm}
      onCancel={onCancel}
      returnFocusRef={returnFocusRef}
      busy={busy}
      danger={deleteCount > 0}
    >
      <p>
        A Backup of the Rekordbox library and the Cratekeeper database is taken first.
        Rekordbox must be closed while Cratekeeper writes to its library.
      </p>
      {rekordboxRunning && (
        <p className="font-medium text-amber-700 dark:text-amber-300">
          Rekordbox is running right now. Close it before you continue.
        </p>
      )}
      {deleteCount > 0 && (
        <p className="font-medium text-red-700 dark:text-red-400">
          This also deletes {plural(deleteCount, "playlist")} in Rekordbox.
        </p>
      )}
    </ConfirmPanel>
  );
}

function asGroupResults(value: unknown): ApplyGroupResult[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (item): item is ApplyGroupResult =>
      typeof item === "object" && item !== null && "key" in item && "status" in item,
  );
}

/** Per-group results of an apply run. */
export function ApplyResults({ applyRunId }: { applyRunId: number }) {
  const run = useRun(applyRunId);
  if (run.isPending) return <Loading label="Loading the results…" />;
  if (run.isError)
    return (
      <ErrorNotice
        error={run.error}
        title="Could not load the results"
        onRetry={() => void run.refetch()}
      />
    );
  const summary = run.data.summary ?? {};
  const results = asGroupResults(summary.groups);
  const failed = results.filter((r) => r.status === "failed").length;
  const applied = results.length - failed;
  const backup = typeof summary.backup === "string" ? summary.backup : null;
  return (
    <section
      className="rounded-lg border border-line bg-surface"
      aria-label="Apply results"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-4 py-3">
        <h2 className="text-sm font-semibold">Apply results</h2>
        <Link
          to={`/history/${applyRunId}`}
          className="text-sm text-accent hover:underline"
        >
          View in History
        </Link>
      </div>
      <div className="space-y-3 p-4">
        <p className="text-sm">
          {plural(applied, "group")} applied
          {failed > 0 && (
            <span className="font-medium text-red-700 dark:text-red-400">
              , {failed} failed
            </span>
          )}
          .
          {backup && (
            <span className="text-muted"> Backup {backup} was taken first.</span>
          )}
        </p>
        {run.data.error && failed === 0 && (
          <Notice tone="danger">{run.data.error}</Notice>
        )}
        <GroupResultList results={results} />
      </div>
    </section>
  );
}

export function GroupResultList({ results }: { results: ApplyGroupResult[] }) {
  if (results.length === 0) return null;
  return (
    <ul className="divide-y divide-line rounded-md border border-line">
      {results.map((result) => (
        <li
          key={result.key}
          className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2 text-sm"
        >
          <StatusBadge status={result.status} />
          <span className="min-w-0 flex-1 break-words">{result.title}</span>
          {result.error && (
            <p className="w-full text-xs text-red-700 dark:text-red-400">
              {result.error}
            </p>
          )}
          {result.warning && (
            <p className="w-full text-xs text-amber-700 dark:text-amber-300">
              {result.warning}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}
