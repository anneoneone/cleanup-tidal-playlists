import { type FormEvent, useState } from "react";
import { isApiError } from "../api/client";
import { useSaveSettings, useSettings } from "../api/queries";
import { DOWNLOAD_QUALITIES, type SettingsOut, TARGET_FORMATS } from "../api/types";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorNotice, Loading, Notice } from "../components/Feedback";
import { Field, Select, TextInput, Toggle } from "../components/form";
import { PageHeader } from "../components/PageHeader";
import {
  errorsFromServer,
  type SettingsErrors,
  type SettingsField,
  type SettingsForm,
  toForm,
  toPayload,
} from "../settings/settingsForm";
import { TagMappingEditor } from "../settings/TagMappingEditor";
import { TidalLoginCard } from "../settings/TidalLoginCard";

export default function Settings() {
  const settings = useSettings();
  return (
    <>
      <PageHeader
        title="Settings"
        description="Folders, downloads, backups and the Playlist tag mapping."
      />
      <div className="space-y-6">
        {settings.isPending && <Loading />}
        {settings.isError && (
          <ErrorNotice
            error={settings.error}
            title="Could not load the settings"
            onRetry={() => void settings.refetch()}
          />
        )}
        {settings.data && <SettingsEditor data={settings.data} />}
        <TidalLoginCard />
        <TagMappingEditor fileInUse={settings.data?.tag_mapping_in_use} />
      </div>
    </>
  );
}

function SettingsEditor({ data }: { data: SettingsOut }) {
  const [form, setForm] = useState<SettingsForm>(() => toForm(data.values));
  const [errors, setErrors] = useState<SettingsErrors>({});
  const [saved, setSaved] = useState(false);
  const save = useSaveSettings();

  const set = <K extends SettingsField>(field: K, value: SettingsForm[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: undefined, _form: undefined }));
    setSaved(false);
  };

  const hasFieldErrors = Object.entries(errors).some(
    ([key, value]) => key !== "_form" && Boolean(value),
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const { values, errors: localErrors } = toPayload(form);
    if (Object.keys(localErrors).length > 0) {
      setErrors(localErrors);
      return;
    }
    save.mutate(values, {
      onSuccess: (result) => {
        setForm(toForm(result.values));
        setSaved(true);
      },
      onError: (error) => {
        setErrors(
          isApiError(error, 422)
            ? errorsFromServer(error.fieldErrors, error.message)
            : { _form: error instanceof Error ? error.message : String(error) },
        );
      },
    });
  };

  const text = (
    field: SettingsField,
    label: string,
    hint?: string,
    placeholder?: string,
  ) => (
    <Field label={label} hint={hint} error={errors[field]}>
      {(props) => (
        <TextInput
          {...props}
          value={String(form[field])}
          placeholder={placeholder}
          onChange={(event) => set(field, event.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
      )}
    </Field>
  );

  const number = (
    field: SettingsField,
    label: string,
    hint: string,
    min: number,
    max?: number,
  ) => (
    <Field label={label} hint={hint} error={errors[field]}>
      {(props) => (
        <TextInput
          {...props}
          type="number"
          inputMode="numeric"
          min={min}
          max={max}
          value={String(form[field])}
          onChange={(event) => set(field, event.target.value)}
          className="max-w-40"
        />
      )}
    </Field>
  );

  return (
    <form onSubmit={submit} noValidate className="space-y-6">
      <Card title="Files">
        <div className="grid gap-5 md:grid-cols-2">
          {text(
            "music_folder",
            "Music folder",
            "Audio files for Tidal tracks, one sub-folder per Playlist.",
          )}
          {text(
            "bandcamp_folder",
            "Bandcamp folder",
            "Optional. One sub-folder per Playlist.",
            "Not used",
          )}
          {text(
            "rekordbox_db",
            "Rekordbox library",
            "Optional. Path to master.db.",
            "Find it automatically",
          )}
          {text(
            "tag_mapping",
            "Playlist tag mapping file",
            "Optional. A JSON file.",
            "Use the default mapping",
          )}
        </div>
        <dl className="mt-5 grid gap-3 border-t border-line pt-4 text-xs sm:grid-cols-2">
          <div>
            <dt className="text-muted">Settings file</dt>
            <dd className="break-all">{data.config_file}</dd>
          </div>
          <div>
            <dt className="text-muted">Tag mapping in use</dt>
            <dd className="break-all">{data.tag_mapping_in_use}</dd>
          </div>
        </dl>
      </Card>

      <Card title="Downloads">
        <div className="grid gap-5 md:grid-cols-3">
          <Field label="Download quality" error={errors.download_quality}>
            {(props) => (
              <Select
                {...props}
                value={form.download_quality}
                onChange={(e) => set("download_quality", e.target.value)}
              >
                {DOWNLOAD_QUALITIES.map((q) => (
                  <option key={q} value={q}>
                    {q}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field
            label="File format"
            hint="Downloads are converted to this format."
            error={errors.target_format}
          >
            {(props) => (
              <Select
                {...props}
                value={form.target_format}
                onChange={(e) => set("target_format", e.target.value)}
              >
                {TARGET_FORMATS.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          {number("ffmpeg_quality", "ffmpeg quality", "0 (best) to 9.", 0, 9)}
        </div>
      </Card>

      <Card title="Rekordbox and Backups">
        <div className="space-y-5">
          <Toggle
            label="Remove tracks from Rekordbox playlists"
            hint="When a Track leaves a Playlist, the Plan removes it from the Rekordbox playlist too."
            checked={form.prune_tracks}
            onChange={(checked) => set("prune_tracks", checked)}
          />
          <div className="grid gap-5 md:grid-cols-3">
            {number(
              "backups_keep_full",
              "Full Backups to keep",
              "With the Rekordbox library.",
              1,
            )}
            {number(
              "backups_keep_db",
              "Database Backups to keep",
              "Cratekeeper database only.",
              1,
            )}
            {number(
              "port",
              "Server port",
              "Used the next time you start the UI.",
              1024,
              65535,
            )}
          </div>
        </div>
      </Card>

      {(errors._form || hasFieldErrors) && (
        <Notice tone="danger" title="Could not save the settings">
          {errors._form ?? "Some values are not valid. See the marked fields."}
        </Notice>
      )}
      {saved && <Notice tone="success">Settings saved.</Notice>}
      <Button type="submit" variant="primary" busy={save.isPending}>
        Save settings
      </Button>
    </form>
  );
}
