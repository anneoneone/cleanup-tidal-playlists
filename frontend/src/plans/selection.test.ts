import { describe, expect, it } from "vitest";
import type { Change, Plan, PlanGroup } from "../api/types";
import {
  allSelected,
  countByKind,
  groupsWithChanges,
  initialSelection,
  isPlanEmpty,
  planTotals,
  selectAll,
  selectedCount,
  selectedKeys,
  selectNone,
  toggleGroup,
} from "./selection";
import { makeChange, makeGroup, makePlan } from "../test/planFactory";

function change(kind: Change["kind"]): Change {
  return makeChange(kind);
}

function group(key: string, changes: Change[], selected = true): PlanGroup {
  return makeGroup({ key, title: key, selected_by_default: selected, changes });
}

const peak = group("p1", [
  change("create_playlist"),
  change("add_track"),
  change("add_track"),
]);
const deep = group("p2", [change("remove_track")]);
const quiet = group("p3", []);
const off = group("p4", [change("rename_playlist")], false);
const del = group("delete", [change("delete_playlist")], false);
const groups = [peak, deep, quiet, off, del];

function plan(list: PlanGroup[]): Plan {
  return makePlan({ groups: list });
}

describe("initialSelection", () => {
  it("selects groups with changes that are selected by default", () => {
    expect([...initialSelection(groups)]).toEqual(["p1", "p2"]);
  });

  it("never selects the delete group, even if the Plan says so", () => {
    expect(initialSelection(groups).has("delete")).toBe(false);
    const flagged = group("delete", [change("delete_playlist")], true);
    expect(initialSelection([flagged]).size).toBe(0);
  });

  it("skips groups without changes even when selected by default", () => {
    expect(initialSelection([quiet]).size).toBe(0);
  });
});

describe("toggleGroup", () => {
  it("adds and removes a key without changing the input", () => {
    const start = initialSelection(groups);
    const added = toggleGroup(start, "delete");
    expect(added.has("delete")).toBe(true);
    expect(start.has("delete")).toBe(false);
    expect(toggleGroup(added, "delete").has("delete")).toBe(false);
  });
});

describe("selectAll / selectNone", () => {
  it("selects all groups with changes except the delete group", () => {
    expect([...selectAll(groups, selectNone())].sort()).toEqual(["p1", "p2", "p4"]);
  });

  it("keeps the delete group when it was already checked by hand", () => {
    const withDelete = toggleGroup(selectNone(), "delete");
    expect(selectAll(groups, withDelete).has("delete")).toBe(true);
  });

  it("selectNone clears everything", () => {
    expect(selectNone().size).toBe(0);
  });

  it("allSelected ignores the delete group", () => {
    expect(allSelected(groups, selectAll(groups, selectNone()))).toBe(true);
    expect(allSelected(groups, initialSelection(groups))).toBe(false);
    expect(allSelected([quiet], selectNone())).toBe(false);
  });
});

describe("selectedKeys / selectedCount", () => {
  it("returns selected keys in Plan order and ignores unknown or empty groups", () => {
    const selection = new Set(["delete", "p3", "p1", "ghost"]);
    expect(selectedKeys(groups, selection)).toEqual(["p1", "delete"]);
    expect(selectedCount(groups, selection)).toBe(2);
  });
});

describe("counts", () => {
  it("counts changes per kind in a fixed order", () => {
    expect(countByKind(peak.changes ?? [])).toEqual([
      ["create_playlist", 1],
      ["add_track", 2],
    ]);
  });

  it("sums totals over all groups", () => {
    expect(planTotals(groups)).toEqual([
      ["create_playlist", 1],
      ["rename_playlist", 1],
      ["add_track", 2],
      ["remove_track", 1],
      ["delete_playlist", 1],
    ]);
  });
});

describe("empty Plan", () => {
  it("is empty when no group has changes", () => {
    expect(isPlanEmpty(plan([quiet]))).toBe(true);
    expect(isPlanEmpty(plan([]))).toBe(true);
  });

  it("is not empty when one group has a change", () => {
    expect(isPlanEmpty(plan(groups))).toBe(false);
    expect(groupsWithChanges(plan(groups)).map((g) => g.key)).toEqual([
      "p1",
      "p2",
      "p4",
      "delete",
    ]);
  });
});
