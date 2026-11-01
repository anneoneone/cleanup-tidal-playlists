import { Link, useParams } from "react-router";
import { isApiError } from "../api/client";
import { usePlaylist } from "../api/queries";
import type { TrackOut } from "../api/types";
import { Badge, SourceBadges, type Tone } from "../components/Badge";
import { cx } from "../components/cx";
import { EmptyState, ErrorNotice, Loading } from "../components/Feedback";
import { PageHeader } from "../components/PageHeader";
import {
  folderPath,
  formatCount,
  formatDate,
  formatDateTime,
  formatRelative,
  parseUtc,
} from "../lib/format";

export default function PlaylistDetail() {
  const id = Number(useParams().playlistId);
  const valid = Number.isInteger(id) && id > 0;
  if (!valid) return <EmptyState title="This playlist does not exist" />;
  return <PlaylistDetailView id={id} />;
}

function PlaylistDetailView({ id }: { id: number }) {
  const query = usePlaylist(id);

  if (query.isPending) return <Loading />;
  if (query.isError) {
    return (
      <>
        <BackLink />
        <ErrorNotice
          error={query.error}
          title={
            isApiError(query.error, 404)
              ? "Playlist not found"
              : "Could not load the playlist"
          }
          onRetry={isApiError(query.error, 404) ? undefined : () => void query.refetch()}
        />
      </>
    );
  }
  const playlist = query.data;
  const counts: [string, number, boolean?][] = [
    ["Tidal", playlist.tracks_tidal],
    ["Bandcamp", playlist.tracks_bandcamp],
    ["Local tracks", playlist.tracks_local],
    ["With file", playlist.tracks_with_file],
    ["Without file", playlist.tracks_without_file, playlist.tracks_without_file > 0],
    ["In Rekordbox", playlist.tracks_in_rekordbox],
  ];

  return (
    <>
      <BackLink />
      <PageHeader
        title={playlist.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <SourceBadges sources={playlist.sources} />
            {playlist.gone && <Badge tone="amber">gone</Badge>}
            {!playlist.in_rekordbox && <Badge>not in Rekordbox</Badge>}
          </span>
        }
      />
      <section
        className="mb-6 rounded-lg border border-line bg-surface p-4"
        aria-label="Playlist details"
      >
        <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
          <div className="sm:col-span-1">
            <dt className="text-xs text-muted">Folder placement</dt>
            <dd className="break-words">{folderPath(playlist.folder)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Rekordbox name</dt>
            <dd className="break-words">{playlist.rekordbox_name}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">Last synced</dt>
            <dd>
              {playlist.last_synced_at ? (
                <span title={formatDateTime(parseUtc(playlist.last_synced_at))}>
                  {formatRelative(parseUtc(playlist.last_synced_at))}
                </span>
              ) : (
                "Never"
              )}
            </dd>
          </div>
        </dl>
        <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-4 sm:grid-cols-6">
          {counts.map(([label, value, warn]) => (
            <div key={label}>
              <dt className="text-xs text-muted">{label}</dt>
              <dd
                className={cx(
                  "tabular text-lg font-semibold",
                  warn && "text-amber-700 dark:text-amber-300",
                )}
              >
                {formatCount(value)}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <h2 className="mb-2 text-base font-semibold">
        Tracks{" "}
        <span className="text-sm font-normal text-muted">
          ({formatCount(playlist.tracks.length)})
        </span>
      </h2>
      {playlist.tracks.length === 0 ? (
        <EmptyState title="No tracks" />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-line bg-surface">
          <table className="w-full min-w-[52rem] text-sm">
            <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">
                  Track
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Added
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Present in
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Download
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {playlist.tracks.map((track) => (
                <TrackRow key={track.id} track={track} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function BackLink() {
  return (
    <Link
      to="/playlists"
      className="mb-3 inline-block text-sm text-accent hover:underline"
    >
      ← All playlists
    </Link>
  );
}

const downloadTones: Record<string, Tone> = {
  downloaded: "green",
  downloading: "blue",
  error: "red",
  not_downloaded: "neutral",
};

function TrackRow({ track }: { track: TrackOut }) {
  const removed = track.removed_from_tidal ? parseUtc(track.removed_from_tidal) : null;
  return (
    <tr className="align-top">
      <td className="px-3 py-2.5">
        <div className="font-medium break-words">
          {track.artist} – {track.title}
          {track.version && (
            <span className="font-normal text-muted"> ({track.version})</span>
          )}
        </div>
        {track.album && (
          <div className="text-xs break-words text-muted">{track.album}</div>
        )}
        {track.file_path && (
          <div
            className="mt-0.5 max-w-[24rem] truncate text-xs text-muted"
            title={track.file_path}
          >
            {track.file_path.split("/").pop()}
          </div>
        )}
      </td>
      <td className="px-3 py-2.5 whitespace-nowrap text-muted">
        {track.added_at ? formatDate(parseUtc(track.added_at)) : "–"}
      </td>
      <td className="px-3 py-2.5">
        <div className="flex flex-wrap gap-1">
          {track.in_tidal && <Badge tone="blue">Tidal</Badge>}
          {track.in_bandcamp && <Badge tone="violet">Bandcamp</Badge>}
          {track.in_local && <Badge>Local</Badge>}
          {track.has_file ? (
            <Badge tone="green">file</Badge>
          ) : (
            <Badge tone="amber">no file</Badge>
          )}
          {track.in_rekordbox && <Badge tone="accent">Rekordbox</Badge>}
        </div>
        {removed && (
          <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
            Removed from Tidal {formatDate(removed)}
          </p>
        )}
        {track.tidal_unavailable && (
          <p className="mt-1">
            <Badge tone="red">unavailable on Tidal</Badge>
          </p>
        )}
      </td>
      <td className="px-3 py-2.5">
        {/* Download only applies to Tidal tracks. */}
        {track.in_tidal || track.download_status === "error" ? (
          <Badge tone={downloadTones[track.download_status] ?? "neutral"}>
            {track.download_status.replace(/_/g, " ")}
          </Badge>
        ) : (
          <span className="text-muted">–</span>
        )}
        {track.download_error && (
          <p className="mt-1 max-w-xs text-xs break-words text-red-700 dark:text-red-400">
            {track.download_error}
          </p>
        )}
      </td>
    </tr>
  );
}
