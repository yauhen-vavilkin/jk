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
  const copy = { id: "copy", name: "Nightly copy", status: "draft", steps: [] } as unknown as Flow;
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
  const copy = { id: "copy", name: "Nightly copy", status: "draft", steps: [] } as unknown as Flow;
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

const stepOf = (position: number, name: string) => ({
  id: `f:${position}`, position, preset_id: `p-${name}`, preset_name: name, state: "planned",
  condition: position ? "after_success" : "unless_failure", run_values: { BRANCH: `b-${name}` },
  summary: [], held: false, build_number: null, abort_state: null, added_while_running: false,
});
const draftOf = (names: string[]) =>
  ({
    id: "f", name: "Draft", status: "draft", pinned: false, cleared: false, saved_flow_id: null,
    steps: names.map((name, position) => stepOf(position, name)), current_position: null,
    started_at: null, finished_at: null, failed_at_position: null, estimate_ms: null, result: null,
  }) as unknown as Flow;

function showBoard() {
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <RouterProvider router={createMemoryRouter([{ path: "/", element: <Board /> }])} />
  </QueryClientProvider>);
}

it("removes a step of a draft at once and puts it back as it was on Undo", async () => {
  vi.spyOn(api, "get").mockImplementation(((path: string) =>
    Promise.resolve(path === "/flows" ? [draftOf(["Build", "Deploy"])] : [])) as typeof api.get);
  const remove = vi.spyOn(api, "delete").mockResolvedValue(draftOf(["Build"]));
  const post = vi.spyOn(api, "post").mockResolvedValue(draftOf(["Build", "Deploy"]));
  showBoard();

  const buttons = await screen.findAllByRole("button", { name: "Remove step" });
  fireEvent.click(buttons[1] as HTMLElement);

  expect(await screen.findByText('Removed step 2 "Deploy"')).toBeInTheDocument();
  expect(remove).toHaveBeenCalledWith("/flows/f/steps/f:1");
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith("/flows/f/steps", {
      preset_id: "p-Deploy",
      condition: "after_success",
      run_values: { BRANCH: "b-Deploy" },
      position: 1,
    }),
  );
});

it("moves a step and moves it back on Undo", async () => {
  vi.spyOn(api, "get").mockImplementation(((path: string) =>
    Promise.resolve(path === "/flows" ? [draftOf(["Build", "Deploy"])] : [])) as typeof api.get);
  const patch = vi.spyOn(api, "patch").mockResolvedValue(draftOf(["Deploy", "Build"]));
  showBoard();

  fireEvent.click(await screen.findByRole("button", { name: "Step 2, Deploy" }));
  fireEvent.click(await screen.findByRole("button", { name: "Move to step 1" }));

  expect(await screen.findByText('Moved "Deploy" to step 1')).toBeInTheDocument();
  expect(patch).toHaveBeenCalledWith("/flows/f/steps/f:1", { position: 0 });
  fireEvent.click(screen.getByRole("button", { name: "Undo" }));
  await waitFor(() => expect(patch).toHaveBeenLastCalledWith("/flows/f/steps/f:0", { position: 1 }));
});
