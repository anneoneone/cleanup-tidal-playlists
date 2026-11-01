import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PlanOut } from "../api/types";
import { makeChange, makeGroup, makePlan } from "../test/planFactory";
import { PlanReview } from "./PlanReview";

const planOut: PlanOut = {
  run_id: 7,
  applied_by_run: null,
  plan: makePlan({
    fingerprint: "abc",
    rekordbox_db: "/demo/master.db",
    unchanged_playlists: 3,
    new_folders: ["Genre/Techno"],
    warnings: ["Track file missing: x.mp3"],
    groups: [
      makeGroup({
        key: "p1",
        title: "Peak Time 🏢⬆️",
        target_name: "Peak Time ⬆️",
        folder: ["Genre", "Techno"],
        changes: [
          makeChange("create_playlist", "Create playlist Peak Time ⬆️"),
          makeChange("add_track", "Add Rødhåd – Target"),
        ],
      }),
      makeGroup({
        key: "p2",
        title: "Deep Nights 🌃",
        folder: ["Genre", "Deep House"],
        changes: [makeChange("add_track", "Add Moodymann – Shades")],
      }),
      makeGroup({ key: "p3", title: "Quiet" }),
      makeGroup({
        key: "delete",
        title: "Delete playlists",
        selected_by_default: false,
        changes: [makeChange("delete_playlist", "Delete Old Stuff")],
      }),
    ],
  }),
};

const status = {
  version: "2.0.0",
  home: "/demo",
  checks: [{ key: "rekordbox_app", label: "Rekordbox app", ok: null, detail: "closed" }],
  counts: {},
  v1_import_available: false,
};

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener() {}
  close() {}
}

let fetchMock: ReturnType<typeof vi.fn>;

function respond(plan: PlanOut) {
  fetchMock = vi.fn((input: string, init?: RequestInit) => {
    const url = input;
    const json = (body: unknown, code = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status: code }));
    if (url === "/api/plans/7" && !init?.method?.match(/POST/)) return json(plan);
    if (url === "/api/plans/7/apply") {
      return json(
        {
          id: "job9",
          kind: "apply",
          label: "Apply",
          status: "running",
          started_at: 1,
          last_seq: 0,
        },
        202,
      );
    }
    if (url === "/api/status") return json(status);
    if (url === "/api/jobs/job9") {
      return json({
        id: "job9",
        kind: "apply",
        label: "Apply",
        status: "running",
        started_at: 1,
        last_seq: 0,
      });
    }
    return json({ detail: "Not found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
}

function renderPlan(): void {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  render(<PlanReview runId={7} />, { wrapper });
}

beforeEach(() => {
  FakeEventSource.instances = [];
  vi.stubGlobal("EventSource", FakeEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PlanReview", () => {
  it("shows groups with changes and keeps the delete group unchecked", async () => {
    respond(planOut);
    renderPlan();
    const peak = await screen.findByLabelText("Peak Time 🏢⬆️");
    expect(peak).toBeChecked();
    expect(screen.getByLabelText("Deep Nights 🌃")).toBeChecked();
    expect(screen.queryByLabelText("Quiet")).not.toBeInTheDocument();
    const del = screen.getByLabelText("Delete playlists");
    expect(del).not.toBeChecked();
    expect(screen.getByText("Deletes playlists in Rekordbox")).toBeInTheDocument();
    expect(screen.getByText("Track file missing: x.mp3")).toBeInTheDocument();
    expect(screen.getByText("Genre/Techno")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Apply 2 groups" })).toBeEnabled();
  });

  it("updates the count, confirms in the page and posts the selected groups", async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.fn(() => true);
    vi.stubGlobal("confirm", confirmSpy);
    respond(planOut);
    renderPlan();
    await user.click(await screen.findByLabelText("Deep Nights 🌃"));
    await user.click(screen.getByLabelText("Delete playlists"));
    await user.click(screen.getByRole("button", { name: "Apply 2 groups" }));

    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
    expect(screen.getByLabelText("Peak Time 🏢⬆️")).toBeDisabled();
    expect(
      within(dialog).getByText(/A Backup of the Rekordbox library/),
    ).toBeInTheDocument();
    expect(
      within(dialog).getByText("This also deletes 1 playlist in Rekordbox."),
    ).toBeInTheDocument();
    // The confirm button only reacts a moment after the panel opened.
    await new Promise((resolve) => setTimeout(resolve, 450));
    await user.click(within(dialog).getByRole("button", { name: "Apply now" }));

    await waitFor(() =>
      expect(FakeEventSource.instances[0]?.url).toBe("/api/jobs/job9/events?after=0"),
    );
    const call = fetchMock.mock.calls.find(([url]) => url === "/api/plans/7/apply");
    const init = call?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toEqual({ groups: ["p1", "delete"] });
    expect((init.headers as Record<string, string>)["X-Cratekeeper"]).toBe("1");
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it("returns focus to the Apply button after Cancel", async () => {
    const user = userEvent.setup();
    respond(planOut);
    renderPlan();
    await user.click(await screen.findByRole("button", { name: "Apply 2 groups" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Apply 2 groups" })).toHaveFocus(),
    );
    expect(screen.getByLabelText("Peak Time 🏢⬆️")).toBeEnabled();
  });

  it("disables Apply when a newer Plan exists", async () => {
    respond({ ...planOut, superseded_by: 9 });
    renderPlan();
    expect(await screen.findByText("A newer Plan exists")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Run 9" })).toHaveAttribute(
      "href",
      "/plans/9",
    );
    expect(screen.getByRole("button", { name: "Apply 2 groups" })).toBeDisabled();
    expect(screen.getByText("Replaced by the Plan of run 9")).toBeInTheDocument();
  });

  it("selects all except the delete group, and none", async () => {
    const user = userEvent.setup();
    respond(planOut);
    renderPlan();
    await user.click(await screen.findByRole("button", { name: "Select none" }));
    expect(screen.getByRole("button", { name: "Apply 0 groups" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Select all" }));
    expect(screen.getByLabelText("Delete playlists")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Apply 2 groups" })).toBeEnabled();
  });

  it("says Rekordbox is up to date for an empty Plan", async () => {
    respond({
      ...planOut,
      plan: { ...planOut.plan, groups: [planOut.plan.groups[2]!], warnings: [] },
    });
    renderPlan();
    expect(await screen.findByText("Rekordbox is up to date")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Apply/ })).not.toBeInTheDocument();
  });

  it("disables Apply when the Plan was applied already", async () => {
    respond({ ...planOut, applied_by_run: 8 });
    renderPlan();
    expect(await screen.findByText("This Plan was applied")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "run 8" })).toHaveAttribute(
      "href",
      "/history/8",
    );
    expect(screen.getByRole("button", { name: "Apply 2 groups" })).toBeDisabled();
    expect(screen.getByText("Already applied in run 8")).toBeInTheDocument();
    expect(screen.getByLabelText("Peak Time 🏢⬆️")).toBeDisabled();
  });
});
