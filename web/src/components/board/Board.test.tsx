import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "@/api/client";
import type { Flow } from "@/api/types";
import Board from "./Board";

vi.mock("./useRail", () => ({ useRail: () => ({ collapsed: true, toggle: () => {} }) }));
afterEach(() => vi.restoreAllMocks());

it("keeps History's review and cancellation available when JK stops after copying", async () => {
  const copy = { id: "copy", name: "Nightly copy", status: "draft", steps: [], editing: false } as unknown as Flow;
  vi.spyOn(api, "get").mockImplementation(((path: string) =>
    path === "/flows" ? Promise.reject(new Error("offline")) : Promise.resolve([])) as typeof api.get);
  const post = vi.spyOn(api, "post").mockRejectedValue(new Error("offline"));
  const remove = vi.spyOn(api, "delete").mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
  const patch = vi.spyOn(api, "patch");
  const router = createMemoryRouter([{ path: "/", element: <Board /> }], {
    initialEntries: [{ pathname: "/", state: { review: copy, source: "original" } }],
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <RouterProvider router={router} />
  </QueryClientProvider>);
  expect(await screen.findByRole("dialog", { name: "Review and run" })).toBeInTheDocument();
  expect(await screen.findByText("JK could not be reached. Nothing was sent.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Run flow" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not cancel the copy");
  expect(screen.getByRole("dialog", { name: "Review and run" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(remove).toHaveBeenLastCalledWith("/flows/copy");
  expect(patch).not.toHaveBeenCalled();
  expect(post.mock.calls.every(([path]) => path.endsWith("/review"))).toBe(true);
});

it("reports source cleanup failure separately after a successful reviewed start", async () => {
  const copy = { id: "copy", name: "Nightly copy", status: "draft", steps: [], editing: false } as unknown as Flow;
  vi.spyOn(api, "get").mockResolvedValue([]);
  const post = vi.spyOn(api, "post").mockImplementation(((path: string) => Promise.resolve(
    path.endsWith("/review")
      ? { ok: true, review_token: "reviewed", issues: [], missing_run_values: [], same_target: [], steps: [
          { step_id: "s", position: 0, preset_name: "Build", condition: "unless_failure", sent: [], defaults: [] },
        ] }
      : { ...copy, status: "running" },
  )) as typeof api.post);
  const patch = vi.spyOn(api, "patch").mockRejectedValue(new Error("offline"));
  const router = createMemoryRouter([{ path: "/", element: <Board /> }], {
    initialEntries: [{ pathname: "/", state: { review: copy, source: "original" } }],
  });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <RouterProvider router={router} />
  </QueryClientProvider>);
  await waitFor(() => expect(screen.getByRole("button", { name: "Run flow" })).toBeEnabled());
  expect(patch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Run flow" }));
  expect(await screen.findByText("The new flow started. The previous run is still on the board; remove it when ready.")).toBeInTheDocument();
  expect(post).toHaveBeenCalledWith("/flows/copy/start", { run_values: {}, review_token: "reviewed" });
  expect(post.mock.calls.filter(([path]) => path.endsWith("/start"))).toHaveLength(1);
  expect(patch).toHaveBeenCalledWith("/flows/original", { cleared: true });
});
