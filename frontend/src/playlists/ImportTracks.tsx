import { useRef } from "react";
import { Link } from "react-router";
import { isRunning, useCurrentJob, type useImportFiles } from "../api/queries";
import { Button } from "../components/Button";
import { Notice } from "../components/Feedback";
import { AUDIO_ACCEPT, importOutcome, importSummary } from "./importFiles";

type Importer = ReturnType<typeof useImportFiles>;

/**
 * Opens the system file dialog. The chosen files are copied into the
 * Playlist's Music folder sub-folder and become Library tracks.
 */
export function ImportButton({ importer }: { importer: Importer }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const jobRunning = isRunning(useCurrentJob().data);
  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={AUDIO_ACCEPT}
        hidden
        aria-label="Audio files to import"
        onChange={(event) => {
          const files = Array.from(event.target.files ?? []);
          // Reset, so picking the same file again fires a change.
          event.target.value = "";
          if (files.length > 0) importer.mutate(files);
        }}
      />
      <Button
        onClick={() => inputRef.current?.click()}
        busy={importer.isPending}
        disabled={jobRunning}
        title={
          jobRunning
            ? "Wait until the running job ends"
            : "Copy audio files from this Mac into this playlist's Music folder sub-folder"
        }
      >
        {importer.isPending ? "Importing…" : "Import tracks"}
      </Button>
    </>
  );
}

export function ImportResults({ importer }: { importer: Importer }) {
  const results = importer.data;
  if (!results || results.length === 0) return null;
  const added = results.filter((r) => r.track !== undefined).length;
  const tone = added === results.length ? "success" : added > 0 ? "warning" : "danger";
  return (
    <Notice
      tone={tone}
      title={importSummary(results)}
      className="mb-6"
      actions={
        <Button size="sm" onClick={() => importer.reset()}>
          Close
        </Button>
      }
    >
      <ul className="space-y-0.5">
        {results.map((result, index) => (
          <li key={`${index}-${result.name}`}>
            <span className="font-medium">{result.name}</span>: {importOutcome(result)}
          </li>
        ))}
      </ul>
      {added > 0 && (
        <p className="pt-1">
          The next Plan adds {added === 1 ? "it" : "them"} to Rekordbox.{" "}
          <Link to="/sync" className="font-medium underline">
            Go to Sync
          </Link>
        </p>
      )}
    </Notice>
  );
}
