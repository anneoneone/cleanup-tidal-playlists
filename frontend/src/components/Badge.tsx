import type { ReactNode } from "react";
import { cx } from "./cx";

export type Tone = "neutral" | "accent" | "green" | "red" | "amber" | "blue" | "violet";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-2 text-muted ring-line",
  accent: "bg-accent-soft text-accent ring-accent/25",
  green:
    "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-950/60 dark:text-emerald-300 dark:ring-emerald-400/25",
  red: "bg-red-50 text-red-800 ring-red-600/20 dark:bg-red-950/60 dark:text-red-300 dark:ring-red-400/25",
  amber:
    "bg-amber-50 text-amber-900 ring-amber-600/25 dark:bg-amber-950/60 dark:text-amber-300 dark:ring-amber-400/25",
  blue: "bg-sky-50 text-sky-800 ring-sky-600/20 dark:bg-sky-950/60 dark:text-sky-300 dark:ring-sky-400/25",
  violet:
    "bg-violet-50 text-violet-800 ring-violet-600/20 dark:bg-violet-950/60 dark:text-violet-300 dark:ring-violet-400/25",
};

export function Badge({
  tone = "neutral",
  className,
  title,
  children,
}: {
  tone?: Tone;
  className?: string;
  title?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

const statusTones: Record<string, Tone> = {
  running: "blue",
  succeeded: "green",
  applied: "green",
  failed: "red",
  cancelled: "amber",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge tone={statusTones[status] ?? "neutral"}>{status}</Badge>;
}

const sourceLabels: Record<string, string> = {
  tidal: "Tidal",
  bandcamp: "Bandcamp",
  library: "Library",
};
const sourceTones: Record<string, Tone> = {
  tidal: "blue",
  bandcamp: "violet",
  library: "neutral",
};

export function SourceBadge({ source }: { source: string }) {
  return (
    <Badge tone={sourceTones[source] ?? "neutral"}>
      {sourceLabels[source] ?? source}
    </Badge>
  );
}

export function SourceBadges({ sources }: { sources: readonly string[] }) {
  if (sources.length === 0) return <span className="text-muted">–</span>;
  return (
    <span className="flex flex-wrap gap-1">
      {sources.map((source) => (
        <SourceBadge key={source} source={source} />
      ))}
    </span>
  );
}
