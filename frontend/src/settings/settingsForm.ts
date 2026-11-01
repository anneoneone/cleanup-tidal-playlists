import type { FieldError } from "../api/client";
import { DOWNLOAD_QUALITIES, TARGET_FORMATS } from "../api/types";

/** Form state: every value as the input shows it. */
export interface SettingsForm {
  music_folder: string;
  bandcamp_folder: string;
  rekordbox_db: string;
  tag_mapping: string;
  target_format: string;
  ffmpeg_quality: string;
  download_quality: string;
  prune_tracks: boolean;
  backups_keep_full: string;
  backups_keep_db: string;
  port: string;
}

export type SettingsField = keyof SettingsForm;
export type SettingsErrors = Partial<Record<SettingsField | "_form", string>>;

const TEXT_FIELDS = [
  "music_folder",
  "bandcamp_folder",
  "rekordbox_db",
  "tag_mapping",
] as const;
const OPTIONAL_TEXT = new Set<SettingsField>([
  "bandcamp_folder",
  "rekordbox_db",
  "tag_mapping",
]);
const NUMBER_FIELDS = [
  "ffmpeg_quality",
  "backups_keep_full",
  "backups_keep_db",
  "port",
] as const;

function text(value: unknown, fallback = ""): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

/** Build the form state from `SettingsOut.values`. */
export function toForm(values: Record<string, unknown>): SettingsForm {
  return {
    music_folder: text(values.music_folder),
    bandcamp_folder: text(values.bandcamp_folder),
    rekordbox_db: text(values.rekordbox_db),
    tag_mapping: text(values.tag_mapping),
    target_format: text(values.target_format, TARGET_FORMATS[0]),
    ffmpeg_quality: text(values.ffmpeg_quality, "2"),
    download_quality: text(values.download_quality, "LOSSLESS"),
    prune_tracks: values.prune_tracks !== false,
    backups_keep_full: text(values.backups_keep_full, "20"),
    backups_keep_db: text(values.backups_keep_db, "10"),
    port: text(values.port, "8765"),
  };
}

/**
 * Turn the form into the PUT body. Empty optional fields become null (the
 * server then leaves them out). Returns errors for values that are not numbers.
 */
export function toPayload(form: SettingsForm): {
  values: Record<string, unknown>;
  errors: SettingsErrors;
} {
  const errors: SettingsErrors = {};
  const values: Record<string, unknown> = {};
  for (const field of TEXT_FIELDS) {
    const value = form[field].trim();
    if (!value && !OPTIONAL_TEXT.has(field)) errors[field] = "Required";
    values[field] = value || null;
  }
  for (const field of NUMBER_FIELDS) {
    const raw = form[field].trim();
    if (!/^-?\d+$/.test(raw)) {
      errors[field] = raw ? "Enter a whole number" : "Required";
      continue;
    }
    values[field] = Number(raw);
  }
  values.target_format = form.target_format;
  values.download_quality = form.download_quality;
  values.prune_tracks = form.prune_tracks;
  if (!(TARGET_FORMATS as readonly string[]).includes(form.target_format)) {
    errors.target_format = "Choose a format";
  }
  if (!(DOWNLOAD_QUALITIES as readonly string[]).includes(form.download_quality)) {
    errors.download_quality = "Choose a quality";
  }
  return { values, errors };
}

/** Map server validation errors to form fields; the rest goes to `_form`. */
export function errorsFromServer(
  fieldErrors: FieldError[],
  fallback: string,
): SettingsErrors {
  const errors: SettingsErrors = {};
  const rest: string[] = [];
  for (const error of fieldErrors) {
    if (error.field && error.field in toForm({})) {
      const field = error.field as SettingsField;
      errors[field] = errors[field]
        ? `${errors[field]}; ${error.message}`
        : error.message;
    } else {
      rest.push(error.field ? `${error.field}: ${error.message}` : error.message);
    }
  }
  if (rest.length > 0) errors._form = rest.join("; ");
  if (fieldErrors.length === 0) errors._form = fallback;
  return errors;
}
