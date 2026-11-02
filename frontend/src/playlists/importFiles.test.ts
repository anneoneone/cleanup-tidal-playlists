import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../api/client";
import type { ImportedTrackOut } from "../api/types";
import {
  AUDIO_ACCEPT,
  type ImportResult,
  importFiles,
  importOutcome,
  importSummary,
} from "./importFiles";

const track = (id: number, library_track = true): ImportedTrackOut => ({
  track_id: id,
  file_path: `Playlists/Peak/${id}.mp3`,
  library_track,
});

describe("importFiles", () => {
  it("uploads one file after the other and keeps going after a failure", async () => {
    const order: string[] = [];
    const upload = vi.fn((playlistId: number, file: File) => {
      order.push(file.name);
      expect(playlistId).toBe(5);
      if (file.name === "b.mp3") {
        return Promise.reject(
          new ApiError("b.mp3 is already in the folder Playlists/Peak", 409),
        );
      }
      return Promise.resolve(track(order.length));
    });
    const files = ["a.mp3", "b.mp3", "c.flac"].map((n) => new File(["x"], n));

    const results = await importFiles(5, files, upload);

    expect(order).toEqual(["a.mp3", "b.mp3", "c.flac"]);
    expect(results).toEqual([
      { name: "a.mp3", track: track(1) },
      { name: "b.mp3", error: "b.mp3 is already in the folder Playlists/Peak" },
      { name: "c.flac", track: track(3) },
    ]);
  });
});

describe("importSummary", () => {
  const ok: ImportResult = { name: "a.mp3", track: track(1) };
  const failed: ImportResult = { name: "b.mp3", error: "nope" };

  it.each([
    [[ok], "Imported 1 file"],
    [[ok, ok], "Imported 2 files"],
    [[ok, failed], "Imported 1 of 2 files"],
    [[failed], "Could not import 1 file"],
    [[failed, failed], "Could not import 2 files"],
  ])("summarises %#", (results, text) => {
    expect(importSummary(results)).toBe(text);
  });

  it("says what happened to each file", () => {
    expect(importOutcome(ok)).toBe("added as a Library track");
    expect(importOutcome({ name: "t.mp3", track: track(2, false) })).toMatch(
      /matched a Tidal track/,
    );
    expect(importOutcome(failed)).toBe("nope");
  });
});

it("accepts the audio types the Music folder refresh reads", () => {
  expect(AUDIO_ACCEPT.split(",")).toEqual(
    expect.arrayContaining([".mp3", ".flac", ".wav", ".aiff", ".m4a"]),
  );
});
