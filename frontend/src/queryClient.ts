import { QueryClient } from "@tanstack/react-query";
import { isApiError } from "./api/client";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        // Retry network problems and server errors once, never client errors.
        retry: (failureCount, error) =>
          failureCount < 1 &&
          !(isApiError(error) && error.status >= 400 && error.status < 500),
      },
      mutations: { retry: false },
    },
  });
}
