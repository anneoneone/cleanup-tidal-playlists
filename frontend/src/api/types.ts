import type { components } from "./schema";

type Schemas = components["schemas"];

export type StatusOut = Schemas["StatusOut"];
export type Check = Schemas["Check"];
export type RunOut = Schemas["RunOut"];
export type JobOut = Schemas["JobOut"];
export type JobStatus = JobOut["status"];
export type PlaylistOut = Schemas["PlaylistOut"];
export type PlaylistDetailOut = Schemas["PlaylistDetailOut"];
export type TrackOut = Schemas["TrackOut"];
export type ImportedTrackOut = Schemas["ImportedTrackOut"];
export type PlanOut = Schemas["PlanOut"];
export type Plan = Schemas["Plan"];
export type PlanGroup = Schemas["PlanGroup"];
export type Change = Schemas["Change"];
export type ChangeKind = Schemas["ChangeKind"];
export type SettingsOut = Schemas["SettingsOut"];
export type TidalLoginOut = Schemas["TidalLoginOut"];
export type BackupOut = Schemas["BackupOut"];
export type CancelOut = Schemas["CancelOut"];
export type SyncIn = Schemas["SyncIn"];
export type ApplyIn = Schemas["ApplyIn"];
export type PickPathIn = Schemas["PickPathIn"];
export type PickPathOut = Schemas["PickPathOut"];
export type PickField = PickPathIn["field"];
export type Source = PlaylistOut["sources"][number];

/** Kinds of job events sent over SSE. Not part of openapi.json (see schemas.py). */
export const JOB_EVENT_KINDS = [
  "started",
  "step",
  "progress",
  "log",
  "finished",
  "failed",
  "cancelled",
] as const;
export type JobEventKind = (typeof JOB_EVENT_KINDS)[number];
export const TERMINAL_EVENT_KINDS: ReadonlySet<JobEventKind> = new Set([
  "finished",
  "failed",
  "cancelled",
]);

/** One job event (the SSE `data` payload, `JobEventOut` on the server). */
export interface JobEvent {
  seq: number;
  job_id: string;
  kind: JobEventKind;
  message: string;
  step: string | null;
  current: number | null;
  total: number | null;
  level: string | null;
  time: number;
}

/** `JobOut.result` per job kind. */
export interface SyncJobResult {
  run_id: number;
  empty?: boolean;
}
export interface ApplyJobResult {
  run_id: number;
  applied: number;
  failed: number;
  backup: string;
}
export interface RestoreJobResult {
  backup: string;
}

/** One group result in an apply run's `summary.groups`. */
export interface ApplyGroupResult {
  key: string;
  title: string;
  /** "applied" or "failed". */
  status: string;
  error?: string | null;
  warning?: string | null;
  changes?: number;
}

export const TARGET_FORMATS = ["mp3", "flac", "m4a", "aiff", "wav"] as const;
export const DOWNLOAD_QUALITIES = ["LOW", "HIGH", "LOSSLESS", "HI_RES_LOSSLESS"] as const;

/** `SettingsOut.values` (typed by hand; the API sends a plain object). */
export interface SettingsValues {
  music_folder: string;
  bandcamp_folder: string | null;
  rekordbox_db: string | null;
  tag_mapping: string | null;
  target_format: (typeof TARGET_FORMATS)[number];
  ffmpeg_quality: number;
  download_quality: (typeof DOWNLOAD_QUALITIES)[number];
  prune_tracks: boolean;
  backups_keep_full: number;
  backups_keep_db: number;
  port: number;
}

/** The Playlist tag mapping file. Unknown keys must be kept as they are. */
export interface TagMapping {
  emoji_to_mytag_mapping: Record<string, Record<string, string>>;
  folder_structure: {
    genre_categories?: Record<string, string[]>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}
