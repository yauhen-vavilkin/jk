import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { useEvents } from "./events";
import { keys } from "./queries";

const made: FakeSource[] = [];
class FakeSource {
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    made.push(this);
  }
  addEventListener() {}
  close() {}
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it("reads the lists again when the stream comes back, not when it first opens", () => {
  vi.useFakeTimers();
  vi.stubGlobal("EventSource", FakeSource);
  const client = new QueryClient();
  const lists = [keys.flows, keys.presets, keys.savedFlows];
  for (const key of lists) client.setQueryData(key, []);
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  renderHook(() => useEvents(), { wrapper });
  const stale = () => lists.map((key) => client.getQueryState(key)?.isInvalidated);

  act(() => made[0]?.onopen?.());
  expect(stale()).toEqual([false, false, false]);

  act(() => {
    made[0]?.onerror?.();
    vi.advanceTimersByTime(1000);
  });
  act(() => made[1]?.onopen?.());
  expect(stale()).toEqual([true, true, true]);
});
