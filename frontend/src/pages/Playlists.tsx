import { Link, useNavigate, useSearchParams } from "react-router";
import { usePlaylists } from "../api/queries";
import type { PlaylistOut } from "../api/types";
import { Badge, SourceBadges } from "../components/Badge";
import { cx } from "../components/cx";
import { EmptyState, ErrorNotice, Loading } from "../components/Feedback";
import { Select, TextInput } from "../components/form";
import { PageHeader } from "../components/PageHeader";
import { SortHeader } from "../components/SortHeader";
import { folderPath, formatCount } from "../lib/format";
import {
  filterAndSort,
  type GoneFilter,
  isSortKey,
  type PlaylistFilter,
  type SortDir,
  type SortKey,
  type SourceFilter,
} from "../playlists/filter";

const SOURCES: { value: SourceFilter; label: string }[] = [
  { value: "all", label: "All Sources" },
  { value: "tidal", label: "Tidal" },
  { value: "bandcamp", label: "Bandcamp" },
  { value: "library", label: "Library" },
];

const GONE: { value: GoneFilter; label: string }[] = [
  { value: "all", label: "Active and gone" },
  { value: "active", label: "Active only" },
  { value: "gone", label: "Gone only" },
];

function readFilter(params: URLSearchParams): PlaylistFilter {
  const source = params.get("source");
  const gone = params.get("gone");
  return {
    query: params.get("q") ?? "",
    source: SOURCES.some((s) => s.value === source) ? (source as SourceFilter) : "all",
    gone: GONE.some((g) => g.value === gone) ? (gone as GoneFilter) : "all",
    notInRekordbox: params.get("nrb") === "1",
  };
}

export default function Playlists() {
  const playlists = usePlaylists();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const filter = readFilter(params);
  const sortParam = params.get("sort");
  const sort: SortKey = isSortKey(sortParam) ? sortParam : "name";
  const dir: SortDir = params.get("dir") === "desc" ? "desc" : "asc";

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next, { replace: true });
  };

  const rows = filterAndSort(playlists.data ?? [], filter, sort, dir);

  const sortBy = (key: SortKey) => {
    const firstDir: SortDir = key === "name" || key === "folder" ? "asc" : "desc";
    const nextDir: SortDir = sort === key ? (dir === "asc" ? "desc" : "asc") : firstDir;
    update({ sort: key === "name" ? null : key, dir: nextDir === "asc" ? null : "desc" });
  };

  return (
    <>
      <PageHeader
        title="Playlists"
        description="Every Playlist from Tidal, Bandcamp and the Music folder."
      />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_auto_auto_auto] lg:items-end">
        <div className="sm:col-span-2 lg:col-span-1">
          <label htmlFor="playlist-search" className="sr-only">
            Search playlists
          </label>
          <TextInput
            id="playlist-search"
            type="search"
            placeholder="Search name or folder"
            value={filter.query}
            onChange={(event) => update({ q: event.target.value })}
          />
        </div>
        <div>
          <label htmlFor="playlist-source" className="sr-only">
            Source
          </label>
          <Select
            id="playlist-source"
            value={filter.source}
            onChange={(event) =>
              update({ source: event.target.value === "all" ? null : event.target.value })
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
          <label htmlFor="playlist-gone" className="sr-only">
            Gone playlists
          </label>
          <Select
            id="playlist-gone"
            value={filter.gone}
            onChange={(event) =>
              update({ gone: event.target.value === "all" ? null : event.target.value })
            }
          >
            {GONE.map((g) => (
              <option key={g.value} value={g.value}>
                {g.label}
              </option>
            ))}
          </Select>
        </div>
        <label className="flex h-10 items-center gap-2 text-sm whitespace-nowrap">
          <input
            type="checkbox"
            checked={filter.notInRekordbox}
            onChange={(event) => update({ nrb: event.target.checked ? "1" : null })}
            className="size-4 accent-accent"
          />
          Not in Rekordbox
        </label>
      </div>

      {playlists.isPending && <Loading />}
      {playlists.isError && (
        <ErrorNotice
          error={playlists.error}
          title="Could not load the playlists"
          onRetry={() => void playlists.refetch()}
        />
      )}
      {playlists.data && playlists.data.length === 0 && (
        <EmptyState title="No playlists yet">Run a sync to read your Sources.</EmptyState>
      )}
      {playlists.data && playlists.data.length > 0 && (
        <>
          <p className="mb-2 text-xs text-muted" aria-live="polite">
            {rows.length === playlists.data.length
              ? `${formatCount(rows.length)} playlists`
              : `${formatCount(rows.length)} of ${formatCount(playlists.data.length)} playlists`}
          </p>
          {rows.length === 0 ? (
            <EmptyState title="No playlist matches the filters" />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-line bg-surface">
              <table className="w-full min-w-[60rem] text-sm">
                <thead className="border-b border-line bg-surface-2 text-left text-xs text-muted">
                  <tr>
                    <SortHeader
                      label="Name"
                      column="name"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                    />
                    <th scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                      Sources
                    </th>
                    <SortHeader
                      label="Folder placement"
                      column="folder"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                    />
                    <th scope="col" className="px-3 py-2 font-medium whitespace-nowrap">
                      Rekordbox name
                    </th>
                    <SortHeader
                      label="Tidal"
                      column="tracks_tidal"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                      numeric
                    />
                    <SortHeader
                      label="With file"
                      column="tracks_with_file"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                      numeric
                    />
                    <SortHeader
                      label="Without file"
                      column="tracks_without_file"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                      numeric
                    />
                    <SortHeader
                      label="In Rekordbox"
                      column="tracks_in_rekordbox"
                      sort={sort}
                      dir={dir}
                      onSort={sortBy}
                      numeric
                    />
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {rows.map((playlist) => (
                    <PlaylistRow
                      key={playlist.id}
                      playlist={playlist}
                      onOpen={() => void navigate(`/playlists/${playlist.id}`)}
                    />
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

function PlaylistRow({
  playlist,
  onOpen,
}: {
  playlist: PlaylistOut;
  onOpen: () => void;
}) {
  return (
    <tr onClick={onOpen} className="cursor-pointer hover:bg-surface-2/70">
      <td className="min-w-56 px-3 py-2.5">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/playlists/${playlist.id}`}
            onClick={(event) => event.stopPropagation()}
            className="font-medium break-words hover:underline"
          >
            {playlist.name}
          </Link>
          {playlist.gone && <Badge tone="amber">gone</Badge>}
        </div>
      </td>
      <td className="px-3 py-2.5">
        <SourceBadges sources={playlist.sources} />
      </td>
      <td className="min-w-44 px-3 py-2.5 text-muted">{folderPath(playlist.folder)}</td>
      <td className="px-3 py-2.5">
        {playlist.in_rekordbox ? (
          playlist.rekordbox_name
        ) : (
          <span className="text-muted">
            {playlist.rekordbox_name} <Badge>not in Rekordbox</Badge>
          </span>
        )}
      </td>
      <td className="tabular px-3 py-2.5 text-right">
        {formatCount(playlist.tracks_tidal)}
      </td>
      <td className="tabular px-3 py-2.5 text-right">
        {formatCount(playlist.tracks_with_file)}
      </td>
      <td
        className={cx(
          "tabular px-3 py-2.5 text-right",
          playlist.tracks_without_file > 0 &&
            "font-medium text-amber-700 dark:text-amber-300",
        )}
      >
        {formatCount(playlist.tracks_without_file)}
      </td>
      <td className="tabular px-3 py-2.5 text-right">
        {formatCount(playlist.tracks_in_rekordbox)}
      </td>
    </tr>
  );
}
