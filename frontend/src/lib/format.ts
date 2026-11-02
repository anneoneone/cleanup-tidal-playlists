import {
  differenceInSeconds,
  format,
  formatDistanceToNowStrict,
  fromUnixTime,
  isValid,
  parseISO,
} from "date-fns";

const HAS_ZONE = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;

/**
 * Parse a server datetime. The database stores UTC without a zone, so a value
 * without a zone is read as UTC.
 */
export function parseUtc(value: string): Date {
  return parseISO(HAS_ZONE.test(value) ? value : `${value}Z`);
}

/** Convert a job timestamp (seconds since the epoch) to a Date. */
export function fromEpochSeconds(seconds: number): Date {
  return fromUnixTime(seconds);
}

export function formatDateTime(date: Date | null | undefined): string {
  if (!date || !isValid(date)) return "–";
  return format(date, "d MMM yyyy, HH:mm");
}

export function formatDate(date: Date | null | undefined): string {
  if (!date || !isValid(date)) return "–";
  return format(date, "d MMM yyyy");
}

export function formatRelative(date: Date | null | undefined): string {
  if (!date || !isValid(date)) return "–";
  return formatDistanceToNowStrict(date, { addSuffix: true });
}

/** Format a number of seconds as "45 s", "3 min 05 s" or "1 h 02 min". */
export function formatSeconds(total: number): string {
  const seconds = Math.max(0, Math.round(total));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ${String(seconds % 60).padStart(2, "0")} s`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ${String(minutes % 60).padStart(2, "0")} min`;
}

export function formatDuration(start: Date, end: Date | null | undefined): string {
  if (!end || !isValid(start) || !isValid(end)) return "–";
  return formatSeconds(differenceInSeconds(end, start));
}

const SIZE_UNITS = ["B", "KB", "MB", "GB", "TB"];

export function formatBytes(bytes: number): string {
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < SIZE_UNITS.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || value >= 100 ? 0 : 1;
  return `${value.toFixed(digits)} ${SIZE_UNITS[unit]}`;
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en").format(value);
}

/** "Genre / Techno" for a Rekordbox folder path. */
export function folderPath(folder: readonly string[] | null | undefined): string {
  return folder && folder.length > 0 ? folder.join(" / ") : "Top level";
}

/** "tidal_tracks" -> "Tidal tracks". */
export function labelize(key: string): string {
  const text = key.replace(/_/g, " ").trim();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${formatCount(count)} ${count === 1 ? one : many}`;
}
