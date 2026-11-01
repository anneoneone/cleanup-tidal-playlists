import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "../api/queries";
import type { TagMapping } from "../api/types";
import { TagMappingEditor } from "./TagMappingEditor";

function mappingWith(category: string): TagMapping {
  return {
    emoji_to_mytag_mapping: { Genre: { "🏢": "Techno" } },
    folder_structure: {
      genre_root: "Genre",
      genre_categories: { [category]: ["Techno"] },
      events_types: ["Partys"],
    },
  };
}

function setup(serve: () => TagMapping) {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(serve())))),
  );
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  render(<TagMappingEditor fileInUse="/home/tag_mapping.json" />, { wrapper });
  return client;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("TagMappingEditor", () => {
  it("keeps unsaved edits when the mapping is fetched again", async () => {
    const user = userEvent.setup();
    const client = setup(() => mappingWith("Techno"));
    const name = await screen.findByLabelText("Category 1 name");
    await user.clear(name);
    await user.type(name, "Hard Techno");

    await client.invalidateQueries({ queryKey: queryKeys.tagMapping });

    expect(screen.getByLabelText("Category 1 name")).toHaveValue("Hard Techno");
    expect(screen.getByRole("button", { name: "Save mapping" })).toBeEnabled();
  });

  it("follows a new copy of the file when nothing is edited", async () => {
    let category = "Techno";
    const client = setup(() => mappingWith(category));
    expect(await screen.findByLabelText("Category 1 name")).toHaveValue("Techno");

    category = "Dub Techno";
    await client.invalidateQueries({ queryKey: queryKeys.tagMapping });

    await waitFor(() =>
      expect(screen.getByLabelText("Category 1 name")).toHaveValue("Dub Techno"),
    );
  });
});
