import { describe, expect, it } from "vitest";
import type { TrackOut } from "../api/types";
import {
  DEFAULT_TRACK_FILTER,
  filterAndSortTracks,
  matchesTrack,
  type TrackFilter,
} from "./trackFilter";

function track(id: number, fields: Partial<TrackOut>): TrackOut {
  return {
    id,
    title: `Title ${id}`,
    artist: "Artist",
    album: null,
    version: null,
    isrc: null,
    position: id,
    added_at: null,
    sources: ["tidal"],
    tidal_track: true,
    removed_from_tidal: null,
    download: "present",
    rekordbox: "present",
    sticks: [],
    file_path: null,
    download_status: "downloaded",
    download_error: null,
    tidal_unavailable: false,
    ...fields,
  };
}

const synced = track(1, {
  artist: "Easttown",
  title: "Timeless",
  added_at: "2025-12-31T10:00:00",
});
const missing = track(2, {
  artist: "Romeo Louisa",
  download: "missing",
  added_at: "2025-04-19T10:00:00",
});
const todo = track(3, { artist: "Demuir", download: "absent", rekordbox: "absent" });
const removed = track(4, {
  artist: "Old",
  sources: [],
  download: "unsynced",
  rekordbox: "unsynced",
  added_at: "2024-01-01T10:00:00",
  sticks: [{ id: 2, name: "S2", state: "unsynced" }],
});
const library = track(5, {
  artist: "Ämbient",
  sources: ["library"],
  tidal_track: false,
  rekordbox: "absent",
  file_path: "/music/Playlists/X/Ambient - Dub.mp3",
  sticks: [
    { id: 1, name: "S1", state: "present" },
    { id: 2, name: "S2", state: "present" },
  ],
});
const all = [synced, missing, todo, removed, library];

function only(filter: Partial<TrackFilter>): number[] {
  return all
    .filter((t) => matchesTrack(t, { ...DEFAULT_TRACK_FILTER, ...filter }))
    .map((t) => t.id);
}

describe("matchesTrack", () => {
  it("filters by Source, with 'none' for tracks removed from every Source", () => {
    expect(only({ source: "library" })).toEqual([5]);
    expect(only({ source: "tidal" })).toEqual([1, 2, 3]);
    expect(only({ source: "none" })).toEqual([4]);
  });

  it("filters by status", () => {
    expect(only({ state: "to_download" })).toEqual([3]);
    expect(only({ state: "missing" })).toEqual([2]);
    expect(only({ state: "unsynced" })).toEqual([4]);
    expect(only({ state: "not_in_rekordbox" })).toEqual([3, 5]);
    expect(only({ state: "in_rekordbox" })).toEqual([1, 2, 4]);
  });

  it("filters by USB stick; 'not on' only counts tracks still in a Source", () => {
    expect(only({ stick: "any" })).toEqual([4, 5]);
    expect(only({ stick: "none" })).toEqual([1, 2, 3]);
    expect(only({ stick: "unsynced" })).toEqual([4]);
    expect(only({ stick: "on:1" })).toEqual([5]);
    expect(only({ stick: "on:2" })).toEqual([4, 5]);
    expect(only({ stick: "off:1" })).toEqual([1, 2, 3]);
  });

  it("searches artist, title and file name, ignoring accents and case", () => {
    expect(only({ query: "ambient dub" })).toEqual([5]);
    expect(only({ query: "TIMELESS" })).toEqual([1]);
  });
});

describe("filterAndSortTracks", () => {
  it("sorts by date added with undated tracks last in both directions", () => {
    const ids = (dir: "asc" | "desc") =>
      filterAndSortTracks(all, DEFAULT_TRACK_FILTER, "added", dir).map((t) => t.id);
    expect(ids("asc")).toEqual([4, 2, 1, 5, 3]);
    expect(ids("desc")).toEqual([1, 2, 4, 5, 3]);
  });

  it("puts problems first when sorting a target descending", () => {
    const ids = filterAndSortTracks(all, DEFAULT_TRACK_FILTER, "download", "desc").map(
      (t) => t.id,
    );
    expect(ids.slice(0, 3)).toEqual([2, 4, 3]); // missing, unsynced, not downloaded
  });

  it("sorts by artist", () => {
    const artists = filterAndSortTracks(all, DEFAULT_TRACK_FILTER, "track", "asc").map(
      (t) => t.artist,
    );
    expect(artists).toEqual(["Ämbient", "Demuir", "Easttown", "Old", "Romeo Louisa"]);
  });
});
