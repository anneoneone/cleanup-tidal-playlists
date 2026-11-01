import type { Change, ChangeKind, Plan, PlanGroup } from "../api/types";

/** Key of the group that deletes playlists in Rekordbox. */
export const DELETE_GROUP_KEY = "delete";

export type Selection = ReadonlySet<string>;

export function changesOf(group: PlanGroup): Change[] {
  return group.changes;
}

export function isDangerous(group: PlanGroup): boolean {
  return group.key === DELETE_GROUP_KEY;
}

/** Groups that have at least one change, in Plan order. */
export function groupsWithChanges(plan: Plan): PlanGroup[] {
  return plan.groups.filter((group) => changesOf(group).length > 0);
}

export function isPlanEmpty(plan: Plan): boolean {
  return groupsWithChanges(plan).length === 0;
}

/** Groups selected before the user changes anything. Never playlist deletions. */
export function initialSelection(groups: readonly PlanGroup[]): Selection {
  return new Set(
    groups
      .filter(
        (group) =>
          group.selected_by_default && !isDangerous(group) && changesOf(group).length > 0,
      )
      .map((group) => group.key),
  );
}

export function toggleGroup(selection: Selection, key: string): Selection {
  const next = new Set(selection);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/**
 * Select every group with changes, except playlist deletions: those are
 * dangerous and must always be checked by hand.
 */
export function selectAll(groups: readonly PlanGroup[], selection: Selection): Selection {
  const next = new Set(
    groups.filter((g) => changesOf(g).length > 0 && !isDangerous(g)).map((g) => g.key),
  );
  if (selection.has(DELETE_GROUP_KEY)) next.add(DELETE_GROUP_KEY);
  return next;
}

export function selectNone(): Selection {
  return new Set();
}

/** Selected keys that belong to a group with changes, in Plan order (the apply body). */
export function selectedKeys(
  groups: readonly PlanGroup[],
  selection: Selection,
): string[] {
  return groups
    .filter((group) => changesOf(group).length > 0 && selection.has(group.key))
    .map((group) => group.key);
}

export function selectedCount(
  groups: readonly PlanGroup[],
  selection: Selection,
): number {
  return selectedKeys(groups, selection).length;
}

/** Whether every non-dangerous group with changes is selected. */
export function allSelected(groups: readonly PlanGroup[], selection: Selection): boolean {
  const candidates = groups.filter((g) => changesOf(g).length > 0 && !isDangerous(g));
  return candidates.length > 0 && candidates.every((g) => selection.has(g.key));
}

export const CHANGE_KIND_ORDER: readonly ChangeKind[] = [
  "create_playlist",
  "rename_playlist",
  "move_playlist",
  "import_track",
  "add_track",
  "remove_track",
  "set_genre",
  "delete_playlist",
];

/** Change counts by kind (only kinds that occur), in a fixed order. */
export function countByKind(changes: readonly Change[]): [ChangeKind, number][] {
  const counts = new Map<ChangeKind, number>();
  for (const change of changes)
    counts.set(change.kind, (counts.get(change.kind) ?? 0) + 1);
  return CHANGE_KIND_ORDER.filter((kind) => counts.has(kind)).map((kind) => [
    kind,
    counts.get(kind) ?? 0,
  ]);
}

export function planTotals(groups: readonly PlanGroup[]): [ChangeKind, number][] {
  return countByKind(groups.flatMap(changesOf));
}
