import { useState } from "react";
import { usePickPath } from "../api/queries";
import type { PickField } from "../api/types";
import { Button } from "../components/Button";
import { TextInput } from "../components/form";

/** What `Field` passes to its control. */
interface FieldProps {
  id: string;
  "aria-describedby"?: string;
  "aria-invalid"?: boolean;
}

/**
 * A path input with a "Choose…" button. A browser cannot give the page an
 * absolute path, so the server opens the Finder dialog on this Mac. The chosen
 * path only fills the input; the user still saves the form.
 */
export function PathInput({
  field,
  label,
  value,
  placeholder,
  onChange,
  ...fieldProps
}: FieldProps & {
  field: PickField;
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  const pick = usePickPath();
  const [error, setError] = useState<string | null>(null);

  const choose = () => {
    setError(null);
    pick.mutate(
      { field, start: value.trim() || null },
      {
        onSuccess: (path) => {
          if (path) onChange(path);
        },
        onError: (err) => setError(err instanceof Error ? err.message : String(err)),
      },
    );
  };

  return (
    <div className="space-y-1.5">
      <div className="flex gap-2">
        <TextInput
          {...fieldProps}
          value={value}
          placeholder={placeholder}
          onChange={(event) => {
            setError(null);
            onChange(event.target.value);
          }}
          autoComplete="off"
          spellCheck={false}
        />
        <Button
          onClick={choose}
          busy={pick.isPending}
          aria-label={`Choose ${label}`}
          title="Opens the Finder dialog on this Mac"
          className="shrink-0"
        >
          Choose…
        </Button>
      </div>
      {pick.isPending && (
        <p role="status" className="text-xs text-muted">
          Pick it in the Finder dialog. It may open behind this window.
        </p>
      )}
      {error && (
        <p role="alert" className="text-xs font-medium text-red-600 dark:text-red-400">
          {error}
        </p>
      )}
    </div>
  );
}
