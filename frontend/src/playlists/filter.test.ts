import { describe, expect, it } from "vitest";
import type { PlaylistOut } from "../api/types";
import { DEFAULT_FILTER, filterAndSort, matchesFilter, sortableName } from "./filter";

function playlist(overrides: Partial<PlaylistOut>): PlaylistOut {
  return {
    id: 1,
    name: "Peak Time 🏢⬆️",
    sources: ["tidal"],
    gone: false,
    folder: ["Genre", "Techno"],
    rekordbox_name: "Peak Time ⬆️",
    in_rekordbox: true,
    tracks_tidal: 10,
    tracks_bandcamp: 0,
    tracks_local: 0,
    tracks_with_file: 9,
    tracks_without_file: 1,
    tracks_in_rekordbox: 9,
    ...overrides,
  };
}

const peak = playlist({});
const dub = playlist({
  id: 2,
  name: "Dub Lab 🐋",
  rekordbox_name: "Dub Lab",
  sources: ["bandcamp"],
  in_rekordbox: false,
  tracks_tidal: 0,
  tracks_with_file: 3,
});
const old = playlist({
  id: 3,
  name: "Café Nights",
  rekordbox_name: "Café Nights",
  gone: true,
  folder: ["Genre", "Deep House"],
});

describe("matchesFilter", () => {
  it("matches words in name, Rekordbox name and folder, ignoring case and accents", () => {
    expect(matchesFilter(old, { ...DEFAULT_FILTER, query: "cafe" })).toBe(true);
    expect(matchesFilter(peak, { ...DEFAULT_FILTER, query: "techno peak" })).toBe(true);
    expect(matchesFilter(peak, { ...DEFAULT_FILTER, query: "house" })).toBe(false);
  });

  it("filters by source, gone and Rekordbox presence", () => {
    expect(matchesFilter(dub, { ...DEFAULT_FILTER, source: "bandcamp" })).toBe(true);
    expect(matchesFilter(peak, { ...DEFAULT_FILTER, source: "bandcamp" })).toBe(false);
    expect(matchesFilter(old, { ...DEFAULT_FILTER, gone: "gone" })).toBe(true);
    expect(matchesFilter(old, { ...DEFAULT_FILTER, gone: "active" })).toBe(false);
    expect(matchesFilter(dub, { ...DEFAULT_FILTER, notInRekordbox: true })).toBe(true);
    expect(matchesFilter(peak, { ...DEFAULT_FILTER, notInRekordbox: true })).toBe(false);
  });
});

describe("filterAndSort", () => {
  it("sorts by name and by numbers in both directions", () => {
    const list = [peak, dub, old];
    expect(filterAndSort(list, DEFAULT_FILTER, "name", "asc").map((p) => p.id)).toEqual([
      3, 2, 1,
    ]);
    expect(
      filterAndSort(list, DEFAULT_FILTER, "tracks_tidal", "desc").map((p) => p.id),
    ).toEqual([3, 1, 2]);
  });

  it("does not change the input list", () => {
    const list = [peak, dub];
    filterAndSort(list, DEFAULT_FILTER, "name", "asc");
    expect(list.map((p) => p.id)).toEqual([1, 2]);
  });
});

describe("sortableName", () => {
  it("drops emojis, flags and skin tones", () => {
    expect(sortableName("🏢⬆️ Peak Time")).toBe("Peak Time");
    expect(sortableName("Italo Box 🇮🇹❓")).toBe("Italo Box");
    expect(sortableName("👵🏻 Old 💾")).toBe("Old");
  });
});
