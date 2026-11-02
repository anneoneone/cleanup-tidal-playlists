import type { PlaylistOut, Source } from "../api/types";

export type SourceFilter = "all" | Source;
export type GoneFilter = "all" | "gone" | "active";

export interface PlaylistFilter {
  query: string;
  source: SourceFilter;
  gone: GoneFilter;
  notInRekordbox: boolean;
}

export const SORT_KEYS = [
  "name",
  "folder",
  "tracks_tidal",
  "tracks_with_file",
  "tracks_without_file",
  "tracks_in_rekordbox",
] as const;
export type SortKey = (typeof SORT_KEYS)[number];
export type SortDir = "asc" | "desc";

export const DEFAULT_FILTER: PlaylistFilter = {
  query: "",
  source: "all",
  gone: "all",
  notInRekordbox: false,
};

function normalize(text: string): string {
  return text.normalize("NFKD").replace(/\p{M}/gu, "").toLowerCase();
}

export function matchesFilter(playlist: PlaylistOut, filter: PlaylistFilter): boolean {
  if (filter.source !== "all" && !playlist.sources.includes(filter.source)) return false;
  if (filter.gone === "gone" && !playlist.gone) return false;
  if (filter.gone === "active" && playlist.gone) return false;
  if (filter.notInRekordbox && playlist.in_rekordbox) return false;
  const query = normalize(filter.query.trim());
  if (!query) return true;
  const haystack = normalize(
    [playlist.name, playlist.rekordbox_name, ...playlist.folder].join(" "),
  );
  return query.split(/\s+/).every((word) => haystack.includes(word));
}

const collator = new Intl.Collator("en", { sensitivity: "base", numeric: true });

const EMOJI =
  /\p{Extended_Pictographic}|\p{Regional_Indicator}|[\u{1F3FB}-\u{1F3FF}]|\uFE0F|\u200D/gu;

/** The name without emojis, for sorting by letters. */
export function sortableName(name: string): string {
  return name.replace(EMOJI, "").replace(/\s+/g, " ").trim();
}

function compare(a: PlaylistOut, b: PlaylistOut, key: SortKey): number {
  switch (key) {
    case "name":
      return collator.compare(sortableName(a.name), sortableName(b.name));
    case "folder":
      return collator.compare(a.folder.join("/"), b.folder.join("/"));
    default:
      return a[key] - b[key];
  }
}

export function filterAndSort(
  playlists: readonly PlaylistOut[],
  filter: PlaylistFilter,
  sort: SortKey,
  dir: SortDir,
): PlaylistOut[] {
  const sign = dir === "asc" ? 1 : -1;
  return playlists
    .filter((p) => matchesFilter(p, filter))
    .sort((a, b) => sign * compare(a, b, sort) || collator.compare(a.name, b.name));
}

export function isSortKey(value: string | null): value is SortKey {
  return value !== null && (SORT_KEYS as readonly string[]).includes(value);
}
