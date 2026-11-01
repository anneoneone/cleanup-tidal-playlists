import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, isApiError, parseDetail } from "./client";

function mockFetch(status: number, body: unknown, contentType = "application/json") {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  const fetchMock = vi.fn((_input: RequestInfo | URL, _init?: RequestInit) =>
    Promise.resolve(
      new Response(status === 204 ? null : text, {
        status,
        headers: { "Content-Type": contentType },
      }),
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function headersOf(fetchMock: ReturnType<typeof mockFetch>): Record<string, string> {
  const init = fetchMock.mock.calls[0]?.[1];
  return (init?.headers ?? {}) as Record<string, string>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api client", () => {
  it("sends GET without the X-Cratekeeper header", async () => {
    const fetchMock = mockFetch(200, { ok: true });
    await expect(api.get("/api/status")).resolves.toEqual({ ok: true });
    expect(headersOf(fetchMock)["X-Cratekeeper"]).toBeUndefined();
  });

  it("sends the X-Cratekeeper header and a JSON body on POST and PUT", async () => {
    const fetchMock = mockFetch(202, { id: "job1" });
    await api.post("/api/sync", { offline: true });
    const init = fetchMock.mock.calls[0]?.[1];
    expect(init?.method).toBe("POST");
    expect(headersOf(fetchMock)["X-Cratekeeper"]).toBe("1");
    expect(headersOf(fetchMock)["Content-Type"]).toBe("application/json");
    expect(init?.body).toBe('{"offline":true}');
  });

  it("sends the header even without a body", async () => {
    const fetchMock = mockFetch(200, { cancelled: true });
    await api.post("/api/jobs/x/cancel");
    expect(headersOf(fetchMock)["X-Cratekeeper"]).toBe("1");
    expect(headersOf(fetchMock)["Content-Type"]).toBeUndefined();
  });

  it("returns null for a JSON null body", async () => {
    mockFetch(200, null);
    await expect(api.get("/api/jobs/current")).resolves.toBeNull();
  });

  it("turns a string detail into the error message", async () => {
    mockFetch(409, { detail: "A job is already running: Sync" });
    const error = await api.post("/api/sync", {}).catch((e: unknown) => e);
    expect(isApiError(error, 409)).toBe(true);
    expect((error as ApiError).message).toBe("A job is already running: Sync");
  });

  it("turns a pydantic error list into field errors", async () => {
    mockFetch(422, {
      detail: [
        {
          type: "less_than_equal",
          loc: ["ffmpeg_quality"],
          msg: "Input should be less than or equal to 9",
        },
        { type: "missing", loc: ["body", "groups"], msg: "Field required" },
      ],
    });
    const error = (await api
      .put("/api/settings", {})
      .catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(422);
    expect(error.fieldErrors.map((e) => e.field)).toEqual(["ffmpeg_quality", "groups"]);
    expect(error.message).toBe(
      "ffmpeg_quality: Input should be less than or equal to 9; groups: Field required",
    );
  });

  it("uses a plain text body or the status when there is no JSON", async () => {
    mockFetch(500, "Internal Server Error", "text/plain");
    await expect(api.get("/api/status")).rejects.toThrow("Internal Server Error");
    mockFetch(502, "");
    await expect(api.get("/api/status")).rejects.toThrow(/^502/);
  });

  it("reports a network failure in plain words", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))),
    );
    const error = (await api.get("/api/status").catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(0);
    expect(error.message).toMatch(/Cannot reach the Cratekeeper server/);
  });
});

describe("parseDetail", () => {
  it("ignores unknown shapes", () => {
    expect(parseDetail({ foo: 1 })).toEqual({ message: null, fieldErrors: [] });
    expect(parseDetail([{ loc: [], msg: "Bad body" }]).message).toBe("Bad body");
  });
});
