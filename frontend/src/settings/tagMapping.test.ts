import { describe, expect, it } from "vitest";
import type { TagMapping } from "../api/types";
import { fromDraft, toDraft, uncategorizedGenres, validateDraft } from "./tagMapping";

const mapping: TagMapping = {
  description: "kept",
  emoji_to_mytag_mapping: {
    Genre: { "🏢": "Techno", "🌃": "House Deep", "🧱": "Breaks" },
    Energy: { "⬆️": "High" },
  },
  folder_structure: {
    genre_root: "Genre",
    genre_categories: { Techno: ["Techno"], "Deep House": ["House Deep"] },
    events_types: ["Partys"],
  },
  no_genre_tag: { group: "Genre", value: "NoGenre" },
};

describe("toDraft / fromDraft", () => {
  it("round-trips without changes and keeps unknown keys in order", () => {
    const result = fromDraft(mapping, toDraft(mapping));
    expect(result).toEqual(mapping);
    expect(Object.keys(result)).toEqual(Object.keys(mapping));
    expect(Object.keys(result.folder_structure)).toEqual(
      Object.keys(mapping.folder_structure),
    );
  });

  it("applies edits to emoji rows and genre categories", () => {
    const draft = toDraft(mapping);
    const genre = draft.groups[0]!;
    genre.rows = genre.rows.filter((row) => row.emoji !== "🧱");
    genre.rows.push({ id: "new", emoji: " 🐋 ", value: " Techno Dub " });
    draft.categories[0]!.genres = "Techno,  Techno Dub ,";
    const result = fromDraft(mapping, draft);
    expect(result.emoji_to_mytag_mapping.Genre).toEqual({
      "🏢": "Techno",
      "🌃": "House Deep",
      "🐋": "Techno Dub",
    });
    expect(result.folder_structure.genre_categories?.Techno).toEqual([
      "Techno",
      "Techno Dub",
    ]);
    expect(result.folder_structure.events_types).toEqual(["Partys"]);
    expect(result.no_genre_tag).toEqual(mapping.no_genre_tag);
  });

  it("does not add genre_categories when the file had none and the draft has none", () => {
    const bare: TagMapping = {
      emoji_to_mytag_mapping: {},
      folder_structure: { genre_root: "Genre" },
    };
    expect(fromDraft(bare, toDraft(bare)).folder_structure).toEqual({
      genre_root: "Genre",
    });
  });
});

describe("validateDraft", () => {
  it("accepts a valid draft", () => {
    expect(validateDraft(toDraft(mapping))).toEqual([]);
  });

  it("reports duplicate emojis, empty rows and duplicate categories", () => {
    const draft = toDraft(mapping);
    draft.groups[1]!.rows.push({ id: "a", emoji: "⬆️", value: "Up" });
    draft.groups[0]!.rows.push({ id: "b", emoji: "", value: "x" });
    draft.categories.push({ id: "c", name: "Techno", genres: "" });
    expect(validateDraft(draft)).toEqual([
      "Genre: every row needs an emoji and a tag value.",
      "Energy: ⬆️ is used twice.",
      'Genre category "Techno" is used twice.',
    ]);
  });
});

describe("uncategorizedGenres", () => {
  it("lists Genre tag values that are in no category", () => {
    expect(uncategorizedGenres(toDraft(mapping))).toEqual(["Breaks"]);
  });
});
