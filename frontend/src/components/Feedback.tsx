import type { ReactNode } from "react";
import { cx } from "./cx";
import { AlertIcon, InfoIcon } from "./icons";

export function Spinner({
  className = "size-5",
  label,
}: {
  className?: string;
  label?: string;
}) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={cx("animate-spin", className)}
      role={label ? "status" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeOpacity="0.25"
        strokeWidth="3"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 py-8 text-sm text-muted" role="status">
      <Spinner className="size-4" />
      {label}
    </div>
  );
}

type NoticeTone = "info" | "warning" | "danger" | "success";

const noticeTones: Record<NoticeTone, string> = {
  info: "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950/50 dark:text-sky-200",
  warning:
    "border-amber-200 bg-amber-50 text-amber-950 dark:border-amber-900 dark:bg-amber-950/50 dark:text-amber-200",
  danger:
    "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/50 dark:text-red-200",
  success:
    "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/50 dark:text-emerald-200",
};

export function Notice({
  tone = "info",
  title,
  children,
  actions,
  className,
}: {
  tone?: NoticeTone;
  title?: ReactNode;
  children?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  const IconCmp = tone === "info" || tone === "success" ? InfoIcon : AlertIcon;
  return (
    <div
      role={tone === "danger" ? "alert" : undefined}
      className={cx(
        "flex gap-3 rounded-lg border px-4 py-3 text-sm",
        noticeTones[tone],
        className,
      )}
    >
      <IconCmp className="mt-0.5 size-4 shrink-0" />
      <div className="min-w-0 flex-1 space-y-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className="break-words">{children}</div>}
        {actions && <div className="flex flex-wrap gap-2 pt-1">{actions}</div>}
      </div>
    </div>
  );
}

export function ErrorNotice({
  error,
  title = "Something went wrong",
  onRetry,
}: {
  error: unknown;
  title?: string;
  onRetry?: () => void;
}) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Notice
      tone="danger"
      title={title}
      actions={
        onRetry && (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-md border border-current/30 px-2.5 py-1 text-xs font-medium hover:bg-current/10"
          >
            Try again
          </button>
        )
      }
    >
      {message}
    </Notice>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-line px-4 py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </div>
  );
}
