import type { Source, TrackOut } from "../api/types";
import type { SortDir } from "../components/SortHeader";

export type TargetState = TrackOut["download"];

/** "none": removed from every Source. */
export type TrackSourceFilter = "all" | Source | "none";
export type TrackStateFilter =
  "all" | "to_download" | "missing" | "unsynced" | "not_in_rekordbox" | "in_rekordbox";

export interface TrackFilter {
  query: string;
  source: TrackSourceFilter;
  state: TrackStateFilter;
}

export const DEFAULT_TRACK_FILTER: TrackFilter = {
  query: "",
  source: "all",
  state: "all",
};

export const TRACK_SORT_KEYS = ["track", "added", "download", "rekordbox"] as const;
export type TrackSortKey = (typeof TRACK_SORT_KEYS)[number];

export function isTrackSortKey(value: string | null): value is TrackSortKey {
  return value !== null && (TRACK_SORT_KEYS as readonly string[]).includes(value);
}

function normalize(text: string): string {
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

function matchesState(track: TrackOut, state: TrackStateFilter): boolean {
  const wanted = track.sources.length > 0;
  switch (state) {
    case "all":
      return true;
    case "to_download":
      return wanted && track.download === "absent";
    case "missing":
      return track.download === "missing";
    case "unsynced":
      return track.download === "unsynced" || track.rekordbox === "unsynced";
    case "not_in_rekordbox":
      return wanted && track.rekordbox === "absent";
    case "in_rekordbox":
      return track.rekordbox !== "absent";
  }
}

export function matchesTrack(track: TrackOut, filter: TrackFilter): boolean {
  if (filter.source === "none" && track.sources.length > 0) return false;
  if (
    filter.source !== "all" &&
    filter.source !== "none" &&
    !track.sources.includes(filter.source)
  ) {
    return false;
  }
  if (!matchesState(track, filter.state)) return false;
  const query = normalize(filter.query.trim());
  if (!query) return true;
  const haystack = normalize(
    [
      track.artist,
      track.title,
      track.version ?? "",
      track.album ?? "",
      track.file_path?.split("/").pop() ?? "",
    ].join(" "),
  );
  return query.split(/\s+/).every((word) => haystack.includes(word));
}

/** Higher = needs more attention, so "desc" puts problems first. */
const STATE_RANK: Record<TargetState, number> = {
  present: 0,
  absent: 1,
  unsynced: 2,
  missing: 3,
};

const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });

function addedTime(track: TrackOut): number | null {
  return track.added_at ? Date.parse(track.added_at) : null;
}

function compare(a: TrackOut, b: TrackOut, key: TrackSortKey): number {
  switch (key) {
    case "track":
      return collator.compare(a.artist, b.artist) || collator.compare(a.title, b.title);
    case "added":
      return (addedTime(a) ?? 0) - (addedTime(b) ?? 0);
    case "download":
      return STATE_RANK[a.download] - STATE_RANK[b.download];
    case "rekordbox":
      return STATE_RANK[a.rekordbox] - STATE_RANK[b.rekordbox];
  }
}

export function filterAndSortTracks(
  tracks: readonly TrackOut[],
  filter: TrackFilter,
  sort: TrackSortKey,
  dir: SortDir,
): TrackOut[] {
  const sign = dir === "asc" ? 1 : -1;
  return tracks
    .filter((track) => matchesTrack(track, filter))
    .sort((a, b) => {
      // Tracks without a date always go last when sorting by date.
      if (sort === "added") {
        const missing = Number(addedTime(a) === null) - Number(addedTime(b) === null);
        if (missing !== 0) return missing;
      }
      return (
        sign * compare(a, b, sort) || collator.compare(a.artist, b.artist) || a.id - b.id
      );
    });
}

/** Sort direction used when a column is clicked for the first time. */
export function firstSortDir(key: TrackSortKey): SortDir {
  return key === "download" || key === "rekordbox" ? "desc" : "asc";
}
