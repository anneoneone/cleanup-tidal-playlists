import { api } from "../api/client";
import type { ImportedTrackOut } from "../api/types";

/** File types the Music folder refresh reads (AUDIO_EXTENSIONS in music/paths.py). */
export const AUDIO_EXTENSIONS = [
  ".mp3",
  ".flac",
  ".wav",
  ".aiff",
  ".aif",
  ".m4a",
  ".aac",
  ".mp4",
] as const;

/** Value for the `accept` attribute of the file input. */
export const AUDIO_ACCEPT = AUDIO_EXTENSIONS.join(",");

export type ImportResult =
  | { name: string; track: ImportedTrackOut; error?: undefined }
  | { name: string; error: string; track?: undefined };

export type Upload = (playlistId: number, file: File) => Promise<ImportedTrackOut>;

/** Copy one file into the Playlist's Music folder sub-folder (on the server). */
export const uploadFile: Upload = (playlistId, file) =>
  api.post<ImportedTrackOut>(
    `/api/playlists/${playlistId}/files?name=${encodeURIComponent(file.name)}`,
    file,
  );

/** Upload the files one after the other. A failed file does not stop the others. */
export async function importFiles(
  playlistId: number,
  files: readonly File[],
  upload: Upload = uploadFile,
): Promise<ImportResult[]> {
  const results: ImportResult[] = [];
  for (const file of files) {
    try {
      results.push({ name: file.name, track: await upload(playlistId, file) });
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      results.push({ name: file.name, error: message });
    }
  }
  return results;
}

function files(count: number): string {
  return count === 1 ? "1 file" : `${count} files`;
}

/** Headline for the results of one import. */
export function importSummary(results: readonly ImportResult[]): string {
  const added = results.filter((r) => r.track !== undefined).length;
  if (added === 0) return `Could not import ${files(results.length)}`;
  if (added === results.length) return `Imported ${files(added)}`;
  return `Imported ${added} of ${files(results.length)}`;
}

/** What happened to one file. */
export function importOutcome(result: ImportResult): string {
  if (result.track === undefined) return result.error;
  return result.track.library_track
    ? "added as a Library track"
    : "matched a Tidal track of this playlist and is now its file";
}
