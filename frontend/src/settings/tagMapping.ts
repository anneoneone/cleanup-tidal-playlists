import type { TagMapping } from "../api/types";

export interface EmojiRow {
  id: string;
  emoji: string;
  value: string;
}

export interface EmojiGroup {
  name: string;
  rows: EmojiRow[];
}

export interface CategoryRow {
  id: string;
  name: string;
  /** Genre tag values, comma separated as typed. */
  genres: string;
}

export interface TagMappingDraft {
  groups: EmojiGroup[];
  categories: CategoryRow[];
}

let counter = 0;
export function newRowId(): string {
  counter += 1;
  return `row-${counter}`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function splitGenres(text: string): string[] {
  return text
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}

/** Editable rows from the mapping file. */
export function toDraft(mapping: TagMapping): TagMappingDraft {
  const groups = isRecord(mapping.emoji_to_mytag_mapping)
    ? mapping.emoji_to_mytag_mapping
    : {};
  const categories = isRecord(mapping.folder_structure?.genre_categories)
    ? mapping.folder_structure.genre_categories
    : {};
  return {
    groups: Object.entries(groups).map(([name, table]) => ({
      name,
      rows: Object.entries(isRecord(table) ? table : {}).map(([emoji, value]) => ({
        id: newRowId(),
        emoji,
        value: String(value),
      })),
    })),
    categories: Object.entries(categories).map(([name, genres]) => ({
      id: newRowId(),
      name,
      genres: Array.isArray(genres) ? genres.map(String).join(", ") : "",
    })),
  };
}

/**
 * Write the draft back into the mapping. Keys the editor does not know stay
 * as they are, in their original order.
 */
export function fromDraft(original: TagMapping, draft: TagMappingDraft): TagMapping {
  const emojiMapping: Record<string, Record<string, string>> = {};
  for (const group of draft.groups) {
    const table: Record<string, string> = {};
    for (const row of group.rows) table[row.emoji.trim()] = row.value.trim();
    emojiMapping[group.name] = table;
  }
  const categories: Record<string, string[]> = {};
  for (const row of draft.categories)
    categories[row.name.trim()] = splitGenres(row.genres);

  const folderStructure = { ...original.folder_structure };
  if (draft.categories.length > 0 || "genre_categories" in folderStructure) {
    folderStructure.genre_categories = categories;
  }
  return {
    ...original,
    emoji_to_mytag_mapping: emojiMapping,
    folder_structure: folderStructure,
  };
}

/** Problems that block saving. */
export function validateDraft(draft: TagMappingDraft): string[] {
  const problems: string[] = [];
  for (const group of draft.groups) {
    const seen = new Set<string>();
    for (const row of group.rows) {
      const emoji = row.emoji.trim();
      if (!emoji || !row.value.trim()) {
        problems.push(`${group.name}: every row needs an emoji and a tag value.`);
        break;
      }
      if (seen.has(emoji)) problems.push(`${group.name}: ${emoji} is used twice.`);
      seen.add(emoji);
    }
  }
  const names = new Set<string>();
  for (const row of draft.categories) {
    const name = row.name.trim();
    if (!name) problems.push("Every genre category needs a name.");
    else if (names.has(name)) problems.push(`Genre category "${name}" is used twice.`);
    names.add(name);
  }
  return [...new Set(problems)];
}

/** Genre tag values that are in no genre category (they land in the uncategorized folder). */
export function uncategorizedGenres(draft: TagMappingDraft): string[] {
  const genreGroup = draft.groups.find((group) => group.name === "Genre");
  if (!genreGroup) return [];
  const categorized = new Set(draft.categories.flatMap((row) => splitGenres(row.genres)));
  const values = genreGroup.rows.map((row) => row.value.trim()).filter(Boolean);
  return [...new Set(values)].filter((value) => !categorized.has(value));
}
