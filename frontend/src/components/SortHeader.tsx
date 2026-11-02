import { cx } from "./cx";
import { ArrowUpDownIcon, ChevronIcon } from "./icons";

export type SortDir = "asc" | "desc";

/** A table header that sorts by its column when clicked. */
export function SortHeader<K extends string>({
  label,
  column,
  sort,
  dir,
  onSort,
  numeric = false,
}: {
  label: string;
  column: K;
  sort: K;
  dir: SortDir;
  onSort: (key: K) => void;
  numeric?: boolean;
}) {
  const active = sort === column;
  return (
    <th
      scope="col"
      aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}
      className={cx("px-3 py-2 font-medium whitespace-nowrap", numeric && "text-right")}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={cx(
          "inline-flex items-center gap-1 rounded hover:text-fg",
          active && "text-fg",
        )}
      >
        {label}
        {active ? (
          <ChevronIcon
            className={cx("size-3.5", dir === "asc" ? "-rotate-90" : "rotate-90")}
          />
        ) : (
          <ArrowUpDownIcon className="size-3.5 opacity-50" />
        )}
      </button>
    </th>
  );
}
