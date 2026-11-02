import { useScanSticks, useSticks } from "../api/queries";
import type { StickOut } from "../api/types";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorNotice, Loading, Notice } from "../components/Feedback";
import { StartJobError } from "../jobs/JobConflict";
import { formatCount, formatDateTime, formatRelative, parseUtc } from "../lib/format";

/** Known USB sticks and a button to scan the plugged-in ones. */
export function SticksCard({ jobRunning }: { jobRunning: boolean }) {
  const sticks = useSticks();
  const scan = useScanSticks();
  const nothingFound =
    scan.data && scan.data.scanned.length === 0 && scan.data.problems.length === 0;

  return (
    <Card
      title="USB sticks"
      actions={
        <Button
          size="sm"
          onClick={() => scan.mutate()}
          busy={scan.isPending}
          disabled={jobRunning}
          title="Read the Rekordbox export on each plugged-in USB stick. Nothing is written to the sticks."
        >
          Scan sticks
        </Button>
      }
    >
      <div className="space-y-3">
        {scan.error && (
          <StartJobError error={scan.error} title="Could not scan the sticks" />
        )}
        {nothingFound && (
          <Notice>No USB stick with a Rekordbox export is plugged in.</Notice>
        )}
        {scan.data?.problems.map((problem) => (
          <Notice key={problem} tone="warning">
            {problem}
          </Notice>
        ))}
        {sticks.isPending && <Loading />}
        {sticks.isError && (
          <ErrorNotice
            error={sticks.error}
            title="Could not load the sticks"
            onRetry={() => void sticks.refetch()}
          />
        )}
        {sticks.data?.length === 0 && (
          <p className="text-sm text-muted">
            No stick scanned yet. Plug in a USB stick with a Rekordbox export, then scan
            it.
          </p>
        )}
        {sticks.data && sticks.data.length > 0 && (
          <ul className="divide-y divide-line">
            {sticks.data.map((stick) => (
              <StickRow key={stick.id} stick={stick} />
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}

function StickRow({ stick }: { stick: StickOut }) {
  const scanned = parseUtc(stick.scanned_at);
  const unknown = stick.tracks_total - stick.tracks_matched;
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2.5 first:pt-0 last:pb-0">
      <span className="w-24 shrink-0 text-sm font-medium break-words">{stick.name}</span>
      {stick.mounted && <Badge tone="green">plugged in</Badge>}
      <span className="min-w-0 flex-1 basis-48 text-sm text-muted">
        {formatCount(stick.tracks_total)} tracks
        {unknown > 0 && `, ${formatCount(unknown)} not in Cratekeeper`} · scanned{" "}
        <span title={formatDateTime(scanned)}>{formatRelative(scanned)}</span>
      </span>
    </li>
  );
}
