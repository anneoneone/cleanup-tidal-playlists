import { Link, useNavigate } from "react-router";
import { useRuns } from "../api/queries";
import type { RunOut } from "../api/types";
import { StatusBadge } from "../components/Badge";
import { EmptyState, ErrorNotice, Loading } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import { RunTotals } from "../components/RunTotals";
import {
  formatDateTime,
  formatDuration,
  formatRelative,
  labelize,
  parseUtc,
} from "../lib/format";

export default function History() {
  const runs = useRuns();
  const navigate = useNavigate();
  return (
    <>
      <PageHeader title="History" description="Every sync, apply and restore." />
      {runs.isPending && <Loading />}
      {runs.isError && (
        <ErrorNotice
          error={runs.error}
          title="Could not load the history"
          onRetry={() => void runs.refetch()}
        />
      )}
      {runs.data && runs.data.length === 0 && (
        <EmptyState title="No runs yet">Start a sync to see it here.</EmptyState>
      )}
      {runs.data && runs.data.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[52rem] text-sm">
            <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Run
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Status
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Scope
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Started
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Duration
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Plan
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Error
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {runs.data.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  onOpen={() => void navigate(`/history/${run.id}`)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function RunRow({ run, onOpen }: { run: RunOut; onOpen: () => void }) {
  const started = parseUtc(run.started_at);
  const finished = run.finished_at ? parseUtc(run.finished_at) : null;
  return (
    <tr onClick={onOpen} className="cursor-pointer align-top hover:bg-surface-2/70">
      <td className="px-3 py-2.5 whitespace-nowrap">
        <Link
          to={`/history/${run.id}`}
          onClick={(event) => event.stopPropagation()}
          className="font-medium hover:underline"
        >
          {labelize(run.kind)} <span className="text-muted">#{run.id}</span>
        </Link>
      </td>
      <td className="px-3 py-2.5">
        <StatusBadge status={run.status} />
      </td>
      <td className="max-w-48 px-3 py-2.5 break-words text-muted">
        {run.scope ?? "All"}
      </td>
      <td className="px-3 py-2.5 whitespace-nowrap" title={formatDateTime(started)}>
        {formatRelative(started)}
      </td>
      <td className="tabular px-3 py-2.5 whitespace-nowrap">
        {run.status === "running" ? "running" : formatDuration(started, finished)}
      </td>
      <td className="px-3 py-2.5">
        {run.kind === "sync" ? (
          <RunTotals totals={run.totals} />
        ) : (
          <span className="text-muted">–</span>
        )}
      </td>
      <td className="max-w-64 px-3 py-2.5 text-xs break-words text-red-700 dark:text-red-400">
        {run.error}
      </td>
    </tr>
  );
}
