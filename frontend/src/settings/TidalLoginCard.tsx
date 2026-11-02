import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { queryKeys, useStartTidalLogin, useTidalLogin } from "../api/queries";
import { Badge } from "../components/Badge";
import { Button } from "../components/Button";
import { Card } from "../components/Card";
import { ErrorNotice, Loading, Notice, Spinner } from "../components/Feedback";
import { ExternalIcon } from "../components/icons";

export function TidalLoginCard() {
  const login = useTidalLogin();
  const start = useStartTidalLogin();
  const queryClient = useQueryClient();
  const state = login.data?.state;
  // GET does not return the link, so keep the one from POST while the login is pending.
  const link = state === "pending" ? start.data : undefined;

  useEffect(() => {
    if (state === "done")
      void queryClient.invalidateQueries({ queryKey: queryKeys.status });
  }, [state, queryClient]);

  return (
    <Card
      title="Tidal login"
      actions={
        login.data &&
        (login.data.logged_in ? (
          <Badge tone="green">logged in</Badge>
        ) : (
          <Badge tone="amber">not logged in</Badge>
        ))
      }
    >
      {login.isPending && <Loading />}
      {login.isError && (
        <ErrorNotice
          error={login.error}
          title="Could not load the login state"
          onRetry={() => void login.refetch()}
        />
      )}
      {login.data && (
        <div className="space-y-3 text-sm">
          <p className="text-muted">
            Cratekeeper needs a Tidal login to read your playlists and download tracks.
            The login is stored in the Cratekeeper home folder.
          </p>
          {state === "pending" && (
            <div className="space-y-2 rounded-md border border-line bg-surface-2 p-3">
              {link?.url ? (
                <>
                  <p>Open this link, log in to Tidal and confirm the code:</p>
                  <a
                    href={link.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-medium break-all text-accent hover:underline"
                  >
                    {link.url}
                    <ExternalIcon className="size-3.5 shrink-0" />
                  </a>
                  {link.user_code && (
                    <p>
                      Code:{" "}
                      <span className="font-mono text-base font-semibold tracking-wider">
                        {link.user_code}
                      </span>
                    </p>
                  )}
                </>
              ) : (
                <p>A login is in progress. Start it again to get a new link.</p>
              )}
              <p className="flex items-center gap-2 text-xs text-muted" role="status">
                <Spinner className="size-3.5" /> Waiting for Tidal…
              </p>
            </div>
          )}
          {state === "done" && (
            <Notice tone="success">You are logged in to Tidal.</Notice>
          )}
          {state === "failed" && (
            <Notice tone="danger" title="The login failed">
              {login.data.error || "Unknown error"}
            </Notice>
          )}
          {start.error && (
            <ErrorNotice error={start.error} title="Could not start the login" />
          )}
          <Button
            variant={login.data.logged_in ? "secondary" : "primary"}
            onClick={() => start.mutate()}
            busy={start.isPending}
          >
            {state === "pending"
              ? "Start again"
              : login.data.logged_in
                ? "Log in again"
                : "Log in to Tidal"}
          </Button>
        </div>
      )}
    </Card>
  );
}
