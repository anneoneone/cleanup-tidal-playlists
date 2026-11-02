import { type ReactNode, useEffect, useRef, useState } from "react";
import { useCancelJob } from "../api/queries";
import type { JobOut } from "../api/types";
import { StatusBadge } from "../components/Badge";
import { Button } from "../components/Button";
import { cx } from "../components/cx";
import { ErrorNotice, Notice, Spinner } from "../components/Feedback";
import { CheckIcon, ChevronIcon, MinusIcon, XIcon } from "../components/icons";
import { ProgressBar } from "../components/ProgressBar";
import { formatCount, formatSeconds } from "../lib/format";
import { useNow } from "../lib/useNow";
import { countLevels, isTerminal, type JobStep, type LogLine } from "./jobState";
import { useJobStream } from "./useJobStream";

/**
 * Live view of one job: steps with progress, a log console and Cancel.
 * Mount with `key={jobId}`. `children` renders once the job has ended.
 */
export function JobPanel({
  jobId,
  title,
  children,
}: {
  jobId: string;
  title?: string;
  children?: (job: JobOut) => ReactNode;
}) {
  const { state, job, finalJob } = useJobStream(jobId);
  const cancel = useCancelJob();
  const terminal = isTerminal(state.status);
  const running = !terminal && !state.lost;
  const now = useNow(running);
  const startedMs = job ? job.started_at * 1000 : null;
  const endedMs = job?.finished_at ? job.finished_at * 1000 : null;
  const elapsed = startedMs !== null ? ((endedMs ?? now) - startedMs) / 1000 : null;
  const statusLabel = state.lost
    ? "unknown"
    : state.status === "connecting"
      ? "running"
      : state.status;

  return (
    <div className="space-y-4">
      <section
        className="rounded-lg border border-line bg-surface"
        aria-label={title ?? job?.label ?? "Job"}
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 className="text-sm font-semibold">{title ?? job?.label ?? "Job"}</h2>
            <StatusBadge status={statusLabel} />
            {elapsed !== null && (
              <span className="tabular text-xs text-muted">{formatSeconds(elapsed)}</span>
            )}
          </div>
          {running && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => cancel.mutate(jobId)}
              busy={cancel.isPending}
              disabled={cancel.data?.cancelled === true}
            >
              {cancel.data?.cancelled ? "Cancelling…" : "Cancel"}
            </Button>
          )}
        </div>
        <div className="space-y-4 p-4">
          {state.reconnecting && (
            <p className="flex items-center gap-2 text-xs text-muted" role="status">
              <Spinner className="size-3.5" /> Connection lost. Reconnecting…
            </p>
          )}
          {state.steps.length === 0 && running ? (
            <p className="flex items-center gap-2 text-sm text-muted" role="status">
              <Spinner className="size-4" /> Starting…
            </p>
          ) : (
            <StepList steps={state.steps} />
          )}
          {cancel.error && <ErrorNotice error={cancel.error} title="Could not cancel" />}
          {state.status === "failed" && (
            <Notice tone="danger" title="The job failed">
              {state.message || job?.error || "Unknown error"}
            </Notice>
          )}
          {state.status === "cancelled" && (
            <Notice tone="warning" title="The job was cancelled" />
          )}
          {state.lost && (
            <Notice tone="warning" title="Lost track of the job">
              {state.lost}
            </Notice>
          )}
          <LogConsole logs={state.logs} defaultOpen={state.status === "failed"} />
        </div>
      </section>
      {finalJob && children?.(finalJob)}
    </div>
  );
}

function StepIcon({ status }: { status: JobStep["status"] }) {
  switch (status) {
    case "running":
      return <Spinner className="size-4 text-accent" />;
    case "done":
      return <CheckIcon className="size-4 text-emerald-600 dark:text-emerald-400" />;
    case "failed":
      return <XIcon className="size-4 text-red-600 dark:text-red-400" />;
    case "cancelled":
      return <MinusIcon className="size-4 text-amber-600 dark:text-amber-400" />;
  }
}

const statusText: Record<JobStep["status"], string> = {
  running: "Running",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

function StepList({ steps }: { steps: JobStep[] }) {
  return (
    <ol className="space-y-3" aria-label="Steps">
      {steps.map((step, index) => {
        const counts =
          step.total !== null && step.current !== null
            ? `${formatCount(step.current)} / ${formatCount(step.total)}`
            : step.current !== null
              ? formatCount(step.current)
              : null;
        const duration =
          step.finishedAt !== null
            ? formatSeconds(step.finishedAt - step.startedAt)
            : null;
        return (
          <li key={`${step.name}-${index}`} className="space-y-1.5">
            <div className="flex items-center gap-2 text-sm">
              <StepIcon status={step.status} />
              <span
                className={cx("font-medium", step.status !== "running" && "text-fg/85")}
              >
                {step.name}
              </span>
              <span className="sr-only">{statusText[step.status]}</span>
              <span className="tabular ml-auto text-xs text-muted">
                {counts}
                {counts && duration && " · "}
                {duration}
              </span>
            </div>
            {step.status === "running" && (
              <ProgressBar
                label={`${step.name} progress`}
                current={step.current}
                total={step.total}
              />
            )}
            {step.status === "running" && step.message && (
              <p className="truncate pl-6 text-xs text-muted" title={step.message}>
                {step.message}
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

const levelClass: Record<LogLine["level"], string> = {
  debug: "text-muted",
  info: "text-fg/90",
  warning: "text-amber-700 dark:text-amber-300",
  error: "text-red-700 dark:text-red-400",
};

function formatClock(seconds: number): string {
  const date = new Date(seconds * 1000);
  return date.toLocaleTimeString("en-GB", { hour12: false });
}

function LogConsole({ logs, defaultOpen }: { logs: LogLine[]; defaultOpen: boolean }) {
  const [openChoice, setOpenChoice] = useState<boolean | null>(null);
  const open = openChoice ?? defaultOpen;
  const boxRef = useRef<HTMLDivElement>(null);
  const stickToBottom = useRef(true);
  const { warnings, errors } = countLevels(logs);

  useEffect(() => {
    const box = boxRef.current;
    if (open && box && stickToBottom.current) box.scrollTop = box.scrollHeight;
  }, [logs.length, open]);

  return (
    <div className="rounded-md border border-line">
      <button
        type="button"
        onClick={() => setOpenChoice(!open)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-surface-2"
      >
        <ChevronIcon className={cx("size-4 transition-transform", open && "rotate-90")} />
        <span className="font-medium">Log</span>
        <span className="text-xs text-muted">
          {logs.length === 1 ? "1 line" : `${formatCount(logs.length)} lines`}
        </span>
        {warnings > 0 && (
          <span className="text-xs text-amber-700 dark:text-amber-300">
            {warnings === 1 ? "1 warning" : `${warnings} warnings`}
          </span>
        )}
        {errors > 0 && (
          <span className="text-xs text-red-700 dark:text-red-400">
            {errors === 1 ? "1 error" : `${errors} errors`}
          </span>
        )}
      </button>
      {open && (
        <div
          ref={boxRef}
          role="log"
          aria-label="Job log"
          tabIndex={0}
          onScroll={(event) => {
            const box = event.currentTarget;
            stickToBottom.current =
              box.scrollHeight - box.scrollTop - box.clientHeight < 24;
          }}
          className="max-h-72 overflow-auto border-t border-line bg-surface-2/60 px-3 py-2 font-mono text-xs leading-relaxed"
        >
          {logs.length === 0 ? (
            <p className="text-muted">No log lines yet.</p>
          ) : (
            logs.map((line) => (
              <div
                key={line.seq}
                className={cx("break-words whitespace-pre-wrap", levelClass[line.level])}
              >
                <span className="mr-2 text-muted select-none">
                  {formatClock(line.time)}
                </span>
                {line.level === "warning" || line.level === "error" ? (
                  <span className="mr-1 font-semibold uppercase">{line.level}</span>
                ) : null}
                {line.message}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
