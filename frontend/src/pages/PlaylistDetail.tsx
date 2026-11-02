import { Link, useParams, useSearchParams } from "react-router";
import { isApiError } from "../api/client";
import { useImportFiles, usePlaylist } from "../api/queries";
import type { TrackOut } from "../api/types";
import { Badge, SourceBadges } from "../components/Badge";
import { cx } from "../components/cx";
import { EmptyState, ErrorNotice, Loading } from "../components/Feedback";
import { Select, TextInput } from "../components/form";
import { PageHeader } from "../components/PageHeader";
import { type SortDir, SortHeader } from "../components/SortHeader";
import {
  folderPath,
  formatCount,
  formatDate,
  formatDateTime,
  formatRelative,
  parseUtc,
} from "../lib/format";
import { ImportButton, ImportResults } from "../playlists/ImportTracks";
import {
  filterAndSortTracks,
  firstSortDir,
  isTrackSortKey,
  type TargetState,
  type TrackFilter,
  type TrackSortKey,
  type TrackSourceFilter,
  type TrackStateFilter,
} from "../playlists/trackFilter";

const SOURCES: { value: TrackSourceFilter; label: string }[] = [
  { value: "all", label: "All Sources" },
  { value: "tidal", label: "Tidal" },
  { value: "bandcamp", label: "Bandcamp" },
  { value: "library", label: "Library" },
  { value: "none", label: "Removed from all Sources" },
];

const STATES: { value: TrackStateFilter; label: string }[] = [
  { value: "all", label: "Any status" },
  { value: "to_download", label: "Not downloaded" },
  { value: "missing", label: "File missing" },
  { value: "unsynced", label: "Unsynced" },
  { value: "not_in_rekordbox", label: "Not in Rekordbox" },
  { value: "in_rekordbox", label: "In Rekordbox" },
];

function readFilter(params: URLSearchParams): TrackFilter {
  const source = params.get("source");
  const state = params.get("state");
  return {
    query: params.get("q") ?? "",
    source: SOURCES.some((s) => s.value === source)
      ? (source as TrackSourceFilter)
      : "all",
    state: STATES.some((s) => s.value === state) ? (state as TrackStateFilter) : "all",
  };
}

export default function PlaylistDetail() {
  const id = Number(useParams().playlistId);
  const valid = Number.isInteger(id) && id > 0;
  if (!valid) return <EmptyState title="This playlist does not exist" />;
  return <PlaylistDetailView id={id} />;
}

function PlaylistDetailView({ id }: { id: number }) {
  const query = usePlaylist(id);
  const importer = useImportFiles(id);
  const [params, setParams] = useSearchParams();

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
    ["Library", playlist.tracks_library],
    ["With file", playlist.tracks_with_file],
    ["Without file", playlist.tracks_without_file, playlist.tracks_without_file > 0],
    ["File missing", playlist.tracks_missing, playlist.tracks_missing > 0],
    ["In Rekordbox", playlist.tracks_in_rekordbox],
    ["Unsynced", playlist.tracks_unsynced, playlist.tracks_unsynced > 0],
  ];

  const filter = readFilter(params);
  const sortParam = params.get("sort");
  const sort: TrackSortKey = isTrackSortKey(sortParam) ? sortParam : "added";
  const dir: SortDir = params.get("dir") === "desc" ? "desc" : "asc";
  const rows = filterAndSortTracks(playlist.tracks, filter, sort, dir);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  const sortBy = (key: TrackSortKey) => {
    const nextDir: SortDir =
      sort === key ? (dir === "asc" ? "desc" : "asc") : firstSortDir(key);
    update({
      sort: key === "added" ? null : key,
      dir: nextDir === "asc" ? null : "desc",
    });
  };

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
        actions={<ImportButton importer={importer} />}
      />
      <ImportResults importer={importer} />
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
        <dl className="mt-4 grid grid-cols-4 gap-3 border-t border-line pt-4 lg:grid-cols-8">
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
        <>
          <div className="mb-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_auto_auto]">
            <div className="sm:col-span-2 lg:col-span-1">
              <label htmlFor="track-search" className="sr-only">
                Search tracks
              </label>
              <TextInput
                id="track-search"
                type="search"
                placeholder="Search artist, title, album or file"
                value={filter.query}
                onChange={(event) => update({ q: event.target.value })}
              />
            </div>
            <div>
              <label htmlFor="track-source" className="sr-only">
                Source
              </label>
              <Select
                id="track-source"
                value={filter.source}
                onChange={(event) =>
                  update({
                    source: event.target.value === "all" ? null : event.target.value,
                  })
                }
              >
                {SOURCES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor="track-state" className="sr-only">
                Status
              </label>
              <Select
                id="track-state"
                value={filter.state}
                onChange={(event) =>
                  update({
                    state: event.target.value === "all" ? null : event.target.value,
                  })
                }
              >
                {STATES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </Select>
            </div>
          </div>
          <p className="mb-2 text-xs text-muted" aria-live="polite">
            {rows.length === playlist.tracks.length
              ? `${formatCount(rows.length)} tracks`
              : `${formatCount(rows.length)} of ${formatCount(playlist.tracks.length)} tracks`}
          </p>
          {rows.length === 0 ? (
            <EmptyState title="No track matches the filters" />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[48rem] text-sm">
                <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
                  <tr>
                    <SortHeader
                      label="Track"
                      column="track"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                    />
                    <SortHeader
                      label="Added"
                      column="added"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                    />
                    <th scope="col" className="px-3 py-2 font-medium">
                      Source
                    </th>
                    <SortHeader
                      label="Download"
                      column="download"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                    />
                    <SortHeader
                      label="Rekordbox"
                      column="rekordbox"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                    />
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {rows.map((track) => (
                    <TrackRow key={track.id} track={track} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
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

/** Text for screen readers and tooltips, per target and state. */
const STATE_TEXT: Record<"download" | "rekordbox", Record<TargetState, string>> = {
  download: {
    present: "File on disk",
    absent: "Not downloaded",
    unsynced: "File still on disk, but removed from every Source",
    missing: "File missing: it was downloaded, but is gone now",
  },
  rekordbox: {
    present: "In the Rekordbox playlist",
    absent: "Not in the Rekordbox playlist",
    unsynced: "Still in Rekordbox, but removed from every Source",
    missing: "Missing from Rekordbox",
  },
};

function TargetCell({
  target,
  state,
}: {
  target: "download" | "rekordbox";
  state: TargetState;
}) {
  const text = STATE_TEXT[target][state];
  switch (state) {
    case "present":
      return (
        <span title={text} className="font-semibold text-green-700 dark:text-green-400">
          <span aria-hidden="true">✓</span>
          <span className="sr-only">{text}</span>
        </span>
      );
    case "absent":
      return (
        <span title={text} className="text-muted">
          <span aria-hidden="true">–</span>
          <span className="sr-only">{text}</span>
        </span>
      );
    case "unsynced":
      return (
        <Badge tone="amber">
          <span title={text}>⚠ unsynced</span>
        </Badge>
      );
    case "missing":
      return (
        <Badge tone="red">
          <span title={text}>✗ missing</span>
        </Badge>
      );
  }
}

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
        {track.sources.length > 0 ? (
          <SourceBadges sources={track.sources} />
        ) : track.tidal_track ? (
          <span className="text-xs text-muted">
            <span className="line-through">Tidal</span>{" "}
            {removed ? `removed ${formatDate(removed)}` : "removed"}
          </span>
        ) : (
          <span className="text-muted">–</span>
        )}
      </td>
      <td className="px-3 py-2.5">
        <TargetCell target="download" state={track.download} />
        {track.download === "absent" && track.tidal_unavailable && (
          <p className="mt-1">
            <Badge tone="red">unavailable on Tidal</Badge>
          </p>
        )}
        {track.download_status === "downloading" && (
          <p className="mt-1">
            <Badge tone="blue">downloading</Badge>
          </p>
        )}
        {track.download_error && (
          <p className="mt-1 max-w-xs text-xs break-words text-red-700 dark:text-red-400">
            {track.download_error}
          </p>
        )}
      </td>
      <td className="px-3 py-2.5">
        <TargetCell target="rekordbox" state={track.rekordbox} />
      </td>
    </tr>
  );
}
