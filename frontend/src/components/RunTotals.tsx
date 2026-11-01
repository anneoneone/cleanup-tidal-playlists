import type { ChangeKind } from "../api/types";
import { KindCountBadge } from "../plans/changeKinds";
import { CHANGE_KIND_ORDER } from "../plans/selection";

/** Change counts of a sync run's Plan as badges ("No changes" when empty). */
export function RunTotals({
  totals,
}: {
  totals: Record<string, number> | null | undefined;
}) {
  if (!totals) return <span className="text-muted">–</span>;
  const entries = CHANGE_KIND_ORDER.filter((kind) => (totals[kind] ?? 0) > 0).map(
    (kind): [ChangeKind, number] => [kind, totals[kind] ?? 0],
  );
  if (entries.length === 0) return <span className="text-xs text-muted">No changes</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {entries.map(([kind, count]) => (
        <KindCountBadge key={kind} kind={kind} count={count} />
      ))}
    </span>
  );
}
