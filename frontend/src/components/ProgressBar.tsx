import { cx } from "./cx";

/** A progress bar; without `total` it shows an indeterminate animation. */
export function ProgressBar({
  current,
  total,
  label,
  tone = "accent",
}: {
  current?: number | null;
  total?: number | null;
  label: string;
  tone?: "accent" | "red" | "amber" | "green";
}) {
  const known = typeof total === "number" && total > 0 && typeof current === "number";
  const percent = known ? Math.min(100, Math.round((current / total) * 100)) : 0;
  const color = {
    accent: "bg-accent",
    red: "bg-red-500",
    amber: "bg-amber-500",
    green: "bg-emerald-500",
  }[tone];
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={known ? 0 : undefined}
      aria-valuemax={known ? total : undefined}
      aria-valuenow={known ? current : undefined}
      className="h-1.5 w-full overflow-hidden rounded-full bg-surface-2"
    >
      {known ? (
        <div
          className={cx("h-full rounded-full transition-[width] duration-300", color)}
          style={{ width: `${percent}%` }}
        />
      ) : (
        <div className={cx("animate-indeterminate h-full w-2/5 rounded-full", color)} />
      )}
    </div>
  );
}
