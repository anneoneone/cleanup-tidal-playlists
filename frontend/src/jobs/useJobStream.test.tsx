import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { JobEvent } from "../api/types";
import { useJobStream } from "./useJobStream";

type Listener = (event: { data: string }) => void;

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private listeners = new Map<string, Listener[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }
  addEventListener(kind: string, listener: Listener) {
    this.listeners.set(kind, [...(this.listeners.get(kind) ?? []), listener]);
  }
  close() {
    this.closed = true;
  }
  emit(event: Partial<JobEvent> & Pick<JobEvent, "seq" | "kind">) {
    const data = JSON.stringify({
      job_id: "j1",
      message: "",
      step: null,
      current: null,
      total: null,
      level: null,
      time: 1,
      ...event,
    });
    for (const listener of this.listeners.get(event.kind) ?? []) listener({ data });
  }
}

let jobStatus = "running";

beforeEach(() => {
  FakeEventSource.instances = [];
  jobStatus = "running";
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) =>
      Promise.resolve(
        url === "/api/jobs/j1"
          ? new Response(
              JSON.stringify({
                id: "j1",
                kind: "sync",
                label: "Sync",
                status: jobStatus,
                started_at: 1,
                last_seq: 0,
                result: jobStatus === "succeeded" ? { run_id: 5, empty: false } : null,
              }),
            )
          : new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }),
      ),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function setup(jobId = "j1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useJobStream(jobId), { wrapper });
}

describe("useJobStream", () => {
  it("reconnects with after=<last seq>, skips replayed events and loads the result", async () => {
    const { result } = setup();
    const first = FakeEventSource.instances[0]!;
    expect(first.url).toBe("/api/jobs/j1/events?after=0");

    act(() => {
      first.emit({ seq: 1, kind: "started", message: "Sync" });
      first.emit({ seq: 2, kind: "step", step: "Backup" });
      first.emit({ seq: 3, kind: "step", step: "Plan" });
    });
    expect(result.current.state.steps.map((s) => s.name)).toEqual(["Backup", "Plan"]);

    act(() => first.onerror?.());
    expect(first.closed).toBe(true);
    expect(result.current.state.reconnecting).toBe(true);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2), {
      timeout: 3000,
    });
    const second = FakeEventSource.instances[1]!;
    expect(second.url).toBe("/api/jobs/j1/events?after=3");

    jobStatus = "succeeded";
    act(() => {
      second.emit({ seq: 3, kind: "step", step: "Plan" });
      second.emit({ seq: 4, kind: "finished", message: "Done" });
    });
    expect(second.closed).toBe(true);
    expect(result.current.state.status).toBe("succeeded");
    expect(result.current.state.steps).toHaveLength(2);

    await waitFor(() =>
      expect(result.current.finalJob?.result).toEqual({ run_id: 5, empty: false }),
    );
  });

  it("stops when the server does not know the job", async () => {
    const { result } = setup("missing");
    act(() => FakeEventSource.instances[0]!.onerror?.());
    await waitFor(
      () => expect(result.current.state.lost).toMatch(/no longer knows this job/),
      { timeout: 3000 },
    );
    expect(FakeEventSource.instances).toHaveLength(1);
  });

  it("drops the last running snapshot when the server forgets the job", async () => {
    const { result } = setup("j1");
    await waitFor(() => expect(result.current.job?.status).toBe("running"));
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve(
          new Response(JSON.stringify({ detail: "Not found" }), { status: 404 }),
        ),
      ),
    );
    act(() => FakeEventSource.instances[0]!.onerror?.());
    await waitFor(() => expect(result.current.state.lost).toBeTruthy(), {
      timeout: 3000,
    });
    await waitFor(() => expect(result.current.job).toBeUndefined());
  });
});
