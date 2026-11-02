import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useImportFiles } from "../api/queries";
import type { JobOut } from "../api/types";
import { ImportButton, ImportResults } from "./ImportTracks";

function Harness() {
  const importer = useImportFiles(5);
  return (
    <>
      <ImportButton importer={importer} />
      <ImportResults importer={importer} />
    </>
  );
}

function json(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function setup(currentJob: JobOut | null = null) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url === "/api/jobs/current") return json(currentJob);
    if (url.startsWith("/api/playlists/5/files") && init?.method === "POST") {
      return url.endsWith("name=dupe.mp3")
        ? json({ detail: "dupe.mp3 is already in the folder Playlists/Peak" }, 409)
        : json(
            { track_id: 9, file_path: "Playlists/Peak/new.mp3", library_track: true },
            201,
          );
    }
    return json({});
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  render(<Harness />, { wrapper });
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Import tracks", () => {
  it("uploads the chosen files and lists what happened to each", async () => {
    const user = userEvent.setup();
    const fetchMock = setup();
    const files = [new File(["a"], "new.mp3"), new File(["b"], "dupe.mp3")];

    await user.upload(screen.getByLabelText("Audio files to import"), files);

    expect(await screen.findByText("Imported 1 of 2 files")).toBeInTheDocument();
    expect(screen.getByText(/added as a Library track/)).toBeInTheDocument();
    expect(screen.getByText(/already in the folder Playlists\/Peak/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to Sync" })).toHaveAttribute(
      "href",
      "/sync",
    );
    const uploads = fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");
    expect(uploads.map(([url]) => url)).toEqual([
      "/api/playlists/5/files?name=new.mp3",
      "/api/playlists/5/files?name=dupe.mp3",
    ]);
    expect(uploads[0]?.[1]?.body).toBe(files[0]);

    await user.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByText("Imported 1 of 2 files")).not.toBeInTheDocument();
  });

  it("is disabled while a job runs", async () => {
    setup({
      id: "j1",
      kind: "sync",
      label: "Sync",
      status: "running",
      started_at: 0,
      last_seq: 1,
    });
    const button = screen.getByRole("button", { name: "Import tracks" });
    await vi.waitFor(() => expect(button).toBeDisabled());
    expect(button).toHaveAttribute("title", "Wait until the running job ends");
  });
});
