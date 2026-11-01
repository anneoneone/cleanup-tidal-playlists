import type { ChangeKind } from "../api/types";
import { Badge, type Tone } from "../components/Badge";

const kinds: Record<ChangeKind, { short: string; long: string; tone: Tone }> = {
  create_playlist: { short: "create", long: "Create playlist", tone: "green" },
  rename_playlist: { short: "rename", long: "Rename playlist", tone: "blue" },
  move_playlist: { short: "move", long: "Move playlist", tone: "blue" },
  import_track: {
    short: "import",
    long: "Import file into the collection",
    tone: "violet",
  },
  add_track: { short: "add", long: "Add track", tone: "green" },
  remove_track: { short: "remove", long: "Remove track", tone: "amber" },
  set_genre: { short: "genre", long: "Set genre", tone: "neutral" },
  delete_playlist: { short: "delete", long: "Delete playlist", tone: "red" },
};

function info(kind: ChangeKind) {
  return kinds[kind] ?? { short: kind, long: kind, tone: "neutral" };
}

export function changeKindLabel(kind: ChangeKind): string {
  return info(kind).long;
}

/** "12 add" style badge for a change count. */
export function KindCountBadge({ kind, count }: { kind: ChangeKind; count: number }) {
  const { short, long, tone } = info(kind);
  return (
    <Badge tone={tone} title={`${long}: ${count}`}>
      <span className="tabular">{count}</span> {short}
    </Badge>
  );
}

export function KindBadge({ kind }: { kind: ChangeKind }) {
  const { short, long, tone } = info(kind);
  return (
    <Badge tone={tone} title={long} className="w-16 justify-center">
      {short}
    </Badge>
  );
}
