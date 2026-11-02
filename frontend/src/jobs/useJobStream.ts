import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useReducer, useRef } from "react";
import { api, isApiError } from "../api/client";
import { invalidateAfterJob, queryKeys, useJob } from "../api/queries";
import {
  JOB_EVENT_KINDS,
  type JobEvent,
  type JobOut,
  TERMINAL_EVENT_KINDS,
} from "../api/types";
import { initialJobState, isTerminal, jobStreamReducer } from "./jobState";

const MAX_RETRY_DELAY_MS = 5000;

function parseEvent(data: unknown): JobEvent | null {
  if (typeof data !== "string") return null;
  try {
    const value = JSON.parse(data) as JobEvent;
    return typeof value.seq === "number" && typeof value.kind === "string" ? value : null;
  } catch {
    return null;
  }
}

/**
 * Follow a job over SSE. Reconnects with `after=<last seq>` when the stream
 * drops while the job still runs. After the terminal event it loads the job
 * (for its `result`) and refreshes the data the job may have changed.
 *
 * Mount it with `key={jobId}` so a new job starts with a fresh state.
 */
export function useJobStream(jobId: string) {
  const queryClient = useQueryClient();
  const [state, dispatch] = useReducer(jobStreamReducer, undefined, initialJobState);
  const lastSeq = useRef(0);
  const terminal = isTerminal(state.status);
  const job = useJob(jobId);

  useEffect(() => {
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let attempts = 0;

    const onMessage = (message: MessageEvent<unknown>) => {
      const event = parseEvent(message.data);
      if (!event || event.seq <= lastSeq.current) return;
      lastSeq.current = event.seq;
      attempts = 0;
      dispatch({ type: "event", event });
      if (TERMINAL_EVENT_KINDS.has(event.kind)) {
        stopped = true;
        source?.close();
        void invalidateAfterJob(queryClient).then(() =>
          queryClient.invalidateQueries({ queryKey: queryKeys.job(jobId) }),
        );
      }
    };

    const connect = () => {
      const url = `/api/jobs/${encodeURIComponent(jobId)}/events?after=${lastSeq.current}`;
      source = new EventSource(url);
      for (const kind of JOB_EVENT_KINDS) source.addEventListener(kind, onMessage);
      source.onopen = () => dispatch({ type: "connected" });
      source.onerror = () => {
        source?.close();
        if (stopped) return;
        dispatch({ type: "disconnected" });
        attempts += 1;
        timer = setTimeout(
          () => void reconnect(),
          Math.min(1000 * attempts, MAX_RETRY_DELAY_MS),
        );
      };
    };

    const reconnect = async () => {
      if (stopped) return;
      try {
        await api.get<JobOut>(`/api/jobs/${encodeURIComponent(jobId)}`);
      } catch (error) {
        if (stopped) return;
        if (isApiError(error, 404)) {
          stopped = true;
          dispatch({
            type: "lost",
            message: "The server no longer knows this job. It may have restarted.",
          });
          // Drop the last "running" snapshot, so pages stop treating it as running.
          queryClient.removeQueries({ queryKey: queryKeys.job(jobId) });
          void invalidateAfterJob(queryClient);
          return;
        }
        attempts += 1;
        timer = setTimeout(
          () => void reconnect(),
          Math.min(1000 * attempts, MAX_RETRY_DELAY_MS),
        );
        return;
      }
      if (!stopped) connect();
    };

    connect();
    return () => {
      stopped = true;
      source?.close();
      clearTimeout(timer);
    };
  }, [jobId, queryClient]);

  // The job snapshot after the terminal event carries the `result`.
  const finalJob =
    terminal && job.data && job.data.status !== "running" ? job.data : undefined;
  return { state, job: job.data, finalJob, jobError: job.error };
}
