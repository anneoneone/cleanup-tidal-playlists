import { useState } from "react";
import { useSaveTagMapping, useTagMapping } from "../api/queries";
import type { TagMapping } from "../api/types";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorNotice, Loading, Notice } from "../components/Feedback";
import { TextInput } from "../components/form";
import { PlusIcon, TrashIcon } from "../components/icons";
import {
  type CategoryRow,
  type EmojiGroup,
  fromDraft,
  newRowId,
  type TagMappingDraft,
  toDraft,
  uncategorizedGenres,
  validateDraft,
} from "./tagMapping";

export function TagMappingEditor({ fileInUse }: { fileInUse?: string }) {
  const mapping = useTagMapping();
  const save = useSaveTagMapping();
  return (
    <Card title="Playlist tag mapping">
      <p className="mb-4 text-sm text-muted">
        Each Playlist emoji stands for one Playlist tag. The Genre tags decide the Folder
        placement in Rekordbox.
        {fileInUse && (
          <>
            {" "}
            File: <span className="break-all">{fileInUse}</span>
          </>
        )}
      </p>
      {mapping.isPending && <Loading />}
      {mapping.isError && (
        <ErrorNotice
          error={mapping.error}
          title="Could not load the mapping"
          onRetry={() => void mapping.refetch()}
        />
      )}
      {mapping.data && (
        <Editor key={fileInUse ?? ""} original={mapping.data} save={save} />
      )}
    </Card>
  );
}

function Editor({
  original,
  save,
}: {
  original: TagMapping;
  save: ReturnType<typeof useSaveTagMapping>;
}) {
  const [draft, setDraft] = useState<TagMappingDraft>(() => toDraft(original));
  const [dirty, setDirty] = useState(false);
  // A refetch brings a new copy of the file: follow it, but never drop unsaved edits.
  const [base, setBase] = useState(original);
  if (original !== base) {
    setBase(original);
    if (!dirty) setDraft(toDraft(original));
  }
  const problems = validateDraft(draft);
  const uncategorized = uncategorizedGenres(draft);

  const change = (next: TagMappingDraft) => {
    setDraft(next);
    setDirty(true);
    save.reset();
  };

  const updateGroup = (index: number, group: EmojiGroup) =>
    change({ ...draft, groups: draft.groups.map((g, i) => (i === index ? group : g)) });

  const updateCategories = (categories: CategoryRow[]) =>
    change({ ...draft, categories });

  return (
    <form
      className="space-y-6"
      onSubmit={(event) => {
        event.preventDefault();
        if (problems.length > 0) return;
        save.mutate(fromDraft(original, draft), { onSuccess: () => setDirty(false) });
      }}
    >
      <div className="grid gap-6 lg:grid-cols-2">
        {draft.groups.map((group, index) => (
          <EmojiTable
            key={group.name}
            group={group}
            onChange={(g) => updateGroup(index, g)}
          />
        ))}
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-semibold">Genre categories</legend>
        <p className="text-xs text-muted">
          Each category is a folder under the Genre folder. List the Genre tags that go
          into it, separated by commas.
        </p>
        <ul className="space-y-2">
          {draft.categories.map((row, index) => (
            <li
              key={row.id}
              className="grid gap-2 sm:grid-cols-[12rem_1fr_auto] sm:items-center"
            >
              <TextInput
                aria-label={`Category ${index + 1} name`}
                value={row.name}
                placeholder="Category"
                onChange={(event) =>
                  updateCategories(
                    draft.categories.map((r) =>
                      r.id === row.id ? { ...r, name: event.target.value } : r,
                    ),
                  )
                }
              />
              <TextInput
                aria-label={`Genre tags in ${row.name || `category ${index + 1}`}`}
                value={row.genres}
                placeholder="House Deep, House Chill"
                onChange={(event) =>
                  updateCategories(
                    draft.categories.map((r) =>
                      r.id === row.id ? { ...r, genres: event.target.value } : r,
                    ),
                  )
                }
              />
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Remove category ${row.name || index + 1}`}
                onClick={() =>
                  updateCategories(draft.categories.filter((r) => r.id !== row.id))
                }
              >
                <TrashIcon />
              </Button>
            </li>
          ))}
        </ul>
        <Button
          size="sm"
          onClick={() =>
            updateCategories([
              ...draft.categories,
              { id: newRowId(), name: "", genres: "" },
            ])
          }
        >
          <PlusIcon /> Add category
        </Button>
        {uncategorized.length > 0 && (
          <p className="text-xs text-amber-700 dark:text-amber-300">
            Not in any category: {uncategorized.join(", ")}
          </p>
        )}
      </fieldset>

      <p className="text-xs text-muted">
        Other settings in the file are kept as they are.
      </p>

      {problems.length > 0 && (
        <Notice tone="warning" title="Fix these before saving">
          <ul className="list-disc pl-4">
            {problems.map((problem) => (
              <li key={problem}>{problem}</li>
            ))}
          </ul>
        </Notice>
      )}
      {save.error && (
        <ErrorNotice error={save.error} title="Could not save the mapping" />
      )}
      {save.isSuccess && (
        <Notice tone="success">Mapping saved. The next Plan uses it.</Notice>
      )}
      <div className="flex flex-wrap gap-2">
        <Button
          type="submit"
          variant="primary"
          disabled={!dirty || problems.length > 0}
          busy={save.isPending}
        >
          Save mapping
        </Button>
        <Button
          disabled={!dirty || save.isPending}
          onClick={() => {
            setDraft(toDraft(original));
            setDirty(false);
            save.reset();
          }}
        >
          Undo changes
        </Button>
      </div>
    </form>
  );
}

function EmojiTable({
  group,
  onChange,
}: {
  group: EmojiGroup;
  onChange: (group: EmojiGroup) => void;
}) {
  const setRow = (id: string, patch: { emoji?: string; value?: string }) =>
    onChange({
      ...group,
      rows: group.rows.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    });

  return (
    <fieldset className="space-y-2">
      <legend className="text-sm font-semibold">
        {group.name} <span className="font-normal text-muted">({group.rows.length})</span>
      </legend>
      <ul className="space-y-1.5">
        {group.rows.map((row, index) => (
          <li
            key={row.id}
            className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-2"
          >
            <TextInput
              aria-label={`${group.name} emoji ${index + 1}`}
              value={row.emoji}
              onChange={(event) => setRow(row.id, { emoji: event.target.value })}
              className="text-center text-base"
            />
            <TextInput
              aria-label={`${group.name} tag for ${row.emoji || `row ${index + 1}`}`}
              value={row.value}
              onChange={(event) => setRow(row.id, { value: event.target.value })}
            />
            <Button
              variant="ghost"
              size="sm"
              aria-label={`Remove ${row.emoji || "row"} from ${group.name}`}
              onClick={() =>
                onChange({ ...group, rows: group.rows.filter((r) => r.id !== row.id) })
              }
            >
              <TrashIcon />
            </Button>
          </li>
        ))}
      </ul>
      <Button
        size="sm"
        onClick={() =>
          onChange({
            ...group,
            rows: [...group.rows, { id: newRowId(), emoji: "", value: "" }],
          })
        }
      >
        <PlusIcon /> Add emoji
      </Button>
    </fieldset>
  );
}
