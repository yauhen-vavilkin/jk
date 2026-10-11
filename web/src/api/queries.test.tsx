import { focusManager, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./client";
import {
  keys,
  useClearFlow,
  useCloseFlow,
  useJenkinsJobs,
  usePresetUsage,
  useSaveAsFlow,
  useSavedFlows,
  useSavingFlows,
} from "./queries";
import type { Flow, JenkinsJob, PresetUsage, SavedFlow } from "./types";

afterEach(() => vi.restoreAllMocks());

describe("saving a flow", () => {
  it("is still saving until the saved flows are read again", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const kept = { id: "kept", name: "Nightly", steps: [] } as unknown as SavedFlow;
    let answer: (list: SavedFlow[]) => void = () => {};
    let reads = 0;
    vi.spyOn(api, "get").mockImplementation(((path: string) => {
      if (path !== "/saved-flows") return Promise.reject(new Error(`unexpected ${path}`));
      reads += 1;
      // The first read answers at once; the one after the save waits for the test.
      if (reads === 1) return Promise.resolve([]);
      return new Promise<SavedFlow[]>((resolve) => {
        answer = resolve;
      });
    }) as typeof api.get);
    vi.spyOn(api, "post").mockResolvedValue({ id: "f1", saved_flow_id: "kept" } as Flow);

    const { result } = renderHook(
      () => ({ save: useSaveAsFlow(), saving: useSavingFlows(), list: useSavedFlows() }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    act(() => {
      void result.current.save.mutateAsync("f1");
    });
    await waitFor(() => expect(reads).toBe(2));
    // The flow is kept by now, but the list does not know it yet: still saving.
    expect(result.current.saving).toEqual(["f1"]);

    await act(async () => answer([kept]));
    await waitFor(() => expect(result.current.saving).toEqual([]));
    expect(client.getQueryData(keys.savedFlows)).toEqual([kept]);
  });

  it("stops saving when the save is refused", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    vi.spyOn(api, "post").mockRejectedValue(new Error("Refused for the test."));
    const { result } = renderHook(() => ({ save: useSaveAsFlow(), saving: useSavingFlows() }), { wrapper });

    await act(async () => {
      await result.current.save.mutateAsync("f1").catch(() => {});
    });

    expect(result.current.saving).toEqual([]);
  });

  it("reads the saved flows again when the tab comes back into view", async () => {
    // The panel's own defaults (main.tsx): no refetch on focus, and five seconds fresh.
    const client = new QueryClient({
      defaultOptions: { queries: { refetchOnWindowFocus: false, retry: false, staleTime: 5000 } },
    });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const get = vi.spyOn(api, "get").mockResolvedValue([]);
    const { result } = renderHook(() => useSavedFlows(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const before = get.mock.calls.length;

    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });

    await waitFor(() => expect(get.mock.calls.length).toBeGreaterThan(before));
    focusManager.setFocused(undefined);
  });
});

describe("what the board and the library send", () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const flow = { id: "f1", cleared: false } as Flow;

  it("ends a flow with the builds the window listed", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue(flow);
    const { result } = renderHook(() => useCloseFlow(), { wrapper });

    await act(() => result.current.mutateAsync({ flowId: "f1", buildNumbers: [9928] }));

    expect(post).toHaveBeenCalledWith("/flows/f1/close", { build_numbers: [9928] });
  });

  it("puts a flow back on the board with cleared false", async () => {
    const patch = vi.spyOn(api, "patch").mockResolvedValue(flow);
    const { result } = renderHook(() => useClearFlow(), { wrapper });

    await act(() => result.current.mutateAsync({ flowId: "f1", cleared: false }));
    await act(() => result.current.mutateAsync({ flowId: "f1" }));

    expect(patch.mock.calls).toEqual([
      ["/flows/f1", { cleared: false }],
      ["/flows/f1", { cleared: true }],
    ]);
  });

  it("reads where a saved job is used", async () => {
    const usage: PresetUsage = {
      steps: [{ flow_id: "f1", flow_name: "Nightly", position: 1 }],
    };
    const get = vi.spyOn(api, "get").mockResolvedValue(usage);
    const { result } = renderHook(() => usePresetUsage("p1"), { wrapper });

    await waitFor(() => expect(result.current.data).toEqual(usage));
    expect(get).toHaveBeenCalledWith("/presets/p1/usage");
  });
});

describe("searching jenkins jobs", () => {
  it("keeps the last list while the answer for the next keystroke is on its way", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
    const job = { job_path: "a/build", name: "build", url: "" } as JenkinsJob;
    vi.spyOn(api, "get").mockImplementation(((path: string) =>
      path.endsWith("?q=") ? Promise.resolve([job]) : new Promise(() => {})) as typeof api.get);
    const { result, rerender } = renderHook(({ query }) => useJenkinsJobs(query), {
      wrapper,
      initialProps: { query: "" },
    });
    await waitFor(() => expect(result.current.data).toEqual([job]));

    rerender({ query: "b" });

    expect(result.current.data).toEqual([job]);
  });
});
