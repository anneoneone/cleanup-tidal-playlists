import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ReactNode, useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SettingsOut } from "../api/types";
import Settings from "../pages/Settings";
import { PathInput } from "./PathInput";

type Handler = (url: string, init: RequestInit) => Response;

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** The JSON body of a request (the client always sends a string). */
function bodyOf(init: RequestInit | undefined): unknown {
  return typeof init?.body === "string" ? JSON.parse(init.body) : undefined;
}

function stubFetch(handler: Handler) {
  const fetchMock = vi.fn((url: string, init: RequestInit) =>
    Promise.resolve(handler(url, init)),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function Harness({ initial = "" }: { initial?: string }) {
  const [value, setValue] = useState(initial);
  return (
    <PathInput
      id="music"
      field="music_folder"
      label="Music folder"
      value={value}
      onChange={setValue}
    />
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PathInput", () => {
  it("fills the input with the chosen path", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch(() => json({ path: "/Volumes/HDD1TB/Music" }));
    render(<Harness initial="/Users/me/Music" />, { wrapper });

    await user.click(screen.getByRole("button", { name: "Choose Music folder" }));

    await waitFor(() =>
      expect(screen.getByRole("textbox")).toHaveValue("/Volumes/HDD1TB/Music"),
    );
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/settings/pick-path");
    expect(init?.method).toBe("POST");
    expect(init?.headers).toMatchObject({ "X-Cratekeeper": "1" });
    expect(bodyOf(init)).toEqual({
      field: "music_folder",
      start: "/Users/me/Music",
    });
  });

  it("keeps the value when the dialog is cancelled", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch(() => json({ path: null }));
    render(<Harness initial="/Users/me/Music" />, { wrapper });

    await user.click(screen.getByRole("button", { name: "Choose Music folder" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Choose Music folder" })).toBeEnabled(),
    );
    expect(screen.getByRole("textbox")).toHaveValue("/Users/me/Music");
  });

  it("sends no start for an empty field and shows server errors", async () => {
    const user = userEvent.setup();
    const fetchMock = stubFetch(() =>
      json({ detail: "A Finder dialog is open already. Close it first." }, 409),
    );
    render(<Harness />, { wrapper });

    await user.click(screen.getByRole("button", { name: "Choose Music folder" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "A Finder dialog is open already. Close it first.",
    );
    expect(bodyOf(fetchMock.mock.calls[0]?.[1])).toEqual({
      field: "music_folder",
      start: null,
    });
    await user.type(screen.getByRole("textbox"), "/x");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Settings path pickers", () => {
  const settings: SettingsOut = {
    values: {
      music_folder: "/Users/me/Music",
      bandcamp_folder: null,
      rekordbox_db: null,
      tag_mapping: null,
      target_format: "mp3",
      ffmpeg_quality: 2,
      download_quality: "LOSSLESS",
      prune_tracks: true,
      backups_keep_full: 20,
      backups_keep_db: 10,
      port: 8765,
    },
    tag_mapping_in_use: "/defaults/tag_mapping.json",
    config_file: "/Users/me/.cratekeeper/config.toml",
  };

  it("offers a picker for every path and saves only on Save", async () => {
    const user = userEvent.setup();
    const puts: unknown[] = [];
    stubFetch((url, init) => {
      if (url === "/api/settings/pick-path") {
        return json({ path: "/Users/me/Library/Pioneer/rekordbox/master.db" });
      }
      if (url === "/api/settings" && init.method === "PUT") {
        const body = bodyOf(init);
        puts.push(body);
        return json({ ...settings, values: body });
      }
      if (url === "/api/settings") return json(settings);
      if (url === "/api/auth/tidal") return json({ logged_in: true, state: "idle" });
      return json({ emoji_to_mytag_mapping: {}, folder_structure: {} });
    });
    render(<Settings />, { wrapper });

    for (const label of [
      "Music folder",
      "Bandcamp folder",
      "Rekordbox library",
      "Playlist tag mapping file",
    ]) {
      expect(
        await screen.findByRole("button", { name: `Choose ${label}` }),
      ).toBeInTheDocument();
    }
    await user.click(screen.getByRole("button", { name: "Choose Rekordbox library" }));

    const input = screen.getByLabelText("Rekordbox library");
    await waitFor(() =>
      expect(input).toHaveValue("/Users/me/Library/Pioneer/rekordbox/master.db"),
    );
    expect(puts).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Save settings" }));

    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]).toMatchObject({
      rekordbox_db: "/Users/me/Library/Pioneer/rekordbox/master.db",
      music_folder: "/Users/me/Music",
    });
  });
});
