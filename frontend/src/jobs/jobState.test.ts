import { describe, expect, it } from "vitest";
import type { JobEvent } from "../api/types";
import {
  applyJobEvent,
  countLevels,
  initialJobState,
  type JobStreamState,
  jobStreamReducer,
} from "./jobState";

let seq = 0;
function ev(kind: JobEvent["kind"], fields: Partial<JobEvent> = {}): JobEvent {
  seq += 1;
  return {
    seq,
    job_id: "j1",
    kind,
    message: "",
    step: null,
    current: null,
    total: null,
    level: null,
    time: 1000 + seq,
    ...fields,
  };
}

function fold(
  events: JobEvent[],
  state: JobStreamState = initialJobState(),
): JobStreamState {
  return events.reduce(applyJobEvent, state);
}

describe("applyJobEvent", () => {
  it("lists steps in arrival order and closes the previous step", () => {
    seq = 0;
    const state = fold([
      ev("started", { message: "Sync" }),
      ev("step", { step: "Backup", message: "Backup" }),
      ev("step", { step: "Refresh Bandcamp", message: "Refresh Bandcamp" }),
      ev("progress", {
        step: "Refresh Bandcamp",
        current: 2,
        total: 5,
        message: "Dub Lab",
      }),
    ]);
    expect(state.status).toBe("running");
    expect(state.steps.map((s) => [s.name, s.status])).toEqual([
      ["Backup", "done"],
      ["Refresh Bandcamp", "running"],
    ]);
    expect(state.steps[1]).toMatchObject({ current: 2, total: 5, message: "Dub Lab" });
  });

  it("ignores repeated events (reconnect replays)", () => {
    seq = 0;
    const first = ev("step", { step: "Plan" });
    const state = fold([first, ev("log", { message: "hello" })]);
    expect(applyJobEvent(state, first)).toBe(state);
    expect(state.lastSeq).toBe(2);
  });

  it("collects log lines with normalized levels", () => {
    seq = 0;
    const state = fold([
      ev("log", { message: "a", level: "info" }),
      ev("log", { message: "b", level: "WARNING" }),
      ev("log", { message: "c", level: "error" }),
      ev("log", { message: "d", level: null }),
    ]);
    expect(state.logs.map((l) => l.level)).toEqual(["info", "warning", "error", "info"]);
    expect(countLevels(state.logs)).toEqual({ warnings: 1, errors: 1 });
  });

  it("marks the run as finished and fills the last progress bar", () => {
    seq = 0;
    const state = fold([
      ev("step", { step: "Download" }),
      ev("progress", { step: "Download", current: 3, total: 4 }),
      ev("finished", { message: "Done" }),
    ]);
    expect(state.status).toBe("succeeded");
    expect(state.steps[0]).toMatchObject({ status: "done", current: 4, total: 4 });
  });

  it("marks the running step as failed or cancelled", () => {
    seq = 0;
    const failed = fold([
      ev("step", { step: "Refresh Tidal" }),
      ev("failed", { message: "Not logged in" }),
    ]);
    expect(failed.status).toBe("failed");
    expect(failed.message).toBe("Not logged in");
    expect(failed.steps[0]?.status).toBe("failed");

    const cancelled = fold([
      ev("step", { step: "Download" }),
      ev("cancelled", { message: "Cancelled" }),
    ]);
    expect(cancelled.steps[0]?.status).toBe("cancelled");
  });

  it("creates a step for progress that arrives before any step event", () => {
    seq = 0;
    const state = fold([ev("progress", { step: "Apply", current: 1, total: 3 })]);
    expect(state.steps[0]).toMatchObject({ name: "Apply", current: 1, total: 3 });
  });
});

describe("jobStreamReducer", () => {
  it("tracks reconnecting until the next event", () => {
    seq = 0;
    let state = jobStreamReducer(initialJobState(), { type: "disconnected" });
    expect(state.reconnecting).toBe(true);
    state = jobStreamReducer(state, { type: "event", event: ev("started") });
    expect(state.reconnecting).toBe(false);
  });

  it("does not show reconnecting after the job ended", () => {
    seq = 0;
    const done = fold([ev("finished")]);
    expect(jobStreamReducer(done, { type: "disconnected" }).reconnecting).toBe(false);
  });
});
