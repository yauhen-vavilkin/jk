// The live stream. `flow.updated` carries the whole flow and is authoritative:
// the cached copy is replaced by id, never merged.
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { keys, putFlow, putPreset, putSavedFlow } from "./queries";
import type { Flow, JenkinsStatus, Preset, SavedFlow } from "./types";

const FIRST_BACKOFF_MS = 1000;
const LAST_BACKOFF_MS = 10_000;

/** The pill only appears once the stream has really been gone for a while. */
const OFFLINE_AFTER_MS = 3000;

/** `offlineSince`: when the stream to JK went away, once it has been gone a while; else null. */
export function useEvents(): { offlineSince: string | null } {
  const client = useQueryClient();
  const [offlineSince, setOfflineSince] = useState<string | null>(null);

  useEffect(() => {
    let source: EventSource | null = null;
    let backoff = FIRST_BACKOFF_MS;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    let markOffline: ReturnType<typeof setTimeout> | undefined;
    let lostAt: string | null = null;
    let stopped = false;

    const connect = () => {
      source = new EventSource("/api/events");

      source.onopen = () => {
        backoff = FIRST_BACKOFF_MS;
        clearTimeout(markOffline);
        // Back after a gap: the events sent meanwhile are lost, so read the lists again.
        if (lostAt !== null) {
          for (const queryKey of [keys.flows, keys.presets, keys.savedFlows]) {
            void client.invalidateQueries({ queryKey });
          }
        }
        lostAt = null;
        setOfflineSince(null);
      };

      source.addEventListener("flow.updated", (event) => {
        putFlow(client, JSON.parse((event as MessageEvent).data) as Flow);
      });
      source.addEventListener("preset.updated", (event) => {
        putPreset(client, JSON.parse((event as MessageEvent).data) as Preset);
      });
      source.addEventListener("saved_flow.updated", (event) => {
        putSavedFlow(client, JSON.parse((event as MessageEvent).data) as SavedFlow);
      });
      source.addEventListener("jenkins.status", (event) => {
        client.setQueryData<JenkinsStatus>(
          keys.jenkinsStatus,
          JSON.parse((event as MessageEvent).data) as JenkinsStatus,
        );
      });
      source.addEventListener("index.refreshed", () => {
        void client.invalidateQueries({ queryKey: ["jenkins-jobs"] });
      });

      source.onerror = () => {
        source?.close();
        if (stopped) return;
        // The first failure is when it went away; the retries after it are not.
        if (lostAt === null) {
          const since = new Date().toISOString();
          lostAt = since;
          markOffline = setTimeout(() => setOfflineSince(since), OFFLINE_AFTER_MS);
        }
        reconnect = setTimeout(connect, backoff);
        backoff = Math.min(LAST_BACKOFF_MS, backoff * 2);
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(reconnect);
      clearTimeout(markOffline);
      source?.close();
    };
  }, [client]);

  return { offlineSince };
}
