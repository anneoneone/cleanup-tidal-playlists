import type { JobEvent } from "../api/types";

export type StepStatus = "running" | "done" | "failed" | "cancelled";
export type LogLevel = "debug" | "info" | "warning" | "error";
export type StreamStatus =
  "connecting" | "running" | "succeeded" | "failed" | "cancelled";

export interface JobStep {
  name: string;
  status: StepStatus;
  current: number | null;
  total: number | null;
  /** Latest progress message (the item being worked on). */
  message: string;
  startedAt: number;
  finishedAt: number | null;
}

export interface LogLine {
  seq: number;
  time: number;
  level: LogLevel;
  step: string | null;
  message: string;
}

export interface JobStreamState {
  lastSeq: number;
  status: StreamStatus;
  steps: JobStep[];
  logs: LogLine[];
  /** Message of the terminal event (error text when failed). */
  message: string | null;
  /** True while the event stream is down and a reconnect is pending. */
  reconnecting: boolean;
  /** Set when the job can no longer be followed (e.g. the server restarted). */
  lost: string | null;
}

export type JobStreamAction =
  | { type: "event"; event: JobEvent }
  | { type: "disconnected" }
  | { type: "connected" }
  | { type: "lost"; message: string };

export function initialJobState(): JobStreamState {
  return {
    lastSeq: 0,
    status: "connecting",
    steps: [],
    logs: [],
    message: null,
    reconnecting: false,
    lost: null,
  };
}

export function isTerminal(status: StreamStatus): boolean {
  return status === "succeeded" || status === "failed" || status === "cancelled";
}

function normalizeLevel(level: string | null): LogLevel {
  switch ((level ?? "info").toLowerCase()) {
    case "debug":
      return "debug";
    case "warn":
    case "warning":
      return "warning";
    case "error":
    case "critical":
    case "exception":
      return "error";
    default:
      return "info";
  }
}

/** Close the running step(s) with `status`. */
function closeSteps(steps: JobStep[], status: StepStatus, time: number): JobStep[] {
  return steps.map((step) =>
    step.status === "running"
      ? {
          ...step,
          status,
          finishedAt: time,
          current: status === "done" && step.total !== null ? step.total : step.current,
        }
      : step,
  );
}

function findStepIndex(steps: JobStep[], name: string | null): number {
  if (name !== null) {
    for (let i = steps.length - 1; i >= 0; i -= 1) {
      if (steps[i]?.name === name) return i;
    }
  }
  return steps.length - 1;
}

/** Fold one job event into the state. Events at or below `lastSeq` are ignored. */
export function applyJobEvent(state: JobStreamState, event: JobEvent): JobStreamState {
  if (event.seq <= state.lastSeq) return state;
  const next: JobStreamState = { ...state, lastSeq: event.seq, reconnecting: false };
  if (next.status === "connecting") next.status = "running";

  switch (event.kind) {
    case "started":
      return next;
    case "step": {
      const steps = closeSteps(state.steps, "done", event.time);
      steps.push({
        name: event.step ?? event.message,
        status: "running",
        current: null,
        total: null,
        message: "",
        startedAt: event.time,
        finishedAt: null,
      });
      return { ...next, steps };
    }
    case "progress": {
      const steps = [...state.steps];
      let index = findStepIndex(steps, event.step);
      if (index < 0) {
        steps.push({
          name: event.step ?? "Working",
          status: "running",
          current: null,
          total: null,
          message: "",
          startedAt: event.time,
          finishedAt: null,
        });
        index = steps.length - 1;
      }
      const step = steps[index];
      if (step) {
        steps[index] = {
          ...step,
          current: event.current,
          total: event.total,
          message: event.message,
        };
      }
      return { ...next, steps };
    }
    case "log":
      return {
        ...next,
        logs: [
          ...state.logs,
          {
            seq: event.seq,
            time: event.time,
            level: normalizeLevel(event.level),
            step: event.step,
            message: event.message,
          },
        ],
      };
    case "finished":
      return {
        ...next,
        status: "succeeded",
        message: event.message,
        steps: closeSteps(state.steps, "done", event.time),
      };
    case "failed":
      return {
        ...next,
        status: "failed",
        message: event.message,
        steps: closeSteps(state.steps, "failed", event.time),
      };
    case "cancelled":
      return {
        ...next,
        status: "cancelled",
        message: event.message,
        steps: closeSteps(state.steps, "cancelled", event.time),
      };
    default:
      return next;
  }
}

export function jobStreamReducer(
  state: JobStreamState,
  action: JobStreamAction,
): JobStreamState {
  switch (action.type) {
    case "event":
      return applyJobEvent(state, action.event);
    case "disconnected":
      return isTerminal(state.status) ? state : { ...state, reconnecting: true };
    case "connected":
      return { ...state, reconnecting: false };
    case "lost":
      return { ...state, reconnecting: false, lost: action.message };
  }
}

export function countLevels(logs: LogLine[]): { warnings: number; errors: number } {
  let warnings = 0;
  let errors = 0;
  for (const line of logs) {
    if (line.level === "warning") warnings += 1;
    else if (line.level === "error") errors += 1;
  }
  return { warnings, errors };
}
