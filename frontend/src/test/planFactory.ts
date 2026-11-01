import type { Change, Plan, PlanGroup } from "../api/types";

/** A Change with every optional field empty. */
export function makeChange(kind: Change["kind"], summary: string = kind): Change {
  return {
    kind,
    summary,
    track_id: null,
    file_path: null,
    content_id: null,
    song_id: null,
    name: null,
    old_name: null,
    folder: null,
    old_folder: null,
    genre: null,
    playlist_id: null,
    rekordbox_playlist_id: null,
  };
}

/** A PlanGroup with defaults for everything not given. */
export function makeGroup(
  group: Pick<PlanGroup, "key" | "title"> & Partial<PlanGroup>,
): PlanGroup {
  return {
    playlist_id: null,
    rekordbox_playlist_id: null,
    target_name: null,
    folder: [],
    selected_by_default: true,
    changes: [],
    member_track_ids: [],
    ...group,
  };
}

/** A Plan with defaults for everything not given. */
export function makePlan(plan: Partial<Plan> = {}): Plan {
  return {
    created_at: "2026-11-01T10:00:00",
    fingerprint: "x",
    rekordbox_db: "/tmp/master.db",
    scope: null,
    groups: [],
    links: [],
    new_folders: [],
    unchanged_playlists: 0,
    warnings: [],
    ...plan,
  };
}
